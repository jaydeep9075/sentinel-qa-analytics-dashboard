/** The wire contract, shared by every framework adapter in this package.
 * It is deliberately small: four endpoints and one event shape. Anything a
 * framework can't produce is optional, so adding a new adapter never means
 * changing the backend. */

export type TestStatus = "running" | "passed" | "failed" | "skipped" | "retried";
export type RunStatus = "passed" | "failed" | "cancelled";

export interface SentinelTest {
  id: string;
  title: string;
  file?: string;
  status?: TestStatus;
  duration_ms?: number;
  retry?: number;
  error?: string | null;
}

export interface SentinelEvent {
  event_type: "test.started" | "test.finished" | "test.log";
  ts: string;
  worker_id?: number;
  test?: SentinelTest;
  payload?: Record<string, unknown>;
}

export interface RunMeta {
  framework: string;
  name?: string;
  total_tests?: number;
  worker_count?: number;
  project_id?: string;
  environment?: string;
  external_id?: string;
  ci_provider?: string;
  branch?: string;
  commit_sha?: string;
  build_url?: string;
  metadata?: Record<string, unknown>;
}

/** Options every adapter accepts. Each has an environment-variable
 * equivalent, because the whole point of the design is that a repo commits
 * the config once and switches Sentinel on and off with env alone. */
export interface SentinelOptions {
  /** Sentinel API origin. Env: SENTINEL_URL. Nothing reports without it. */
  url?: string;
  /** Shared ingest key. Env: SENTINEL_API_KEY. */
  apiKey?: string;
  /** Where a human watches, when the UI is on a different origin than the
   * API (local dev: :3000 vs :8000). Env: SENTINEL_DASHBOARD_URL. */
  dashboardUrl?: string;
  /** Free-text labels shown in the run list. Env: SENTINEL_PROJECT / SENTINEL_ENV. */
  projectId?: string;
  environment?: string;
  /** Joins several processes into one run - the sharded-CI case, where
   * `--shard=1/4` would otherwise produce four unrelated runs. Any stable
   * string works; the build id is the obvious one. Env: SENTINEL_RUN_KEY. */
  runKey?: string;
  /** ~1fps browser screenshots. Defaults on locally, off in CI - see
   * resolveConfig. Env: SENTINEL_LIVE_VIEW=on|off. */
  liveView?: boolean;
  /** Force the whole integration on or off regardless of env. */
  enabled?: boolean;
  /** Print what the reporter is doing. Env: SENTINEL_DEBUG=1. */
  debug?: boolean;
}
