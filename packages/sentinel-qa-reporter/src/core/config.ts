import type { SentinelOptions } from "./types";

export interface ResolvedConfig {
  enabled: boolean;
  url: string;
  dashboardUrl: string;
  apiKey: string;
  projectId?: string;
  environment?: string;
  runKey?: string;
  liveView: boolean;
  debug: boolean;
}

function envFlag(value: string | undefined): boolean | undefined {
  if (value === undefined || value === "") return undefined;
  return !["0", "false", "off", "no"].includes(value.toLowerCase());
}

/** True on every CI provider this package knows about, plus the generic
 * `CI` var that nearly all of them set. */
export function isCi(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(
    env.CI ||
      env.GITHUB_ACTIONS ||
      env.JENKINS_URL ||
      env.TF_BUILD ||
      env.BITBUCKET_BUILD_NUMBER ||
      env.GITLAB_CI ||
      env.CIRCLECI
  );
}

/**
 * Options first, then environment, then a default. There is exactly one
 * variable that decides whether anything happens at all - SENTINEL_URL - so
 * a repo can commit its Sentinel wiring permanently and every pipeline that
 * has not opted in behaves precisely as it did before.
 */
export function resolveConfig(
  options: SentinelOptions = {},
  env: NodeJS.ProcessEnv = process.env
): ResolvedConfig {
  const url = (options.url || env.SENTINEL_URL || env.SENTINEL_BASE_URL || "").replace(/\/+$/, "");
  const enabled = options.enabled ?? Boolean(url);

  return {
    enabled,
    url: url || "http://localhost:8000",
    // Where a human goes to watch is not necessarily where events are
    // posted: hosted behind one domain they are the same origin, but in
    // local dev the API is :8000 and the dashboard :3000, so printing the
    // API origin hands out a link to a port that serves no such page.
    dashboardUrl: (
      options.dashboardUrl ||
      env.SENTINEL_DASHBOARD_URL ||
      url ||
      "http://localhost:8000"
    ).replace(/\/+$/, ""),
    apiKey: options.apiKey || env.SENTINEL_API_KEY || "",
    projectId: options.projectId || env.SENTINEL_PROJECT || undefined,
    environment: options.environment || env.SENTINEL_ENV || undefined,
    runKey: options.runKey || env.SENTINEL_RUN_KEY || undefined,
    // Screenshots of the app under test are the one thing this package
    // sends that could carry customer data, and on CI nobody is watching
    // them anyway - the run is reviewed after it finishes. So: on by
    // default where someone is actually looking at a browser, off by
    // default where they are not, overridable either way.
    liveView: options.liveView ?? envFlag(env.SENTINEL_LIVE_VIEW) ?? !isCi(env),
    debug: options.debug ?? envFlag(env.SENTINEL_DEBUG) ?? false,
  };
}
