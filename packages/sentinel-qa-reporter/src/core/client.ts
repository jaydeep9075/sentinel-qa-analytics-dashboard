import { readFileSync, statSync } from "node:fs";
import { basename } from "node:path";
import type { ResolvedConfig } from "./config";
import { redact, truncate } from "./redact";
import type { RunMeta, RunStatus, SentinelEvent } from "./types";

/**
 * The single HTTP client behind every framework adapter.
 *
 * Its one hard rule: **nothing in here may ever fail a test run**. The test
 * suite is the thing of value; reporting on it is not. Every network path is
 * wrapped, every request has a deadline, every queue has a ceiling, and the
 * worst outcome available to this class is a warning line on stdout followed
 * by silence. That constraint is what makes it safe to commit the
 * integration into a repo whose pipelines you cannot afford to break.
 */

/** Nothing here is worth waiting on for long: the run is still executing and
 * the reporter is racing it. A hung connection blocking the final flush
 * would hold the test process open after the last test finished, which is
 * the one failure mode a user would rightly blame on us. */
const REQUEST_TIMEOUT_MS = 10_000;
const UPLOAD_TIMEOUT_MS = 60_000;
/** Events pile up while the backend is unreachable. Past this, shed rather
 * than grow without bound - a long chatty suite against a backend that went
 * away mid-run is otherwise a real memory leak in the *test* process. */
const MAX_QUEUE = 500;
const FLUSH_AT = 25;
const MAX_ERROR_CHARS = 8_000;
const MAX_LOG_CHARS = 4_000;
/** Videos routinely run to tens of megabytes. The hot store keeps them on
 * local disk for the life of the run and serves them to every viewer, so an
 * unbounded upload is a way to fill a server's disk with one flaky suite. */
const MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024;

export interface StartResult {
  ok: boolean;
  runId?: string;
  watchUrl?: string;
  reason?: string;
}

export class SentinelClient {
  readonly config: ResolvedConfig;
  private runId: string | null = null;
  private disabled = false;
  private queue: SentinelEvent[] = [];
  private inflight: Promise<unknown>[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private flushing = false;
  private consecutiveFailures = 0;
  private skipTicks = 0;
  private warnedDropping = false;
  private finished = false;

  constructor(config: ResolvedConfig) {
    this.config = config;
    if (!config.enabled) this.disabled = true;
  }

  get id(): string | null {
    return this.runId;
  }

  get active(): boolean {
    return !this.disabled && this.runId !== null;
  }

  /** The unsent buffer. Exposed for tests only - nothing in production
   * reads it, but shedding behaviour is exactly the kind of thing that
   * quietly regresses without a test that can see inside. */
  get pending(): readonly SentinelEvent[] {
    return this.queue;
  }

  get watchUrl(): string | null {
    return this.runId ? `${this.config.dashboardUrl}/runs/${this.runId}/live` : null;
  }

  // -- lifecycle ---------------------------------------------------------

  async start(meta: RunMeta): Promise<StartResult> {
    if (this.disabled) return { ok: false, reason: "not configured" };
    try {
      const res = await this.request("/live/runs", {
        method: "POST",
        headers: this.jsonHeaders(),
        body: JSON.stringify({ ...meta, external_id: this.config.runKey }),
      });
      if (!res.ok) {
        this.disabled = true;
        return {
          ok: false,
          reason: explainFailure(res.status, this.config.url, !!this.config.apiKey),
        };
      }
      const data = (await res.json()) as { run_id: string };
      this.runId = data.run_id;
      this.flushTimer = setInterval(() => void this.flush(), 1000);
      // A background timer must never be the reason a finished test process
      // refuses to exit.
      this.flushTimer.unref?.();
      return { ok: true, runId: this.runId, watchUrl: this.watchUrl ?? undefined };
    } catch (err) {
      this.disabled = true;
      return { ok: false, reason: describeNetworkError(err, this.config.url) };
    }
  }

  /** Idempotent: a framework's own end hook and a signal handler can both
   * reach it, and finalizing twice would start the server-side promotion
   * into permanent history twice. */
  async finish(status: RunStatus): Promise<void> {
    if (this.flushTimer) clearInterval(this.flushTimer);
    if (this.finished || !this.active) {
      this.finished = true;
      return;
    }
    this.finished = true;
    await this.flush(true);
    await Promise.allSettled(this.inflight);
    try {
      await this.request(`/live/runs/${this.runId}`, {
        method: "PATCH",
        headers: this.jsonHeaders(),
        body: JSON.stringify({ status }),
      });
    } catch {
      // The server's stale-run sweeper clears an unfinished run within
      // LIVE_RUN_STALE_TIMEOUT_SECONDS, so a lost PATCH costs a stale row
      // for a few minutes rather than a permanent one - not worth a warning
      // at the very end of a run whose results the user is already reading.
    }
  }

  // -- events ------------------------------------------------------------

  emit(event: SentinelEvent): void {
    if (!this.active) return;
    if (event.test?.error) {
      event.test.error = truncate(redact(event.test.error), MAX_ERROR_CHARS);
    }
    const message = event.payload?.message;
    if (typeof message === "string") {
      event.payload = { ...event.payload, message: truncate(redact(message), MAX_LOG_CHARS) };
    }
    this.queue.push(event);
    if (this.queue.length > MAX_QUEUE) this.shed();
    if (this.queue.length >= FLUSH_AT) void this.flush();
  }

  /** *Which* events get lost matters. Test results are the record of what
   * happened and there are at most a few thousand; log lines are colour
   * commentary and there can be a hundred thousand. So shed logs first, and
   * only touch results if the queue is still over the ceiling afterwards. */
  private shed(): void {
    this.queue = this.queue.filter((e) => e.event_type !== "test.log");
    if (this.queue.length > MAX_QUEUE) {
      this.queue.splice(0, this.queue.length - MAX_QUEUE);
    }
    if (!this.warnedDropping) {
      this.warnedDropping = true;
      warn(
        "backend unreachable for a while - dropping buffered log lines to keep memory bounded. " +
          "Test results are kept. The run itself is unaffected."
      );
    }
  }

  async flush(force = false): Promise<void> {
    if (!this.active || this.queue.length === 0) return;
    if (this.flushing) return;
    // Exponential backoff after repeated failures, so a backend that is down
    // (or restarting mid-run) is retried at a decreasing rate instead of
    // being hammered once a second for the length of a 40-minute suite.
    if (!force && this.skipTicks > 0) {
      this.skipTicks -= 1;
      return;
    }
    this.flushing = true;
    const events = this.queue.splice(0, this.queue.length);
    try {
      const res = await this.request(`/live/runs/${this.runId}/events`, {
        method: "POST",
        headers: this.jsonHeaders(),
        body: JSON.stringify({ events }),
      });
      if (res.status === 404) {
        // The run was swept, or this is a different backend than the one we
        // started against. Retrying forever would burn the rest of the suite
        // posting into a void.
        this.disabled = true;
        warn("run no longer exists on the server - reporting stopped for the rest of this run.");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.consecutiveFailures = 0;
      this.skipTicks = 0;
    } catch (err) {
      this.queue.unshift(...events);
      if (this.queue.length > MAX_QUEUE) this.shed();
      this.consecutiveFailures += 1;
      this.skipTicks = Math.min(2 ** this.consecutiveFailures, 30);
      if (this.consecutiveFailures === 1) {
        warn(`event delivery failed, retrying in the background: ${(err as Error).message}`);
      }
    } finally {
      this.flushing = false;
    }
  }

  // -- attachments and frames -------------------------------------------

  uploadAttachment(testId: string, kind: string, filePath: string): void {
    if (!this.active) return;
    this.inflight.push(this.doUpload(testId, kind, filePath));
  }

  private async doUpload(testId: string, kind: string, filePath: string): Promise<void> {
    try {
      const size = statSync(filePath).size;
      if (size > MAX_ATTACHMENT_BYTES) {
        debug(this.config, `skipping ${basename(filePath)} (${Math.round(size / 1e6)}MB, over limit)`);
        return;
      }
      const body = new FormData();
      body.append("file", new Blob([readFileSync(filePath)]), basename(filePath));
      const query = `?test_id=${encodeURIComponent(testId)}&kind=${encodeURIComponent(kind)}`;
      await this.request(
        `/live/runs/${this.runId}/attachments${query}`,
        { method: "POST", headers: { "x-api-key": this.config.apiKey }, body },
        UPLOAD_TIMEOUT_MS
      );
    } catch (err) {
      debug(this.config, `attachment upload failed: ${(err as Error).message}`);
    }
  }

  async postFrame(workerId: number, frame: string): Promise<void> {
    if (!this.active) return;
    try {
      await this.request(
        `/live/runs/${this.runId}/live-frame`,
        {
          method: "POST",
          headers: this.jsonHeaders(),
          body: JSON.stringify({ worker_id: workerId, frame }),
        },
        5_000
      );
    } catch {
      // A dropped frame is invisible a second later. Never worth a word.
    }
  }

  // -- plumbing ----------------------------------------------------------

  private jsonHeaders(): Record<string, string> {
    return { "content-type": "application/json", "x-api-key": this.config.apiKey };
  }

  private request(
    path: string,
    init: RequestInit,
    timeoutMs = REQUEST_TIMEOUT_MS
  ): Promise<Response> {
    return fetch(`${this.config.url}${path}`, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
    });
  }
}

export function warn(message: string): void {
  // eslint-disable-next-line no-console
  console.warn(`[sentinel] ${message}`);
}

export function info(message: string): void {
  // eslint-disable-next-line no-console
  console.log(`[sentinel] ${message}`);
}

export function debug(config: { debug: boolean }, message: string): void {
  if (config.debug) info(message);
}

/** A failed handshake is where nearly every "why is Live Runs empty?" ends
 * up, and the status code identifies the cause exactly - so say the cause,
 * not the code. The failure is otherwise completely silent: the suite runs
 * and passes precisely as it would have. */
export function explainFailure(status: number, url: string, hasKey: boolean): string {
  if (status === 401 || status === 403) {
    return hasKey
      ? `${status} from ${url} - SENTINEL_API_KEY does not match this backend's ingest key. An admin can copy the current one from Live Runs > Connect a repo.`
      : `${status} from ${url} - this backend requires an ingest key and SENTINEL_API_KEY is not set. An admin can copy it from Live Runs > Connect a repo.`;
  }
  if (status === 404) {
    return `404 from ${url}/live/runs - something is listening, but it is not a Sentinel API. SENTINEL_URL must be the backend origin, with no trailing path.`;
  }
  if (status === 413) {
    return `413 from ${url} - the server rejected the payload as too large.`;
  }
  if (status >= 500) {
    return `${status} from ${url} - the Sentinel backend returned a server error.`;
  }
  return `run creation failed (${status}) at ${url}`;
}

/** Node's fetch collapses every connection-level failure into the same
 * opaque "fetch failed", which reads like a bug in this package rather than
 * what it nearly always is: nothing is listening at that URL. */
export function describeNetworkError(err: unknown, url: string): string {
  const message = (err as Error)?.message ?? String(err);
  if (message === "fetch failed" || message.includes("ECONNREFUSED")) {
    return `could not reach ${url} - check SENTINEL_URL and that the backend is running.`;
  }
  if ((err as Error)?.name === "TimeoutError" || message.includes("aborted")) {
    return `${url} did not respond in time - check the URL and any proxy in between.`;
  }
  if (message.includes("certificate") || message.includes("SELF_SIGNED")) {
    return `TLS handshake with ${url} failed. For an internally hosted install with a private CA, point NODE_EXTRA_CA_CERTS at your CA bundle.`;
  }
  return message;
}
