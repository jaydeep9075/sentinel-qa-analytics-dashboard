/**
 * One-call wiring for a Playwright repo.
 *
 * Wiring this by hand means getting three separate things right in
 * playwright.config.ts: appending (not replacing) the reporter, adding a
 * `--remote-debugging-port` launch arg, and offsetting that port per worker.
 * Each has a silent failure mode - the run completes normally and simply
 * never shows up, or shows up with no browser view - which is a miserable
 * thing to debug in a repo you did not write.
 *
 * The worst of the three is not obvious even to people who know Playwright
 * well: a project-level `use.launchOptions` REPLACES the config-level one
 * rather than merging with it. Any repo whose projects set their own
 * `launchOptions.args` - which is most real repos: sandbox flags, window
 * size, slowMo - silently drops a top-level CDP flag, so live view never
 * connects and the only symptom is a warning buried in the test output.
 * withSentinel walks the project list and injects the flag into each one.
 */

import type { PlaywrightTestConfig } from "@playwright/test";
import { resolveConfig } from "../core/config";
import type { SentinelPlaywrightOptions } from "./index";

export interface WithSentinelOptions extends SentinelPlaywrightOptions {}

/** Playwright accepts a bare module name, a [name, options] tuple, or an
 * array of either. Normalize to the array form so we append rather than
 * clobber whatever the repo already had. */
type ReporterEntry = NonNullable<PlaywrightTestConfig["reporter"]>;

function asReporterList(reporter: ReporterEntry | undefined): unknown[] {
  if (!reporter) return [["list"]];
  if (typeof reporter === "string") return [[reporter]];
  // Already a list of entries, or a single [name, opts] tuple. A tuple's
  // first element is a string; a list's first element is itself an entry.
  if (Array.isArray(reporter) && typeof reporter[0] === "string") return [reporter];
  return [...(reporter as unknown[])];
}

/** WebKit and Firefox have no CDP endpoint; handing them a Chromium flag is
 * an immediate launch error, not a no-op. Anything not explicitly one of
 * those is treated as Chromium (Playwright's own default). */
function isChromium(use: Record<string, any> | undefined): boolean {
  const name = use?.browserName;
  return name !== "webkit" && name !== "firefox";
}

function withCdpArg(use: Record<string, any> | undefined, port: number): Record<string, any> {
  const existing = use?.launchOptions?.args ?? [];
  // Respect a port the repo already set for its own reasons rather than
  // adding a second, conflicting flag.
  if (existing.some((a: string) => a.startsWith("--remote-debugging-port"))) {
    return use ?? {};
  }
  return {
    ...(use ?? {}),
    launchOptions: {
      ...(use?.launchOptions ?? {}),
      args: [...existing, `--remote-debugging-port=${port}`],
    },
  };
}

/**
 * Returns the config with Sentinel's reporter and (when live view is on) its
 * launch flags merged in, leaving everything else untouched:
 *
 * ```ts
 * export default defineConfig(withSentinel({ ...your config }));
 * ```
 *
 * A no-op unless SENTINEL_URL is set, so the call is safe to commit: a plain
 * `npx playwright test` with no Sentinel environment behaves exactly as it
 * did before, and so does every pipeline that has not opted in.
 */
export function withSentinel<T extends PlaywrightTestConfig>(
  config: T,
  options: WithSentinelOptions = {}
): T {
  const resolved = resolveConfig(options);
  if (!resolved.enabled) return config;

  const basePort = options.liveViewPort ?? 9222;
  // playwright.config.ts is evaluated once per worker process, and
  // TEST_PARALLEL_INDEX is that worker's index - so each worker computes its
  // own port, matching the reporter's liveViewPort + workerIndex.
  const port = basePort + Number(process.env.TEST_PARALLEL_INDEX || 0);

  const reporter = [
    ...asReporterList(config.reporter),
    ["sentinel-qa-reporter/playwright", { ...options, liveViewPort: basePort }],
  ] as ReporterEntry;

  if (!resolved.liveView) return { ...config, reporter };

  return {
    ...config,
    reporter,
    use: isChromium(config.use) ? withCdpArg(config.use, port) : config.use,
    projects: config.projects?.map((project) =>
      isChromium(project.use) ? { ...project, use: withCdpArg(project.use, port) } : project
    ),
  };
}
