/** Framework-neutral core. Import a framework adapter instead unless you
 * are writing one:
 *
 *   sentinel-qa-reporter/playwright
 *   sentinel-qa-reporter/playwright/config
 *   sentinel-qa-reporter/cypress
 *   sentinel-qa-reporter/cypress/support
 */

export { SentinelClient, explainFailure, describeNetworkError, info, warn, debug } from "./client";
export type { StartResult } from "./client";
export { resolveConfig, isCi } from "./config";
export type { ResolvedConfig } from "./config";
export { detectCi } from "./ci";
export { redact, truncate } from "./redact";
export type {
  RunMeta,
  RunStatus,
  SentinelEvent,
  SentinelOptions,
  SentinelTest,
  TestStatus,
} from "./types";
