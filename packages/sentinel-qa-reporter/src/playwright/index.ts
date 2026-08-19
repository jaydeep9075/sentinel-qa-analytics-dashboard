import type {
  Reporter,
  FullConfig,
  Suite,
  TestCase,
  TestResult,
  FullResult,
  TestStep,
} from "@playwright/test/reporter";
import { SentinelClient, info, warn } from "../core/client";
import { resolveConfig } from "../core/config";
import { detectCi } from "../core/ci";
import type { SentinelOptions, TestStatus } from "../core/types";
import { LiveViewWatcher } from "./liveView";

export interface SentinelPlaywrightOptions extends SentinelOptions {
  /** Base CDP port for the live browser view; each worker uses
   * liveViewPort + the parallel slot index. Must match what withSentinel injected
   * launchOptions.args. Default 9222. */
  liveViewPort?: number;
  /** Screenshot poll interval in ms. Default 1000 (~1fps). */
  liveViewIntervalMs?: number;
  /** Worker count above which the poll interval stretches in proportion, so
   * total frames/sec across a wide CI matrix stays roughly flat instead of
   * climbing with every worker added. Default 3. */
  liveViewMaxFullRateWorkers?: number;
}

function testId(test: TestCase): string {
  return test.titlePath().join(" > ");
}

/** A run called "run_a1b2c3" tells you nothing at a glance, so derive
 * something readable from the spec files actually being run. */
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

/** Which parallel slot a test ran in.
 *
 * NOT the same as `workerIndex`, and the difference is the whole reason live
 * view used to fail on any run with more than one worker. `workerIndex`
 * counts every worker process ever started and keeps climbing when Playwright
 * recycles one; `parallelIndex` is the slot number, always 0..workers-1, and
 * it is what Playwright exports to the config as TEST_PARALLEL_INDEX - which
 * is what withSentinel used to compute each browser's debugging port. Keying
 * the watcher off workerIndex therefore pointed it at a port nothing was
 * listening on as soon as the two diverged. It also kept the frame tiles
 * bounded by the worker count instead of growing all run.
 */
function slotOf(result: TestResult): number {
  const parallel = (result as TestResult & { parallelIndex?: number }).parallelIndex;
  return typeof parallel === "number" ? parallel : result.workerIndex;
}

/** Playwright reports the losing attempt of a test that will be retried as
 * failed/timedOut. Recording that as "failed" makes the dashboard show a red
 * count that later vanishes when the retry passes, which is worse than
 * useless to someone watching. "retried" is a distinct state the UI shows in
 * amber, and the final attempt overwrites it either way. */
function mapStatus(test: TestCase, result: TestResult): TestStatus {
  if (result.status === "passed") return "passed";
  if (result.status === "skipped") return "skipped";
  if (result.retry < test.retries) return "retried";
  // failed, timedOut and interrupted all mean the same thing to a reader.
  return "failed";
}

/**
 * Streams a Playwright run to a Sentinel backend while it happens.
 *
 * Wire it with `withSentinel()` from `sentinel-qa-reporter/playwright/config`
 * rather than by hand - see that file for why the launch-args part is not
 * something to reproduce from memory.
 */
export default class SentinelPlaywrightReporter implements Reporter {
  private readonly options: SentinelPlaywrightOptions;
  private readonly client: SentinelClient;
  private readonly watchers = new Map<number, LiveViewWatcher>();
  private workerCount = 1;
  private started = false;

  constructor(options: SentinelPlaywrightOptions = {}) {
    this.options = options;
    this.client = new SentinelClient(resolveConfig(options));
  }

  async onBegin(config: FullConfig, suite: Suite): Promise<void> {
    this.workerCount = config.workers || 1;
    // `playwright test --list` runs the full reporter lifecycle, so without
    // this a listing POSTs a run that never executes a test and never gets
    // finalized - i.e. it manufactures exactly the abandoned rows the
    // backend then has to sweep. Listing is a read-only question about the
    // suite; it should leave no trace on the dashboard.
    if (process.argv.includes("--list")) return;

    const result = await this.client.start({
      framework: "playwright",
      name: deriveRunName(suite),
      total_tests: suite.allTests().length,
      worker_count: config.workers,
      project_id: this.client.config.projectId,
      environment: this.client.config.environment,
      ...detectCi(),
    });

    if (!result.ok) {
      if (this.client.config.enabled) {
        warn(`live reporting is off for this run: ${result.reason} The tests are unaffected.`);
      }
      return;
    }
    this.started = true;
    info(`watch this run: ${result.watchUrl}`);
  }

  onTestBegin(test: TestCase, result: TestResult): void {
    this.client.emit({
      event_type: "test.started",
      ts: new Date().toISOString(),
      worker_id: slotOf(result),
      test: {
        id: testId(test),
        title: test.title,
        file: test.location.file,
        status: "running",
        retry: result.retry,
      },
    });
    this.ensureLiveView(slotOf(result));
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

  onTestEnd(test: TestCase, result: TestResult): void {
    this.client.emit({
      event_type: "test.finished",
      ts: new Date().toISOString(),
      worker_id: slotOf(result),
      test: {
        id: testId(test),
        title: test.title,
        file: test.location.file,
        status: mapStatus(test, result),
        duration_ms: result.duration,
        retry: result.retry,
        error: result.error?.message ?? null,
      },
    });

    for (const attachment of result.attachments) {
      if (!attachment.path) continue;
      this.client.uploadAttachment(testId(test), attachment.name, attachment.path);
    }
  }

  async onEnd(result: FullResult): Promise<void> {
    for (const watcher of this.watchers.values()) watcher.stop();
    if (!this.started) return;
    // Ctrl-C and a global-timeout abort both land here as 'interrupted'.
    // Recording that as 'failed' would blame the suite for something the
    // operator did; 'cancelled' is a distinct outcome the dashboard shows
    // as such, and it still finalizes the run instead of leaving a row for
    // the stale sweeper to clean up minutes later.
    const status =
      result.status === "passed" ? "passed" : result.status === "interrupted" ? "cancelled" : "failed";
    await this.client.finish(status);
  }

  // -- live view ---------------------------------------------------------

  /** One watcher per worker, started lazily on that worker's first test and
   * left running for the rest of the suite - cheaper than reconnecting CDP
   * every test, and the poller already tolerates the page changing under it. */
  private ensureLiveView(slot: number): void {
    if (!this.client.config.liveView || !this.client.active) return;
    if (this.watchers.has(slot)) return;
    const port = (this.options.liveViewPort ?? 9222) + slot;
    const watcher = new LiveViewWatcher(port, this.liveViewIntervalMs(), (frame) =>
      void this.client.postFrame(slot, frame)
    );
    this.watchers.set(slot, watcher);
    void watcher.start();
  }

  /** Every worker posts frames independently, so unthrottled load scales
   * linearly with worker count - unbounded on a wide CI matrix. Below the
   * threshold nothing changes; past it the interval stretches in proportion
   * so aggregate frames/sec stays roughly flat. */
  private liveViewIntervalMs(): number {
    const base = this.options.liveViewIntervalMs ?? 1000;
    const fullRate = this.options.liveViewMaxFullRateWorkers ?? 3;
    if (this.workerCount <= fullRate) return base;
    return Math.round(base * (this.workerCount / fullRate));
  }

  private logLine(test: TestCase | undefined, level: string, message: string): void {
    if (!test || !message.trim()) return;
    this.client.emit({
      event_type: "test.log",
      ts: new Date().toISOString(),
      test: { id: testId(test), title: test.title },
      payload: { level, message: message.trim() },
    });
  }
}

export { withSentinel } from "./config";
export type { WithSentinelOptions } from "./config";
