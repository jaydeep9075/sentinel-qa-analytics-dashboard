/** Shared by both halves of the Cypress adapter, in a module of its own
 * because the support file is bundled *for the browser*. Importing them from
 * ./index would drag the node client - and `node:fs` with it - into that
 * bundle, which fails at build time in the consuming repo. */

export const SENTINEL_ENV_FLAG = "sentinelEnabled";
export const SENTINEL_TASK = "sentinel:events";
