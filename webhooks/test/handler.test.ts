import assert from "node:assert/strict";
import { test } from "node:test";
import { STUCK_AFTER_MS } from "../src/store.ts";
import { fixture, harness, json, SECRET } from "./helpers.ts";

// ---- request gatekeeping -------------------------------------------------

test("health check answers GET only", async () => {
  const h = harness();
  const ok = await h.call(new Request("https://hooks.test/health"));
  assert.equal(ok.status, 200);
  assert.deepEqual(await json(ok), { ok: true, env: "test" });
  assert.equal((await h.call(new Request("https://hooks.test/health", { method: "POST" }))).status, 405);
});

test("unknown paths are 404 and GET on the hook is 405", async () => {
  const h = harness();
  assert.equal((await h.call(new Request("https://hooks.test/"))).status, 404);
  const r = await h.call(new Request("https://hooks.test/github"));
  assert.equal(r.status, 405);
  assert.equal(r.headers.get("allow"), "POST");
});

test("form-encoded deliveries are refused with a fix-it message", async () => {
  const h = harness();
  const r = await h.deliver("ping", fixture("ping"), { headers: { "content-type": "application/x-www-form-urlencoded" } });
  assert.equal(r.status, 415);
  assert.match((await json(r)).error, /application\/json/);
});

test("oversized bodies are 413, by header and by actual size", async () => {
  const h = harness({ maxBytes: 100 });
  assert.equal((await h.deliver("ping", fixture("ping"))).status, 413);
  // A declared length over the cap is refused before the body is read.
  const big = harness();
  const r = await big.deliver("ping", fixture("ping"), { headers: { "content-length": String(10 * 1024 * 1024) } });
  assert.equal(r.status, 413);
});

test("missing event or delivery header is 400", async () => {
  const h = harness();
  assert.equal((await h.deliver("ping", fixture("ping"), { headers: { "x-github-delivery": "" } })).status, 400);
  assert.equal((await h.deliver("", fixture("ping"))).status, 400);
  assert.equal((await h.deliver("ping", fixture("ping"), { id: "../../etc/passwd" })).status, 400);
});

test("no signature, wrong secret, or tampered body is 401 and stores nothing", async () => {
  const h = harness();
  const id = crypto.randomUUID();
  assert.equal((await h.deliver("ping", fixture("ping"), { id, headers: { "x-hub-signature-256": "" } })).status, 401);
  assert.equal((await h.deliver("ping", fixture("ping"), { id, secret: "attacker" })).status, 401);
  // After the rejections the real delivery with the same id still goes through:
  // unsigned requests can't burn a delivery id.
  const ok = await h.deliver("ping", fixture("ping"), { id });
  assert.equal(ok.status, 200);
  assert.equal(h.logs.filter((l) => l.at === "reject").length, 2);
});

test("signed but not a JSON object is 400", async () => {
  const h = harness();
  assert.equal((await h.deliver("ping", "not json")).status, 400);
  assert.equal((await h.deliver("ping", "[1,2]")).status, 400);
  assert.equal((await h.deliver("ping", "null")).status, 400);
});

test("signed delivery from another repository is 403", async () => {
  const h = harness();
  const other = fixture("ping").replaceAll("johnbmurdock3/battle-rhythm", "someone/else");
  assert.equal((await h.deliver("ping", other)).status, 403);
  // Repo match is case-insensitive, like GitHub's own names.
  const upper = fixture("ping").replaceAll("johnbmurdock3/battle-rhythm", "JohnBMurdock3/Battle-Rhythm");
  assert.equal((await h.deliver("ping", upper)).status, 200);
});

// ---- delivery ids: redelivery, replay, conflict --------------------------

test("the same delivery twice is processed once", async () => {
  const h = harness();
  const id = crypto.randomUUID();
  const first = await json(await h.deliver("ping", fixture("ping"), { id }));
  await h.settle();
  const second = await h.deliver("ping", fixture("ping"), { id });
  assert.equal(first.outcome, "processed");
  assert.equal(second.status, 200);
  assert.equal((await json(second)).outcome, "duplicate");
  assert.equal(h.sent.length, 1, "one Discord message, not two");
});

test("a reused delivery id with a different body is 409", async () => {
  const h = harness();
  const id = crypto.randomUUID();
  await h.deliver("push", fixture("push"), { id });
  const r = await h.deliver("push", fixture("push_forced"), { id });
  assert.equal(r.status, 409);
});

test("a delivery stuck mid-processing can be claimed again after the timeout", async () => {
  const h = harness();
  const id = crypto.randomUUID();
  const bodySha = "00".repeat(32);
  const now = new Date(h.clock.t);
  assert.equal(await h.store.claim({ id, event: "push", action: null, repo: "r", bodySha, now }), "new");
  assert.equal(await h.store.claim({ id, event: "push", action: null, repo: "r", bodySha, now }), "duplicate");
  const later = new Date(h.clock.t + STUCK_AFTER_MS + 1000);
  assert.equal(await h.store.claim({ id, event: "push", action: null, repo: "r", bodySha, now: later }), "retry");
});

// ---- event rules -----------------------------------------------------------

test("ping posts a connected message", async () => {
  const h = harness();
  const r = await json(await h.deliver("ping", fixture("ping")));
  assert.equal(r.notify, "queued");
  await h.settle();
  assert.match(h.sent[0], /^\[test\] Webhook connected for johnbmurdock3\/battle-rhythm: hook 500000001/);
});

test("ordinary push is recorded without an alert; force-push to main alerts", async () => {
  const h = harness();
  const plain = await json(await h.deliver("push", fixture("push")));
  assert.equal(plain.detail, "1 commit to main");
  await h.deliver("push", fixture("push_forced"));
  await h.settle();
  assert.equal(h.sent.length, 1);
  assert.match(h.sent[0], /Force-push to main by johnbmurdock3: ccccccc -> bbbbbbb/);
});

test("branch deletion alerts, with the branch name passed through untouched", async () => {
  const h = harness();
  await h.deliver("push", fixture("push_deleted_branch"));
  await h.settle();
  // The name contains "@everyone"; notify.ts disables mentions, so it is shown, not pinged.
  assert.match(h.sent[0], /Branch deleted: @everyone-test/);
});

test("workflow_run: alert on the change, not on every run", async () => {
  const h = harness();
  const steps: [string, string | null][] = [
    ["workflow_run_requested", null], // not completed: ignored
    ["workflow_run_success_40", null], // first result, passing: no alert
    ["workflow_run_failure_41", "CI failure: tests on main (run #41)"],
    ["workflow_run_failure_42", null], // still failing: suppressed
    ["workflow_run_success_43", "CI recovered: tests on main (run #43) passed after run #42 failed"],
    ["workflow_run_cancelled_44", null], // cancelled says nothing about health
  ];
  for (const [name, expect] of steps) {
    const before = h.sent.length;
    const r = await h.deliver("workflow_run", fixture(name));
    assert.equal(r.status, 200, name);
    await h.settle();
    if (expect) assert.match(h.sent.at(-1)!, new RegExp(expect.replace(/[()#]/g, "\\$&")), name);
    else assert.equal(h.sent.length, before, `${name} should not alert`);
  }
  const s = await h.store.getWorkflow("190000001:main");
  assert.equal(s?.runNumber, 43);
  assert.equal(s?.conclusion, "success");
});

test("workflow_run: a late, older run never rewrites newer state", async () => {
  const h = harness();
  await h.deliver("workflow_run", fixture("workflow_run_success_43"));
  const late = await json(await h.deliver("workflow_run", fixture("workflow_run_failure_41")));
  await h.settle();
  assert.equal(late.outcome, "ignored");
  assert.match(late.detail, /^stale/);
  assert.equal(h.sent.length, 0);
  assert.equal((await h.store.getWorkflow("190000001:main"))?.conclusion, "success");
});

test("workflow_run: the same run under a second delivery id is stale", async () => {
  // Two hooks on one repo, or a hook deleted and re-added, can send one run
  // twice with different delivery ids. Dedupe by id can't catch that; the
  // run number and attempt can.
  const h = harness();
  await h.deliver("workflow_run", fixture("workflow_run_success_40"));
  await h.deliver("workflow_run", fixture("workflow_run_failure_41"));
  await h.settle();
  const again = await json(await h.deliver("workflow_run", fixture("workflow_run_failure_41")));
  await h.settle();
  assert.equal(again.outcome, "ignored");
  assert.equal(h.sent.length, 1);
});

test("workflow_run: a re-run attempt of the same run counts as newer", async () => {
  const h = harness();
  await h.deliver("workflow_run", fixture("workflow_run_success_40"));
  await h.deliver("workflow_run", fixture("workflow_run_failure_42"));
  await h.settle();
  await h.deliver("workflow_run", fixture("workflow_run_success_42_attempt2"));
  await h.settle();
  assert.match(h.sent.at(-1)!, /recovered: tests on main \(run #42, attempt 2\)/);
});

// ---- failure handling -------------------------------------------------------

test("Discord down: delivery marked failed, state held back, redelivery sends the alert", async () => {
  const h = harness();
  const id = crypto.randomUUID();
  await h.deliver("workflow_run", fixture("workflow_run_success_40"));
  h.notifyResult = { ok: false, status: 503, attempts: 3, error: "discord 503" };
  const r = await h.deliver("workflow_run", fixture("workflow_run_failure_41"), { id });
  assert.equal(r.status, 200, "GitHub still gets a fast 2xx");
  await h.settle();
  assert.equal(h.sent.length, 0);
  assert.equal((await h.store.getWorkflow("190000001:main"))?.runNumber, 40, "state not advanced");

  // GitHub's "Redeliver" button sends the same id and body.
  h.notifyResult = { ok: true, status: 204, attempts: 1 };
  const again = await json(await h.deliver("workflow_run", fixture("workflow_run_failure_41"), { id }));
  assert.notEqual(again.outcome, "duplicate");
  await h.settle();
  assert.match(h.sent[0], /CI failure/);
  assert.equal((await h.store.getWorkflow("190000001:main"))?.runNumber, 41);
});

test("with no Discord URL configured, events are still recorded", async () => {
  const h = harness({}, false);
  const r = await json(await h.deliver("workflow_run", fixture("workflow_run_failure_41")));
  assert.equal(r.outcome, "processed");
  assert.match(r.detail, /no notifier configured/);
  assert.equal((await h.store.getWorkflow("190000001:main"))?.conclusion, "failure");
});

test("storage failure is a 500 so GitHub shows it and it can be redelivered", async () => {
  const h = harness();
  h.store.claim = async () => {
    throw new Error("D1 unavailable");
  };
  const r = await h.deliver("ping", fixture("ping"));
  assert.equal(r.status, 500);
});

test("rotation: deliveries signed with the previous secret still land", async () => {
  const h = harness({ secrets: ["brand-new", SECRET] });
  assert.equal((await h.deliver("ping", fixture("ping"))).status, 200);
});

test("sandbox mode keeps raw bodies and GitHub's signature for fixtures", async () => {
  const h = harness({ storeBodies: true });
  const id = crypto.randomUUID();
  await h.deliver("push", fixture("push"), { id });
  // Read it back through the same SQL the export script uses.
  const row = await (h.store as any).db.prepare("SELECT event, signature, body FROM payloads WHERE id = ?1").bind(id).first();
  assert.equal(row.event, "push");
  assert.equal(row.body, fixture("push"));
  assert.match(row.signature, /^sha256=[0-9a-f]{64}$/);
});
