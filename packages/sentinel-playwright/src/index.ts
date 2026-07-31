import type {
  Reporter,
  FullConfig,
  Suite,
  TestCase,
  TestResult,
  FullResult,
  TestStep,
} from "@playwright/test/reporter";
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import { LiveViewWatcher } from "./liveView";

export interface SentinelReporterOptions {
  /** Defaults to SENTINEL_BASE_URL, then http://localhost:8000 */
  baseUrl?: string;
  /** Defaults to SENTINEL_API_KEY. Must match services LIVE_INGEST_API_KEY. */
  apiKey?: string;
  projectId?: string;
  workspaceId?: string;
  environment?: string;
  /**
   * Opt-in live browser view (~1 screenshot/sec while a test runs). Requires
   * the browser to actually be launched with a remote-debugging port - add
   * `--remote-debugging-port=9222` (or liveViewPort) to your Chromium
   * launchOptions.args. Off by default: it costs real CPU/bandwidth, so it
   * should only be on when someone's actually going to watch.
   */
  liveView?: boolean;
  /** Base CDP port; each worker uses liveViewPort + workerIndex. Default 9222. */
  liveViewPort?: number;
  /** How often to grab a frame, in ms, for a run at or below liveViewMaxFullRateWorkers. Default 1000 (~1fps). */
  liveViewIntervalMs?: number;
  /**
   * Worker count under which live view runs at the full liveViewIntervalMs
   * rate. Each worker posts a frame independently, so total load on the
   * Sentinel backend scales with worker count - unbounded on a big CI
   * matrix. Above this threshold the interval stretches proportionally
   * (e.g. 2x the workers -> 2x the interval) so aggregate frames/sec across
   * the whole run stays roughly flat instead of climbing with every worker
   * added. Default 3.
   */
  liveViewMaxFullRateWorkers?: number;
}

interface SentinelEvent {
  event_type:
    | "test.started"
    | "test.finished"
    | "test.log";
  ts: string;
  worker_id?: number;
  test?: {
    id: string;
    title: string;
    file?: string;
    status?: string;
    duration_ms?: number;
    retry?: number;
    error?: string | null;
  };
  payload?: Record<string, unknown>;
}

interface CiMeta {
  ci_provider?: string;
  branch?: string;
  commit_sha?: string;
  build_url?: string;
}

function detectCi(): CiMeta {
  const env = process.env;
  if (env.GITHUB_ACTIONS) {
    const server = env.GITHUB_SERVER_URL || "https://github.com";
    return {
      ci_provider: "github-actions",
      branch: env.GITHUB_REF_NAME,
      commit_sha: env.GITHUB_SHA,
      build_url: env.GITHUB_RUN_ID
        ? `${server}/${env.GITHUB_REPOSITORY}/actions/runs/${env.GITHUB_RUN_ID}`
        : undefined,
    };
  }
  if (env.JENKINS_URL) {
    return {
      ci_provider: "jenkins",
      branch: env.GIT_BRANCH,
      commit_sha: env.GIT_COMMIT,
      build_url: env.BUILD_URL,
    };
  }
  if (env.TF_BUILD) {
    return {
      ci_provider: "azure-devops",
      branch: env.BUILD_SOURCEBRANCHNAME,
      commit_sha: env.BUILD_SOURCEVERSION,
      build_url: env.SYSTEM_TEAMFOUNDATIONCOLLECTIONURI,
    };
  }
  if (env.BITBUCKET_BUILD_NUMBER) {
    return {
      ci_provider: "bitbucket",
      branch: env.BITBUCKET_BRANCH,
      commit_sha: env.BITBUCKET_COMMIT,
    };
  }
  return {};
}

function testId(test: TestCase): string {
  return test.titlePath().join(" > ");
}

/** A run named "run_a1b2c3" tells you nothing at a glance. Derive something
 * readable from the actual spec file(s) being run instead - e.g. a single
 * file run becomes "AddToCart.spec.ts"; a multi-file run becomes
 * "AddToCart.spec.ts +2 more". Falls back to a generic label if Playwright
 * hasn't resolved any tests yet (e.g. an empty --grep match). */
function deriveRunName(suite: Suite): string {
  const files = new Set<string>();
  for (const test of suite.allTests()) {
    const file = test.location?.file;
    if (file) files.add(file.replace(/\\/g, "/").split("/").pop() as string);
  }
  const names = [...files];
  if (names.length === 0) return "playwright run";
  if (names.length === 1) return names[0];
  return `${names[0]} +${names.length - 1} more`;
}

/**
 * Streams Playwright run/test events to a Sentinel backend as they happen.
 * Never throws into the test run - a dead network just disables reporting
 * for that process (see LIVE_EXECUTION_ARCHITECTURE.md #11).
 */
export default class SentinelPlaywrightReporter implements Reporter {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly options: SentinelReporterOptions;
  private runId: string | null = null;
  private disabled = false;
  private pending: SentinelEvent[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private inflight: Promise<void>[] = [];
  private liveViewWatchers = new Map<number, LiveViewWatcher>();
  private droppedEventsWarned = false;
  /** Set from FullConfig.workers in onBegin; drives the live-view throttle
   * in ensureLiveView. Defaults to 1 so a watcher created before onBegin
   * somehow ran (shouldn't happen, but cheaper than a null check at every
   * call site) behaves like a single-worker run. */
  private workerCount = 1;

  /** If the backend is unreachable for a stretch (network blip, backend
   * restart, a long CI run outlasting some deploy), flush() keeps failing
   * and pending keeps growing every tick with no upper bound - for a long,
   * chatty suite that's a real memory leak in the test process itself, not
   * just a reporting gap. Past this many buffered events, drop the oldest
   * ones rather than let it grow forever; a dropped log line from an outage
   * that's already being retried is a much smaller problem than OOMing the
   * test runner. */
  private static readonly MAX_PENDING = 500;

  constructor(options: SentinelReporterOptions = {}) {
    this.options = options;
    this.baseUrl = (
      options.baseUrl ||
      process.env.SENTINEL_BASE_URL ||
      "http://localhost:8000"
    ).replace(/\/$/, "");
    this.apiKey = options.apiKey || process.env.SENTINEL_API_KEY || "";
  }

  async onBegin(config: FullConfig, suite: Suite): Promise<void> {
    this.workerCount = config.workers || 1;
    try {
      const res = await fetch(`${this.baseUrl}/live/runs`, {
        method: "POST",
        headers: this.jsonHeaders(),
        body: JSON.stringify({
          framework: "playwright",
          name: deriveRunName(suite),
          project_id: this.options.projectId,
          workspace_id: this.options.workspaceId,
          environment: this.options.environment,
          worker_count: config.workers,
          ...detectCi(),
        }),
      });
      if (!res.ok) {
        throw new Error(`Sentinel run creation failed (${res.status})`);
      }
      const data = (await res.json()) as { run_id: string };
      this.runId = data.run_id;
      // eslint-disable-next-line no-console
      console.log(
        `[sentinel] live run started: ${this.baseUrl}/runs/${this.runId}/live`
      );
      this.flushTimer = setInterval(() => void this.flush(), 1000);
    } catch (err) {
      this.disabled = true;
      // eslint-disable-next-line no-console
      console.warn(
        `[sentinel] live reporting disabled for this run: ${(err as Error).message}`
      );
    }
  }

  onTestBegin(test: TestCase, result: TestResult): void {
    this.emit({
      event_type: "test.started",
      ts: new Date().toISOString(),
      worker_id: result.workerIndex,
      test: {
        id: testId(test),
        title: test.title,
        file: test.location.file,
        status: "running",
        retry: result.retry,
      },
    });
    this.ensureLiveView(result.workerIndex);
  }

  /** One watcher per worker, started lazily on that worker's first test and
   * left running for the rest of the suite (cheaper than reconnecting CDP
   * every single test, and the poller already tolerates the page changing
   * underneath it between tests). */
  private ensureLiveView(workerIndex: number): void {
    if (!this.options.liveView || this.disabled || !this.runId) return;
    if (this.liveViewWatchers.has(workerIndex)) return;
    const port = (this.options.liveViewPort ?? 9222) + workerIndex;
    const watcher = new LiveViewWatcher(
      port,
      this.effectiveLiveViewIntervalMs(),
      (frame) => void this.postFrame(workerIndex, frame)
    );
    this.liveViewWatchers.set(workerIndex, watcher);
    void watcher.start();
  }

  /** Every worker posts frames independently, so unthrottled load on the
   * backend scales linearly with worker count. Below liveViewMaxFullRateWorkers
   * nothing changes (full 1fps, matches today's behavior for local/small
   * runs); past it, the interval stretches in proportion to worker count so
   * aggregate frames/sec across the run stays roughly flat instead of
   * growing with every worker a CI matrix adds. */
  private effectiveLiveViewIntervalMs(): number {
    const baseIntervalMs = this.options.liveViewIntervalMs ?? 1000;
    const fullRateWorkers = this.options.liveViewMaxFullRateWorkers ?? 3;
    if (this.workerCount <= fullRateWorkers) return baseIntervalMs;
    return Math.round(baseIntervalMs * (this.workerCount / fullRateWorkers));
  }

  private async postFrame(workerIndex: number, frame: string): Promise<void> {
    if (this.disabled || !this.runId) return;
    try {
      await fetch(`${this.baseUrl}/live/runs/${this.runId}/live-frame`, {
        method: "POST",
        headers: this.jsonHeaders(),
        body: JSON.stringify({ worker_id: workerIndex, frame }),
      });
    } catch {
      // A dropped frame is invisible to anyone watching a second later -
      // not worth logging, let alone worth affecting the test run.
    }
  }

  onStdOut(chunk: string | Buffer, test?: TestCase): void {
    this.logLine(test, "stdout", chunk.toString());
  }

  onStdErr(chunk: string | Buffer, test?: TestCase): void {
    this.logLine(test, "stderr", chunk.toString());
  }

  onStepEnd(test: TestCase, _result: TestResult, step: TestStep): void {
    if (step.category !== "test.step") return;
    this.logLine(test, "step", `${step.title} (${Math.round(step.duration)}ms)`);
  }

  async onTestEnd(test: TestCase, result: TestResult): Promise<void> {
    const status = result.status === "timedOut" ? "failed" : result.status;
    this.emit({
      event_type: "test.finished",
      ts: new Date().toISOString(),
      worker_id: result.workerIndex,
      test: {
        id: testId(test),
        title: test.title,
        file: test.location.file,
        status,
        duration_ms: result.duration,
        retry: result.retry,
        error: result.error?.message ?? null,
      },
    });

    // Only-on-failure screenshots + traces and the final video are what
    // Playwright actually produces when configured that way (see
    // LIVE_EXECUTION_IMPLEMENTATION_PLAN.md "Artifacts policy") - the
    // reporter just uploads whatever attachments exist, no filtering here.
    for (const attachment of result.attachments) {
      if (!attachment.path) continue;
      this.inflight.push(this.uploadAttachment(test, attachment));
    }
  }

  async onEnd(result: FullResult): Promise<void> {
    if (this.flushTimer) clearInterval(this.flushTimer);
    for (const watcher of this.liveViewWatchers.values()) watcher.stop();
    await this.flush();
    await Promise.allSettled(this.inflight);
    if (this.disabled || !this.runId) return;
    try {
      await fetch(`${this.baseUrl}/live/runs/${this.runId}`, {
        method: "PATCH",
        headers: this.jsonHeaders(),
        body: JSON.stringify({
          status: result.status === "passed" ? "passed" : "failed",
        }),
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn(
        `[sentinel] failed to finalize run status: ${(err as Error).message}`
      );
    }
  }

  private logLine(test: TestCase | undefined, level: string, message: string): void {
    if (!test || !message.trim()) return;
    this.emit({
      event_type: "test.log",
      ts: new Date().toISOString(),
      test: { id: testId(test), title: test.title },
      payload: { level, message: message.trim() },
    });
  }

  private async uploadAttachment(
    test: TestCase,
    attachment: { name: string; path?: string; contentType: string }
  ): Promise<void> {
    if (this.disabled || !this.runId || !attachment.path) return;
    try {
      const fileBuffer = readFileSync(attachment.path);
      const form = new FormData();
      const id = testId(test);
      form.append("file", new Blob([fileBuffer]), basename(attachment.path));
      const url =
        `${this.baseUrl}/live/runs/${this.runId}/attachments` +
        `?test_id=${encodeURIComponent(id)}&kind=${encodeURIComponent(attachment.name)}`;
      await fetch(url, {
        method: "POST",
        headers: { "x-api-key": this.apiKey },
        body: form,
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn(`[sentinel] attachment upload failed: ${(err as Error).message}`);
    }
  }

  private jsonHeaders(): Record<string, string> {
    return { "content-type": "application/json", "x-api-key": this.apiKey };
  }

  private emit(event: SentinelEvent): void {
    if (this.disabled) return;
    this.pending.push(event);
    if (this.pending.length > SentinelPlaywrightReporter.MAX_PENDING) {
      this.pending.splice(0, this.pending.length - SentinelPlaywrightReporter.MAX_PENDING);
      if (!this.droppedEventsWarned) {
        this.droppedEventsWarned = true;
        // eslint-disable-next-line no-console
        console.warn(
          `[sentinel] backend unreachable for a while - dropping oldest buffered events past ${SentinelPlaywrightReporter.MAX_PENDING} to avoid unbounded memory growth. The test run itself is unaffected.`
        );
      }
    }
    if (this.pending.length >= 20) void this.flush();
  }

  private async flush(): Promise<void> {
    if (this.disabled || !this.runId || this.pending.length === 0) return;
    const events = this.pending.splice(0, this.pending.length);
    try {
      await fetch(`${this.baseUrl}/live/runs/${this.runId}/events`, {
        method: "POST",
        headers: this.jsonHeaders(),
        body: JSON.stringify({ events }),
      });
    } catch (err) {
      // Never fail the test run over a reporting hiccup - put the events
      // back and let the next tick retry them.
      this.pending.unshift(...events);
      // eslint-disable-next-line no-console
      console.warn(`[sentinel] event flush failed, will retry: ${(err as Error).message}`);
    }
  }
}
