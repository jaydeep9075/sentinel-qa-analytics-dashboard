import { strict as assert } from "node:assert";
import { test } from "node:test";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const { withSentinel } = await import(
  pathToFileURL(resolve("dist/playwright/config.js")).href
);
const { resolveConfig, isCi } = await import(
  pathToFileURL(resolve("dist/core/config.js")).href
);

const SENTINEL_ENV = ["SENTINEL_URL", "SENTINEL_BASE_URL", "SENTINEL_LIVE_VIEW", "CI", "TEST_PARALLEL_INDEX"];

/** Runs fn with exactly the given Sentinel-related env, restoring after. The
 * suite would otherwise pass or fail depending on whether the developer
 * running it happens to have SENTINEL_URL exported. */
function withEnv(vars, fn) {
  const saved = Object.fromEntries(SENTINEL_ENV.map((k) => [k, process.env[k]]));
  for (const k of SENTINEL_ENV) delete process.env[k];
  Object.assign(process.env, vars);
  try {
    return fn();
  } finally {
    for (const k of SENTINEL_ENV) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

test("does nothing when SENTINEL_URL is unset", () => {
  withEnv({}, () => {
    const input = { testDir: "./tests", reporter: [["html"]] };
    assert.equal(withSentinel(input), input);
  });
});

test("enabled:false overrides a configured environment", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const input = { reporter: [["html"]] };
    assert.equal(withSentinel(input, { enabled: false }), input);
  });
});

test("appends the reporter instead of replacing what the repo had", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const out = withSentinel({ reporter: [["html", { open: "never" }]] });
    assert.equal(out.reporter.length, 2);
    assert.deepEqual(out.reporter[0], ["html", { open: "never" }]);
    assert.equal(out.reporter[1][0], "sentinel-qa-reporter/playwright");
  });
});

test("normalizes a bare string reporter rather than dropping it", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const out = withSentinel({ reporter: "line" });
    assert.deepEqual(out.reporter[0], ["line"]);
    assert.equal(out.reporter.length, 2);
  });
});

// The whole reason withSentinel exists: Playwright REPLACES a config-level
// use.launchOptions with a project-level one rather than merging, so a
// top-level CDP flag never reaches a project that sets its own args.
test("injects the CDP flag into every Chromium project, skipping webkit/firefox", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const out = withSentinel({
      use: { headless: true },
      projects: [
        { name: "chrome", use: { launchOptions: { args: ["--no-sandbox"], slowMo: 200 } } },
        { name: "safari", use: { browserName: "webkit" } },
        { name: "ff", use: { browserName: "firefox", launchOptions: { args: ["-headless"] } } },
      ],
    });
    assert.deepEqual(out.projects[0].use.launchOptions.args, [
      "--no-sandbox",
      "--remote-debugging-port=9222",
    ]);
    assert.equal(out.projects[0].use.launchOptions.slowMo, 200, "other launchOptions survive");
    assert.equal(out.projects[1].use.launchOptions, undefined, "webkit has no CDP endpoint");
    assert.deepEqual(out.projects[2].use.launchOptions.args, ["-headless"], "firefox untouched");
    assert.deepEqual(out.use.launchOptions.args, ["--remote-debugging-port=9222"]);
  });
});

test("offsets the port per worker while the reporter keeps the base port", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000", TEST_PARALLEL_INDEX: "3" }, () => {
    const out = withSentinel({ use: {} }, { liveViewPort: 9300 });
    assert.deepEqual(out.use.launchOptions.args, ["--remote-debugging-port=9303"]);
    assert.equal(out.reporter[1][1].liveViewPort, 9300);
  });
});

test("respects a debugging port the repo already set", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const out = withSentinel({
      projects: [{ name: "c", use: { launchOptions: { args: ["--remote-debugging-port=7000"] } } }],
    });
    assert.deepEqual(out.projects[0].use.launchOptions.args, ["--remote-debugging-port=7000"]);
  });
});

test("liveView:false wires the reporter but touches no launch args", () => {
  withEnv({ SENTINEL_URL: "http://localhost:8000" }, () => {
    const out = withSentinel({ use: { headless: true } }, { liveView: false });
    assert.equal(out.reporter.length, 2);
    assert.deepEqual(out.use, { headless: true });
  });
});

// Screenshots of the app under test are the one thing this package sends
// that could carry customer data, and on CI nobody is watching them live.
test("live view defaults on locally and off in CI", () => {
  withEnv({ SENTINEL_URL: "http://x" }, () => {
    assert.equal(resolveConfig().liveView, true);
  });
  withEnv({ SENTINEL_URL: "http://x", CI: "true" }, () => {
    assert.equal(resolveConfig().liveView, false);
    assert.equal(isCi(), true);
    assert.equal(resolveConfig({ liveView: true }).liveView, true, "explicit option wins");
  });
  withEnv({ SENTINEL_URL: "http://x", CI: "true", SENTINEL_LIVE_VIEW: "on" }, () => {
    assert.equal(resolveConfig().liveView, true, "env override wins over the CI default");
  });
});

test("trailing slashes on SENTINEL_URL do not produce doubled paths", () => {
  withEnv({ SENTINEL_URL: "https://sentinel.example.com//" }, () => {
    assert.equal(resolveConfig().url, "https://sentinel.example.com");
    assert.equal(resolveConfig().dashboardUrl, "https://sentinel.example.com");
  });
});
