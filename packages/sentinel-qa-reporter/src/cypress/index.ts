/**
 * Cypress adapter - the node half.
 *
 * Cypress splits into two worlds: `setupNodeEvents` runs in Node (can make
 * HTTP calls, knows about specs and artifacts) and the support file runs in
 * the browser (knows about individual tests as they happen, cannot make
 * arbitrary HTTP calls). Live per-test reporting needs both, so this package
 * ships both halves and bridges them over `cy.task`.
 *
 * The bridge is switched on from here, not from the browser: this file sets
 * a flag in `config.env`, and the support half stays completely inert unless
 * it sees that flag. So a repo where Sentinel is not configured never calls
 * `cy.task` at all, and cannot fail a test because a task handler is
 * missing.
 */

import { SentinelClient, info, warn } from "../core/client";
import { resolveConfig } from "../core/config";
import { detectCi } from "../core/ci";
import type { SentinelEvent, SentinelOptions } from "../core/types";
import { SENTINEL_ENV_FLAG, SENTINEL_TASK } from "./constants";

export { SENTINEL_ENV_FLAG, SENTINEL_TASK } from "./constants";

export interface SentinelCypressOptions extends SentinelOptions {}

/** The subset of Cypress's plugin API this adapter uses. Declared
 * structurally so the package does not need `cypress` installed to build,
 * which matters because it is an optional peer dependency - a Playwright-only
 * repo should not have to install Cypress to use this package. */
type PluginEvents = (event: string, handler: any) => void;

interface CypressConfig {
  env?: Record<string, unknown>;
  [key: string]: unknown;
}

interface SpecResults {
  video?: string | null;
  screenshots?: { path: string; testId?: string; name?: string }[];
  stats?: { failures?: number };
}

/**
 * Wire Sentinel into a Cypress config:
 *
 * ```ts
 * import { defineConfig } from "cypress";
 * import { registerSentinel } from "sentinel-qa-reporter/cypress";
 *
 * export default defineConfig({
 *   e2e: {
 *     setupNodeEvents(on, config) {
 *       return registerSentinel(on, config);
 *     },
 *   },
 * });
 * ```
 *
 * A no-op unless SENTINEL_URL is set, so it is safe to commit.
 */
export function registerSentinel<T extends CypressConfig>(
  on: PluginEvents,
  config: T,
  options: SentinelCypressOptions = {}
): T {
  const resolved = resolveConfig(options);
  if (!resolved.enabled) return config;

  const client = new SentinelClient(resolved);
  let finishing: Promise<void> | null = null;

  on("before:run", async (details: { specs?: { relative?: string }[] }) => {
    const specs = (details?.specs ?? []).map((s) => s.relative || "").filter(Boolean);
    const result = await client.start({
      framework: "cypress",
      name: describeSpecs(specs),
      project_id: resolved.projectId,
      environment: resolved.environment,
      ...detectCi(),
    });
    if (!result.ok) {
      warn(`live reporting is off for this run: ${result.reason} The tests are unaffected.`);
      return;
    }
    info(`watch this run: ${result.watchUrl}`);
  });

  // The browser half posts here. It must never throw: a task that rejects
  // fails the test that called it, which would mean reporting could break a
  // suite - the one thing this package promises not to do.
  on("task", {
    [SENTINEL_TASK]: (events: SentinelEvent[]) => {
      try {
        for (const event of events ?? []) client.emit(event);
      } catch {
        // Deliberately swallowed - see above.
      }
      return null;
    },
  });

  // Artifacts are only knowable in Node, and only once a spec has finished.
  on("after:spec", async (_spec: unknown, results: SpecResults) => {
    if (!client.active) return;
    for (const shot of results?.screenshots ?? []) {
      if (shot?.path) client.uploadAttachment(shot.testId || "", "screenshot", shot.path);
    }
    // Cypress records one video per spec, not per test, so it is attached to
    // the spec rather than to any single test. Only uploaded when the spec
    // had a failure - a green run's video is a large file nobody opens.
    if (results?.video && (results.stats?.failures ?? 0) > 0) {
      client.uploadAttachment("", "video", results.video);
    }
    await client.flush(true);
  });

  on("after:run", async (results: { totalFailed?: number } | undefined) => {
    finishing = client.finish(results?.totalFailed ? "failed" : "passed");
    await finishing;
  });

  // `after:run` does not fire when someone kills the run. Without this the
  // run sits in the list as permanently in-progress until the server's stale
  // sweeper clears it minutes later.
  const onSignal = () => {
    if (!finishing) void client.finish("cancelled");
  };
  process.once("SIGINT", onSignal);
  process.once("SIGTERM", onSignal);

  // The browser half reads this and stays inert if it is absent, so a repo
  // that has not configured Sentinel never calls cy.task at all.
  config.env = { ...(config.env ?? {}), [SENTINEL_ENV_FLAG]: true };
  return config;
}

function describeSpecs(specs: string[]): string {
  if (specs.length === 0) return "cypress run";
  const first = specs[0].split(/[\\/]/).pop() as string;
  return specs.length === 1 ? first : `${first} +${specs.length - 1} more`;
}
