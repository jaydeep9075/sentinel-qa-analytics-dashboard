/**
 * Optional live-browser view: polls a screenshot from the browser Playwright
 * already launched, over Chrome's own remote-debugging protocol (CDP) - no
 * changes needed to the consuming repo's fixtures/page objects, only one
 * launch flag (`--remote-debugging-port=<port>`) in its playwright.config.ts.
 *
 * Deliberately polling (Page.captureScreenshot on a timer) rather than
 * event-driven Page.startScreencast: no frame-ack protocol to get wrong,
 * trivially resumable if a page navigates/closes mid-test, and ~1 frame/sec
 * is exactly what "watch what's happening" needs - this was never meant to
 * be video.
 */

const DISCOVERY_TIMEOUT_MS = 2000;
// A refused connection (nothing listening yet) fails near-instantly, so the
// real wait per attempt is ~DISCOVERY_RETRY_DELAY_MS, not DISCOVERY_TIMEOUT_MS
// - 6 retries at 500ms only covers ~2.5s of actual cold-start time. A real
// `channel: "chrome"` launch (vs. bundled Chromium) competing with sibling
// workers for CPU on `--workers > 1` can easily take longer than that before
// its CDP port is up, which silently disabled live view on some/all workers
// even though the browser (and its debugging port) came up fine a moment
// later - the watcher had already given up by then. 20x600ms covers ~12s.
const DISCOVERY_RETRIES = 20;
const DISCOVERY_RETRY_DELAY_MS = 600;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface CdpTarget {
  type: string;
  webSocketDebuggerUrl: string;
}

export class LiveViewWatcher {
  private ws: WebSocket | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private msgId = 1;
  private pending = new Map<number, (result: unknown) => void>();
  private stopped = false;
  private reconnecting = false;
  private currentTargetUrl: string | null = null;

  constructor(
    private readonly port: number,
    private readonly intervalMs: number,
    private readonly onFrame: (jpegBase64: string) => void
  ) {}

  /** Never throws into the test run - a live view that can't connect just
   * stays off, exactly like every other reporting failure mode in this
   * package - but it does warn once, since a silently-not-working feature
   * is its own kind of bug report nobody can act on.
   *
   * Retries discovery a handful of times: this is normally called from
   * onTestBegin, which fires before the browser has necessarily finished
   * launching and opened its debugging port yet - a single immediate
   * attempt reliably loses that race on the first test of a run. */
  async start(): Promise<void> {
    let lastError: unknown = null;
    for (let attempt = 0; attempt < DISCOVERY_RETRIES; attempt++) {
      if (attempt > 0) await sleep(DISCOVERY_RETRY_DELAY_MS);
      try {
        const page = await this.discoverPageTarget();
        if (!page) continue; // CDP is up but no page yet - keep retrying
        await this.connect(page.webSocketDebuggerUrl);
        this.timer = setInterval(() => void this.tick(), this.intervalMs);
        // eslint-disable-next-line no-console
        console.log(`[sentinel] live view connected on port ${this.port}`);
        return;
      } catch (err) {
        lastError = err;
      }
    }
    // eslint-disable-next-line no-console
    console.warn(
      `[sentinel] live view disabled: could not reach CDP on port ${this.port} after ${DISCOVERY_RETRIES} attempts` +
        (lastError ? ` (${(lastError as Error).message})` : " (no page target appeared)") +
        `. Check the browser was launched with --remote-debugging-port=${this.port}.`
    );
  }

  /** Playwright gives each test a fresh page/context by default, so the page
   * this watcher originally connected to closes at the end of every test -
   * Chrome tears down that page's CDP socket along with it. Without this,
   * the watcher would go silent after test #1 forever (ws never OPEN again,
   * tick() has nothing to do). Called whenever a tick finds the connection
   * dead: re-run discovery and reconnect to whatever page is current now. */
  private async reconnect(): Promise<void> {
    if (this.stopped || this.reconnecting) return;
    this.reconnecting = true;
    try {
      const page = await this.discoverPageTarget();
      if (!page || page.webSocketDebuggerUrl === this.currentTargetUrl) return;
      await this.connect(page.webSocketDebuggerUrl);
    } catch {
      // Nothing to reconnect to yet (e.g. between tests, briefly no page) -
      // the next tick tries again.
    } finally {
      this.reconnecting = false;
    }
  }

  private async discoverPageTarget(): Promise<CdpTarget | undefined> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), DISCOVERY_TIMEOUT_MS);
    try {
      const res = await fetch(`http://127.0.0.1:${this.port}/json/list`, {
        signal: controller.signal,
      });
      const targets = (await res.json()) as CdpTarget[];
      return targets.find((t) => t.type === "page");
    } finally {
      clearTimeout(timeout);
    }
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    this.ws?.close();
  }

  private connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      socket.addEventListener("open", () => {
        this.currentTargetUrl = url;
        resolve();
      });
      socket.addEventListener("error", () => reject(new Error("CDP connection failed")));
      socket.addEventListener("close", () => {
        // The page this socket was watching just closed (e.g. test ended,
        // Playwright tore down its context) - drop it so the next tick
        // reconnects to whatever page is current instead of finding a dead
        // socket and doing nothing.
        if (this.ws === socket) {
          this.ws = null;
          this.currentTargetUrl = null;
        }
      });
      socket.addEventListener("message", (ev: MessageEvent) => {
        try {
          const msg = JSON.parse(ev.data.toString());
          if (msg.id && this.pending.has(msg.id)) {
            this.pending.get(msg.id)!(msg.result);
            this.pending.delete(msg.id);
          }
        } catch {
          // Malformed/unexpected CDP frame - ignore this one, keep polling.
        }
      });
      this.ws = socket;
    });
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    if (!this.ws || this.ws.readyState !== this.ws.OPEN) {
      void this.reconnect();
      return;
    }
    try {
      const result = (await this.send("Page.captureScreenshot", {
        format: "jpeg",
        quality: 40,
      })) as { data?: string } | undefined;
      if (result?.data) this.onFrame(result.data);
    } catch {
      // Page mid-navigation / closed for this tick - next tick tries again.
    }
  }

  private send(method: string, params: Record<string, unknown>): Promise<unknown> {
    const id = this.msgId++;
    return new Promise((resolve, reject) => {
      if (!this.ws) {
        reject(new Error("not connected"));
        return;
      }
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}
