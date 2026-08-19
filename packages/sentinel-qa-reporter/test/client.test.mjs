import { strict as assert } from "node:assert";
import { test } from "node:test";
import { createServer } from "node:http";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const { SentinelClient, explainFailure, describeNetworkError } = await import(
  pathToFileURL(resolve("dist/core/client.js")).href
);
const { resolveConfig } = await import(pathToFileURL(resolve("dist/core/config.js")).href);
const { redact, truncate } = await import(pathToFileURL(resolve("dist/core/redact.js")).href);

/** A throwaway backend that records what the client sent. Real HTTP rather
 * than a stubbed fetch, because half of what is being tested here is how the
 * client behaves against actual status codes and connection failures. */
async function fakeBackend(handler) {
  const received = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString() || "{}";
    const entry = { method: req.method, url: req.url, body: safeJson(body) };
    received.push(entry);
    const reply = handler ? handler(entry) : null;
    res.writeHead(reply?.status ?? 200, { "content-type": "application/json" });
    res.end(JSON.stringify(reply?.body ?? { run_id: "run_test123" }));
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}`;
  return {
    url,
    received,
    // closeAllConnections first: the client uses fetch, which keeps
    // connections alive, and server.close() waits for every open one - so
    // without this the callback never fires and the test file hangs.
    close: () =>
      new Promise((r) => {
        server.closeAllConnections();
        server.close(r);
      }),
  };
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function client(url, extra = {}) {
  return new SentinelClient(
    resolveConfig({ url, apiKey: "k", liveView: false, ...extra }, {})
  );
}

test("start posts the run and exposes a watch URL", async () => {
  const backend = await fakeBackend();
  const c = client(backend.url, { dashboardUrl: "http://dash:3000" });
  const result = await c.start({ framework: "cypress", name: "checkout.cy.ts", total_tests: 4 });
  assert.equal(result.ok, true);
  assert.equal(result.runId, "run_test123");
  assert.equal(result.watchUrl, "http://dash:3000/runs/run_test123/live");
  assert.equal(backend.received[0].body.framework, "cypress");
  assert.equal(backend.received[0].body.total_tests, 4);
  await c.finish("passed");
  await backend.close();
});

test("a rejected key disables reporting and names the cause", async () => {
  const backend = await fakeBackend(() => ({ status: 401, body: {} }));
  const c = client(backend.url);
  const result = await c.start({ framework: "playwright" });
  assert.equal(result.ok, false);
  assert.match(result.reason, /SENTINEL_API_KEY does not match/);
  assert.equal(c.active, false);
  // Emitting after a failed handshake must be inert, not queued forever.
  c.emit({ event_type: "test.log", ts: "now", payload: { message: "x" } });
  await c.flush(true);
  assert.equal(backend.received.length, 1);
  await backend.close();
});

test("a backend that closes the connection never throws into the caller", async () => {
  // A server that destroys the socket mid-request is the closest reliable
  // stand-in for "the backend went away". Pointing at a dead port instead
  // would sit through the OS connect timeout, which on Windows is long
  // enough to hang the suite.
  const server = createServer((req) => req.destroy());
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const c = client(`http://127.0.0.1:${server.address().port}`);
  const result = await c.start({ framework: "playwright" });
  assert.equal(result.ok, false);
  assert.ok(result.reason.length > 0);
  await c.finish("failed"); // must resolve, not reject
  server.closeAllConnections();
  await new Promise((r) => server.close(r));
});

test("events are batched into one request and secrets are stripped", async () => {
  const backend = await fakeBackend();
  const c = client(backend.url);
  await c.start({ framework: "playwright" });
  c.emit({
    event_type: "test.log",
    ts: "t",
    payload: { level: "stdout", message: 'curl -H "Authorization: Bearer abcdef1234567890"' },
  });
  c.emit({ event_type: "test.finished", ts: "t", test: { id: "a", title: "a", status: "passed" } });
  await c.flush(true);
  const posted = backend.received.find((r) => r.url.endsWith("/events"));
  assert.equal(posted.body.events.length, 2, "both events in a single request");
  assert.doesNotMatch(posted.body.events[0].payload.message, /abcdef1234567890/);
  assert.match(posted.body.events[0].payload.message, /Authorization: \*\*\*/);
  await c.finish("passed");
  await backend.close();
});

test("finish is idempotent, so a signal handler and an end hook cannot double-finalize", async () => {
  const backend = await fakeBackend();
  const c = client(backend.url);
  await c.start({ framework: "playwright" });
  await c.finish("passed");
  await c.finish("cancelled");
  const patches = backend.received.filter((r) => r.method === "PATCH");
  assert.equal(patches.length, 1);
  assert.equal(patches[0].body.status, "passed");
  await backend.close();
});

test("a 404 on events stops reporting instead of retrying into a void", async () => {
  const backend = await fakeBackend((entry) =>
    entry.url.endsWith("/events") ? { status: 404, body: {} } : null
  );
  const c = client(backend.url);
  await c.start({ framework: "playwright" });
  c.emit({ event_type: "test.log", ts: "t", payload: { message: "hi" } });
  await c.flush(true);
  assert.equal(c.active, false);
  await backend.close();
});

test("a backend that stops accepting events sheds logs but keeps test results", async () => {
  // 503 rather than a closed socket: it exercises the same re-queue path
  // while failing immediately, so the test does not sit through connection
  // timeouts. A backend restarting mid-run looks exactly like this.
  const backend = await fakeBackend((entry) =>
    entry.url.endsWith("/events") ? { status: 503, body: {} } : null
  );
  const c = client(backend.url);
  await c.start({ framework: "playwright" });

  for (let i = 0; i < 900; i++) {
    c.emit({ event_type: "test.log", ts: "t", payload: { message: `line ${i}` } });
  }
  for (let i = 0; i < 40; i++) {
    c.emit({
      event_type: "test.finished",
      ts: "t",
      test: { id: `t${i}`, title: `t${i}`, status: "passed" },
    });
  }
  // Emitting kicks off flushes that briefly hold a batch out of the queue,
  // so let the in-flight ones fail and re-queue before counting.
  await new Promise((r) => setTimeout(r, 200));

  assert.ok(c.pending.length <= 500, `queue stayed bounded (was ${c.pending.length})`);
  assert.equal(
    c.pending.filter((e) => e.event_type === "test.finished").length,
    40,
    "every test result survived shedding"
  );
  assert.equal(c.active, true, "a 503 is transient - reporting stays on and retries");
  await c.finish("passed");
  await backend.close();
});

test("oversized errors and log lines are truncated before they are sent", () => {
  assert.equal(truncate("abc", 10), "abc");
  const cut = truncate("x".repeat(5000), 100);
  assert.ok(cut.length < 200);
  assert.match(cut, /truncated 4900 more characters/);
});

test("redaction catches the common accidents and leaves ordinary output alone", () => {
  assert.match(redact("api_key=sk-live-9f8a7b6c5d"), /api_key=\*\*\*/);
  assert.match(redact('{"password": "hunter22"}'), /\*\*\*/);
  assert.match(redact("postgres://user:s3cr3t@db:5432/x"), /user:\*\*\*@/);
  const ordinary = "expected 3 to equal 4 at cart.spec.ts:12";
  assert.equal(redact(ordinary), ordinary);
});

test("failure explanations name the cause, not the status code", () => {
  assert.match(explainFailure(403, "http://x", false), /is not set/);
  assert.match(explainFailure(404, "http://x", true), /not a Sentinel API/);
  assert.match(explainFailure(502, "http://x", true), /server error/);
  assert.match(describeNetworkError(new Error("fetch failed"), "http://x"), /could not reach/);
  const timeout = new Error("aborted");
  timeout.name = "TimeoutError";
  assert.match(describeNetworkError(timeout, "http://x"), /did not respond/);
});
