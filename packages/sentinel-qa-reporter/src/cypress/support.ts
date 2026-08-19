/**
 * Cypress adapter - the browser half.
 *
 * Individual test results only exist in the browser, so this is where they
 * are observed; the events are handed to the node half over `cy.task` (see
 * ./index.ts for why the bridge is gated from that side).
 *
 * Import it once from cypress/support/e2e.{js,ts}:
 *
 * ```ts
 * import { registerSentinelSupport } from "sentinel-qa-reporter/cypress/support";
 * registerSentinelSupport();
 * ```
 */

import { SENTINEL_ENV_FLAG, SENTINEL_TASK } from "./constants";
import type { SentinelEvent, TestStatus } from "../core/types";

// Declared rather than imported so this file compiles without the `cypress`
// types package, which is an optional peer dependency.
declare const Cypress: any;
declare const cy: any;
declare const beforeEach: (fn: (this: any) => void) => void;
declare const afterEach: (fn: (this: any) => void) => void;

export interface SentinelSupportOptions {
  /** Forward explicit `cy.log()` calls to the live log. Default true.
   * Only `cy.log` is captured, never the full Cypress command log - that
   * runs to thousands of entries per test and is noise on a live view. */
  captureLogs?: boolean;
}

export function registerSentinelSupport(options: SentinelSupportOptions = {}): void {
  // The node half sets this. Its absence means Sentinel is not configured
  // for this run, and the task handler does not exist - so calling it would
  // fail the test. Staying inert is the entire safety property here.
  if (typeof Cypress === "undefined" || !Cypress.env(SENTINEL_ENV_FLAG)) return;

  const captureLogs = options.captureLogs ?? true;
  let queue: SentinelEvent[] = [];

  if (captureLogs) {
    Cypress.on("log:added", (attrs: any) => {
      if (attrs?.name !== "log" || !attrs?.message) return;
      const test = Cypress.currentTest;
      queue.push({
        event_type: "test.log",
        ts: new Date().toISOString(),
        test: { id: idOf(test), title: test?.title ?? "" },
        payload: { level: "log", message: String(attrs.message) },
      });
    });
  }

  beforeEach(function (this: any) {
    const test = this.currentTest;
    if (!test) return;
    queue.push({
      event_type: "test.started",
      ts: new Date().toISOString(),
      test: {
        id: idOf(test),
        title: test.title,
        file: Cypress.spec?.relative,
        status: "running",
        retry: currentRetry(test),
      },
    });
    flush();
  });

  afterEach(function (this: any) {
    const test = this.currentTest;
    if (!test) return;
    queue.push({
      event_type: "test.finished",
      ts: new Date().toISOString(),
      test: {
        id: idOf(test),
        title: test.title,
        file: Cypress.spec?.relative,
        status: statusOf(test),
        duration_ms: test.duration ?? undefined,
        retry: currentRetry(test),
        error: test.err?.message ?? null,
      },
    });
    flush();
  });

  /** cy.task is a queued Cypress command, so this schedules the send rather
   * than performing it - which is what we want: it lands in order with the
   * rest of the test's commands and cannot race them. `log: false` keeps
   * reporting out of the command log the user is reading. */
  function flush(): void {
    if (queue.length === 0) return;
    const batch = queue;
    queue = [];
    cy.task(SENTINEL_TASK, batch, { log: false });
  }
}

function idOf(test: any): string {
  if (!test) return "unknown";
  if (typeof test.titlePath === "function") return test.titlePath().join(" > ");
  if (Array.isArray(test.titlePath)) return test.titlePath.join(" > ");
  return typeof test.fullTitle === "function" ? test.fullTitle() : String(test.title ?? "unknown");
}

function currentRetry(test: any): number {
  return typeof test?._currentRetry === "number" ? test._currentRetry : 0;
}

/** Mocha's states, mapped onto the shared contract. A failed attempt that
 * still has retries left is reported as "retried" rather than "failed", so a
 * live viewer does not see a red count that later disappears. */
function statusOf(test: any): TestStatus {
  const state = test?.state;
  if (state === "passed") return "passed";
  if (state === "pending" || !state) return "skipped";
  const retries = typeof test.retries === "function" ? test.retries() : -1;
  if (retries > 0 && currentRetry(test) < retries) return "retried";
  return "failed";
}
