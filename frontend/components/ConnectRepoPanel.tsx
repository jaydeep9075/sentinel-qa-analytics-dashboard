"use client";

import { useState } from "react";
import { Check, Copy, RefreshCw } from "lucide-react";
import { API_BASE, authHeaders } from "@/lib/liveRuns";

export interface ConnectionInfo {
  base_url: string;
  api_key: string;
  authenticated: boolean;
  key_pinned_in_env?: boolean;
  install_command: string;
  package?: { name: string; version: string; filename: string } | null;
}

type Framework = "playwright" | "cypress";

/** The exact commands that connect a repo to THIS backend, with this
 * install's real URL, key and package version already filled in. The whole
 * point is that nothing here has to be adapted by hand - a value someone has
 * to substitute is a value someone will substitute wrong. */
function snippet(info: ConnectionInfo, framework: Framework): string {
  const key = info.api_key || "<this backend requires no key>";
  const common = [
    `# 1. install (this is the build this dashboard is running)`,
    info.install_command,
    ``,
  ];
  const run = [
    ``,
    `# 3. run`,
    `SENTINEL_URL=${info.base_url} \\`,
    `SENTINEL_API_KEY=${key} \\`,
    framework === "playwright" ? `  npx playwright test` : `  npx cypress run`,
  ];

  if (framework === "playwright") {
    return [
      ...common,
      `# 2. playwright.config.ts - wrap whatever is already there`,
      `import { withSentinel } from "sentinel-qa-reporter/playwright/config";`,
      ``,
      `export default defineConfig(`,
      `  withSentinel({ /* your existing config, unchanged */ })`,
      `);`,
      ...run,
    ].join("\n");
  }
  return [
    ...common,
    `# 2a. cypress.config.ts`,
    `import { registerSentinel } from "sentinel-qa-reporter/cypress";`,
    ``,
    `export default defineConfig({`,
    `  e2e: {`,
    `    setupNodeEvents(on, config) {`,
    `      return registerSentinel(on, config);`,
    `    },`,
    `  },`,
    `});`,
    ``,
    `# 2b. cypress/support/e2e.ts`,
    `import { registerSentinelSupport } from "sentinel-qa-reporter/cypress/support";`,
    `registerSentinelSupport();`,
    ...run,
  ].join("\n");
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 transition-colors hover:bg-slate-100 dark:border-white/[0.12] dark:bg-white/[0.05] dark:text-white/70 dark:hover:bg-white/[0.1]"
    >
      {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function ConnectRepoPanel({
  info,
  onRotated,
}: {
  info: ConnectionInfo;
  onRotated: (key: string) => void;
}) {
  const [framework, setFramework] = useState<Framework>("playwright");
  const [rotating, setRotating] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);
  const text = snippet(info, framework);

  const rotate = async () => {
    if (!window.confirm("Issue a new ingest key? Every repo using the current one stops reporting until it is updated.")) {
      return;
    }
    setRotating(true);
    setRotateError(null);
    try {
      const res = await fetch(`${API_BASE}/live/connection-info/rotate`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      onRotated(data.api_key);
    } catch (err) {
      setRotateError((err as Error).message);
    } finally {
      setRotating(false);
    }
  };

  return (
    <div className="mb-6 rounded-xl border border-slate-200 bg-white/90 p-4 dark:border-white/[0.08] dark:bg-black/40">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 dark:border-white/[0.1]">
          {(["playwright", "cypress"] as Framework[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFramework(f)}
              className={`rounded-md px-3 py-1 text-xs font-semibold capitalize transition-colors ${
                framework === f
                  ? "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300"
                  : "text-slate-500 hover:text-slate-700 dark:text-white/40 dark:hover:text-white/70"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <CopyButton value={text} />
      </div>

      <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
        {text}
      </pre>

      {!info.authenticated && (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          This backend has no ingest key set, so anyone who can reach it can post runs. Set{" "}
          <code className="font-mono">LIVE_INGEST_API_KEY</code> before exposing it beyond localhost.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-white/[0.06] dark:text-white/35">
        <span>
          {info.package
            ? `Serving ${info.package.name}@${info.package.version} from this host — no npm registry needed.`
            : "Install from npm; this host is not serving a bundled package build."}
        </span>
        {info.authenticated && !info.key_pinned_in_env && (
          <button
            type="button"
            onClick={rotate}
            disabled={rotating}
            className="flex items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1 font-semibold text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:border-white/[0.12] dark:text-white/70 dark:hover:bg-white/[0.08]"
          >
            <RefreshCw className={`h-3 w-3 ${rotating ? "animate-spin" : ""}`} />
            {rotating ? "Rotating…" : "Rotate key"}
          </button>
        )}
      </div>
      {rotateError && <p className="mt-2 text-xs text-red-500">{rotateError}</p>}
    </div>
  );
}
