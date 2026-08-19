#!/usr/bin/env node
/**
 * Sentinel dashboard driver — launch the stack and poke it programmatically.
 *
 * The app is two processes (FastAPI on 8000, Next.js on 3000) behind a login
 * wall, so "run it" is never one command. This wraps the whole thing:
 *
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs up
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs login
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs api GET /dashboard/overview
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs shot /dashboard
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs smoke
 *   node .claude/skills/run-sentinel-dashboard/driver.mjs down
 *
 * Run it from the repo root (sentinel-qa-analytics-dashboard/).
 *
 * State (token, child PIDs) lives in .claude/skills/run-sentinel-dashboard/
 * .driver-state.json so each command is independent — you can `login` in one
 * shell and `api` in another.
 */

import { createRequire } from "node:module";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SKILL_DIR, "../../..");
const STATE_FILE = join(SKILL_DIR, ".driver-state.json");
const SHOT_DIR = join(SKILL_DIR, "shots");
const LOG_DIR = join(SKILL_DIR, "logs");

const API = process.env.SENTINEL_API || "http://localhost:8000";
const WEB = process.env.SENTINEL_WEB || "http://localhost:3000";

// Windows venv layout; POSIX venvs put python in bin/.
const PY = existsSync(join(ROOT, "venv/Scripts/python.exe"))
  ? join(ROOT, "venv/Scripts/python.exe")
  : join(ROOT, "venv/bin/python");

const isWin = process.platform === "win32";

// ── state ────────────────────────────────────────────────────────────────────
const readState = () => {
  try {
    return JSON.parse(readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
};
const writeState = (patch) =>
  writeFileSync(STATE_FILE, JSON.stringify({ ...readState(), ...patch }, null, 2));

// ── process control ──────────────────────────────────────────────────────────
/**
 * Free a TCP port by killing whatever listens on it.
 *
 * Both servers refuse to start on a taken port rather than picking another, and
 * a half-dead process from a previous run is the single most common reason a
 * fresh `up` appears to hang. Clearing first is cheaper than diagnosing it.
 */
function killPort(port) {
  if (isWin) {
    spawnSync(
      "powershell",
      [
        "-NoProfile",
        "-Command",
        `Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue |` +
          ` Select-Object -ExpandProperty OwningProcess -Unique |` +
          ` ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }`,
      ],
      { stdio: "ignore" },
    );
  } else {
    spawnSync("bash", ["-c", `lsof -ti:${port} | xargs -r kill -9`], { stdio: "ignore" });
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Poll a URL until it answers, or give up. Returns true on success. */
async function waitFor(url, label, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (res.status < 500) {
        console.log(`  ${label} is up (${url} -> ${res.status})`);
        return true;
      }
    } catch {
      /* not listening yet */
    }
    await sleep(2000);
  }
  console.error(`  ${label} did NOT answer within ${timeoutMs / 1000}s — see ${LOG_DIR}`);
  return false;
}

/**
 * Spawn a server detached, with its output on a log file.
 *
 * Never `shell: true`. The repo path can contain spaces ("C:\Users\JAIDEEP
 * JOSHI\..."), and under a shell the command is concatenated rather than
 * escaped, so the venv python path splits at the space and cmd.exe reports
 * "'C:\Users\JAIDEEP' is not recognized". Spawning the executable directly
 * passes argv as an array and keeps the path intact — which means npm has to
 * be named as `npm.cmd` on Windows, since only a shell would resolve `npm`.
 */
function launch(name, cmd, args, cwd) {
  mkdirSync(LOG_DIR, { recursive: true });
  const out = join(LOG_DIR, `${name}.log`);
  const fd = openSync(out, "w");
  const child = spawn(cmd, args, {
    cwd,
    stdio: ["ignore", fd, fd],
    // detached on Windows too: without it the server is tied to this node
    // process and dies the moment `up` returns, so the very next command gets
    // ECONNREFUSED against a port that was answering seconds earlier.
    detached: true,
    windowsHide: true,
  });
  child.on("error", (e) => console.error(`  ${name} failed to spawn: ${e.message}`));
  child.unref();
  console.log(`  ${name} pid=${child.pid} -> ${out}`);
  return child.pid;
}

/**
 * Absolute path to npm-cli.js, run with this same node binary.
 *
 * Node >=18.20 refuses to spawn a .cmd/.bat without `shell: true` (EINVAL,
 * from the CVE-2024-27980 fix) — and `shell: true` is exactly what breaks on a
 * path containing spaces. Running npm's JS entrypoint under `process.execPath`
 * sidesteps both: no shell, no .cmd, spaces preserved.
 */
function npmCli() {
  const fromNode = resolve(dirname(process.execPath), "node_modules/npm/bin/npm-cli.js");
  if (existsSync(fromNode)) return fromNode;
  try {
    return createRequire(import.meta.url).resolve("npm/bin/npm-cli.js");
  } catch {
    console.error("Could not locate npm-cli.js — is npm installed alongside node?");
    process.exit(1);
  }
}

// ── commands ─────────────────────────────────────────────────────────────────
async function cmdUp() {
  if (!existsSync(PY)) {
    console.error(
      `No venv python at ${PY}\n` +
        `Create it:  python -m venv venv && ./venv/Scripts/pip install -r requirements.txt`,
    );
    process.exit(1);
  }
  console.log("Starting Sentinel...");
  killPort(8000);
  killPort(3000);
  await sleep(1000);

  const backendPid = launch("backend", PY, ["-m", "services.main"], ROOT);
  const frontendPid = launch("frontend", process.execPath, [npmCli(), "run", "dev"], join(ROOT, "frontend"));
  writeState({ backendPid, frontendPid });

  const ok = [
    await waitFor(`${API}/health`, "backend"),
    await waitFor(`${WEB}/login`, "frontend"),
  ].every(Boolean);

  if (!ok) process.exit(1);
  console.log(`\nReady:\n  Dashboard ${WEB}/dashboard\n  API docs  ${API}/docs`);
}

function cmdDown() {
  killPort(8000);
  killPort(3000);
  writeState({ backendPid: null, frontendPid: null });
  console.log("Stopped backend (8000) and frontend (3000).");
}

async function cmdStatus() {
  for (const [label, url] of [
    ["backend", `${API}/health`],
    ["frontend", `${WEB}/login`],
  ]) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
      console.log(`${label.padEnd(9)} UP    ${url} -> ${res.status}`);
    } catch (e) {
      console.log(`${label.padEnd(9)} DOWN  ${url} (${e.message})`);
    }
  }
}

/**
 * Sign in and cache the bearer token.
 *
 * /auth/login takes username and password as QUERY parameters, not a JSON body
 * — they are bare `str` parameters on the FastAPI handler. Posting a body here
 * returns 422, which reads like a validation bug in your payload and is not.
 */
async function cmdLogin() {
  const username = process.env.SENTINEL_USER || "admin";
  const password = process.env.SENTINEL_PASS;
  if (!password) {
    console.error(
      "Set SENTINEL_PASS (and SENTINEL_USER if not 'admin').\n" +
        "Unknown password? Reset it locally:\n" +
        `  ${PY} -m services.admin_users reset-password --username admin\n` +
        `List accounts:  ${PY} -m services.admin_users list-users`,
    );
    process.exit(1);
  }
  const qs = new URLSearchParams({ username, password });
  const res = await fetch(`${API}/auth/login?${qs}`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    console.error(`Login failed (${res.status}): ${body.detail || JSON.stringify(body)}`);
    process.exit(1);
  }
  writeState({
    token: body.access_token,
    username: body.username,
    workspaceId: body.workspace_id || "default",
  });
  console.log(`Logged in as ${body.username} (role=${body.role}, workspace=${body.workspace_id})`);
}

function authHeaders(extra = {}) {
  const { token, workspaceId } = readState();
  if (!token) {
    console.error("No token — run `driver.mjs login` first.");
    process.exit(1);
  }
  return {
    Authorization: `Bearer ${token}`,
    "x-workspace-id": workspaceId || "default",
    ...extra,
  };
}

/** Which build the dashboard reads by default: newest completed ingestion. */
async function latestIngestion() {
  const res = await fetch(`${API}/ingestions`, { headers: authHeaders() });
  const data = await res.json();
  const list = Array.isArray(data) ? data : data.ingestions || [];
  const ids = list
    .map((i) => (typeof i === "string" ? i : i.ingestion_id || i.build_id || i.id))
    .filter(Boolean)
    .sort();
  return ids[ids.length - 1] || "";
}

/**
 * Normalise an API path argument.
 *
 * Git Bash (MSYS) rewrites any argument that looks like a POSIX path before
 * node ever sees it, so `api GET /health` arrives as
 * `C:/Users/.../Git/health` and the fetch URL becomes nonsense. Recover the
 * real path by taking the last segment(s) after the mangled prefix, and accept
 * a leading-slash-free form (`api GET health`) which MSYS leaves alone.
 * Callers can also prefix the whole command with MSYS_NO_PATHCONV=1.
 */
function apiPath(raw) {
  let p = String(raw || "");
  const mangled = p.match(/^[A-Za-z]:[\/].*?[\/]Git[\/](.*)$/);
  if (mangled) p = "/" + mangled[1];
  if (!p.startsWith("/")) p = "/" + p;
  return p;
}

async function cmdApi(method, rawPath, bodyArg) {
  const path = apiPath(rawPath);
  const ingestion = process.env.SENTINEL_INGESTION || (await latestIngestion());
  const res = await fetch(`${API}${path}`, {
    method: (method || "GET").toUpperCase(),
    headers: authHeaders({
      "x-ingestion-id": ingestion,
      ...(bodyArg ? { "Content-Type": "application/json" } : {}),
    }),
    body: bodyArg,
  });
  const text = await res.text();
  console.log(`${res.status} ${method.toUpperCase()} ${path}  (x-ingestion-id: ${ingestion || "none"})`);
  try {
    console.log(JSON.stringify(JSON.parse(text), null, 2));
  } catch {
    console.log(text.slice(0, 2000));
  }
  if (!res.ok) process.exit(1);
}

/**
 * Resolve Playwright. It is not a dependency of this app — the sibling
 * sfcc-qa-automation repo carries it along with downloaded browsers, so the
 * driver borrows it from there. Override with SENTINEL_PLAYWRIGHT_FROM if it
 * lives somewhere else.
 */
function loadChromium() {
  const anchor =
    process.env.SENTINEL_PLAYWRIGHT_FROM ||
    resolve(ROOT, "../sfcc-qa-automation/package.json");
  try {
    return createRequire(anchor)("playwright").chromium;
  } catch (e) {
    console.error(
      `Could not load Playwright from ${anchor}\n${e.message}\n` +
        `Point SENTINEL_PLAYWRIGHT_FROM at a package.json whose node_modules has playwright, or:\n` +
        `  npm i -D playwright && npx playwright install chromium`,
    );
    process.exit(1);
  }
}

/**
 * Open a route as a signed-in user and screenshot it.
 *
 * The token is seeded into localStorage via an init script that runs before any
 * page JS, because the app reads it during the first render — setting it after
 * goto() lands you on /login and screenshots the login form instead.
 */
async function cmdShot(rawRoutes) {
  const routes = rawRoutes.map(apiPath); // same MSYS path mangling applies here
  const { token, workspaceId, username } = readState();
  if (!token) {
    console.error("No token — run `driver.mjs login` first.");
    process.exit(1);
  }
  mkdirSync(SHOT_DIR, { recursive: true });
  const chromium = loadChromium();
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });

  const ingestion = process.env.SENTINEL_INGESTION || (await latestIngestion());
  await ctx.addInitScript(
    ([t, w, u, ing]) => {
      localStorage.setItem("token", t);
      localStorage.setItem("workspace_id", w);
      localStorage.setItem("username", u);
      localStorage.setItem("role", "cto");
      if (ing) localStorage.setItem("selectedIngestion", ing);
    },
    [token, workspaceId || "default", username || "admin", ingestion],
  );

  const failed = [];
  for (const route of routes) {
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(`${WEB}${route}`, { waitUntil: "domcontentloaded", timeout: 60000 });
    // The dashboard paints skeletons first and fills them from /dashboard/overview.
    // Waiting on network idle is unreliable (a 20s poll keeps it busy), so wait
    // for the request that actually populates the page, then let React commit.
    await page
      .waitForResponse((r) => r.url().includes("/dashboard/overview"), { timeout: 30000 })
      .catch(() => {});
    await page.waitForTimeout(2500);

    const name = (route.replace(/^\//, "").replace(/\//g, "-") || "root") + ".png";
    const out = join(SHOT_DIR, name);
    await page.screenshot({ path: out, fullPage: false });
    console.log(`  ${route} -> ${out}${errors.length ? `  [${errors.length} page errors]` : ""}`);
    errors.slice(0, 3).forEach((e) => console.log(`      ${e.split("\n")[0]}`));
    if (errors.length) failed.push(route);
    await page.close();
  }
  await browser.close();
  if (failed.length) console.log(`\nRoutes with page errors: ${failed.join(", ")}`);
}

/** End-to-end: everything must already be `up`. Exits non-zero on any failure. */
async function cmdSmoke() {
  let bad = 0;
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
    if (!ok) bad++;
  };

  console.log("Smoke:");
  const health = await fetch(`${API}/health`).then((r) => r.json());
  check("backend /health", health.status === "ok", JSON.stringify(health).slice(0, 80));

  const ingestion = process.env.SENTINEL_INGESTION || (await latestIngestion());
  check("has an ingested build", !!ingestion, ingestion);

  const ov = await fetch(`${API}/dashboard/overview?include_quality=true`, {
    headers: authHeaders({ "x-ingestion-id": ingestion }),
  }).then((r) => r.json());

  const total = ov?.status?.total_rows ?? ov?.status_summary?.total ?? 0;
  check("overview returns rows", Number(total) > 0, `total=${total}`);

  const rt = ov?.insights?.runtime || {};
  check(
    "runtime reports elapsed time",
    Number(rt.wall_clock_seconds) > 0,
    `elapsed=${Math.round(rt.wall_clock_seconds / 60)}m across ${rt.workers || 0} workers` +
      ` (machine time ${(rt.total_seconds / 3600).toFixed(1)}h)`,
  );

  await cmdShot(["/dashboard"]);
  check("screenshot written", existsSync(join(SHOT_DIR, "dashboard.png")));

  console.log(bad ? `\n${bad} check(s) failed.` : "\nAll checks passed.");
  process.exit(bad ? 1 : 0);
}

/**
 * Run ONE server in the foreground, logging to stdout.
 *
 * `up` detaches its children, which is right in a normal shell but not enough
 * inside an agent harness: on Windows the harness runs each command in a Job
 * Object, and `detached: true` maps to DETACHED_PROCESS, which does NOT set
 * CREATE_BREAKAWAY_FROM_JOB. So when the harness closes the job at the end of
 * a tool call, every "detached" server dies with it — `up` reports both
 * timing out while frontend.log cheerfully says "Ready in 783ms".
 *
 * The fix is not to detach harder, it is to not exit: run in the foreground
 * and let the harness's own background mechanism (Bash run_in_background,
 * `&`, tmux) own the process lifetime.
 */
function cmdServe(which) {
  const specs = {
    backend: { cmd: PY, args: ["-m", "services.main"], cwd: ROOT },
    frontend: { cmd: process.execPath, args: [npmCli(), "run", "dev"], cwd: join(ROOT, "frontend") },
  };
  const spec = specs[which];
  if (!spec) {
    console.error(`serve: expected "backend" or "frontend", got ${which ?? "nothing"}`);
    process.exit(1);
  }
  if (which === "backend" && !existsSync(PY)) {
    console.error(`No venv python at ${PY}`);
    process.exit(1);
  }
  killPort(which === "backend" ? 8000 : 3000);
  const child = spawn(spec.cmd, spec.args, { cwd: spec.cwd, stdio: "inherit", windowsHide: true });
  child.on("exit", (code) => process.exit(code ?? 0));
}

// ── dispatch ─────────────────────────────────────────────────────────────────
const [cmd, ...rest] = process.argv.slice(2);
const commands = {
  up: cmdUp,
  serve: () => cmdServe(rest[0]),
  down: () => cmdDown(),
  status: cmdStatus,
  login: cmdLogin,
  api: () => cmdApi(rest[0] || "GET", rest[1], rest[2]),
  shot: () => cmdShot(rest.length ? rest : ["/dashboard"]),
  smoke: cmdSmoke,
};

if (!commands[cmd]) {
  console.log(
    `usage: node driver.mjs <command>\n\n` +
      `  up                     start backend (8000) + frontend (3000), wait for both\n` +
      `  serve <backend|frontend>  run ONE server in the FOREGROUND (for agent
` +
      `                         harnesses, where detached children get reaped)
` +
      `  down                   stop both\n` +
      `  status                 are they answering?\n` +
      `  login                  sign in (SENTINEL_USER/SENTINEL_PASS), cache token\n` +
      `  api <METHOD> <path>    authenticated request, e.g. api GET /dashboard/overview\n` +
      `  shot [routes...]       screenshot routes as a signed-in user (default /dashboard)\n` +
      `  smoke                  end-to-end check, exits non-zero on failure\n`,
  );
  process.exit(cmd ? 1 : 0);
}
await commands[cmd]();
