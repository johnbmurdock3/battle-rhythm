#!/usr/bin/env node
// Probe a deployed receiver from the outside: the negative cases GitHub never
// sends, plus a signed delivery and its replay. Run it after every deploy.
//
//   PowerShell:
//     $env:WEBHOOK_SECRET = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText   (PS7)
//     $env:WEBHOOK_SECRET = "<paste>"                                                           (PS5.1)
//     node scripts/probe.mjs https://br-hooks-sandbox.<you>.workers.dev johnbmurdock3/battle-rhythm-sandbox
//     Remove-Item Env:WEBHOOK_SECRET
//
// The secret comes only from the environment, never from the command line,
// so it stays out of shell history. Every probe delivery is an event the
// receiver records but never alerts on (workflow_run "requested"), so running
// this against production doesn't post anything to Discord.

import { createHmac, randomUUID } from "node:crypto";

const [base, repo] = process.argv.slice(2);
const secret = process.env.WEBHOOK_SECRET;
if (!base || !repo || !secret) {
  console.error("usage: WEBHOOK_SECRET=... node scripts/probe.mjs <base-url> <owner/repo>");
  process.exit(2);
}
const hook = new URL("/github", base).toString();
const sign = (s, body) => "sha256=" + createHmac("sha256", s).update(body).digest("hex");

const body = (r = repo, runNumber = Date.now() % 1e9) =>
  JSON.stringify({
    action: "requested",
    workflow_run: { id: runNumber, name: "probe", head_branch: "probe", run_number: runNumber, run_attempt: 1, workflow_id: 1, status: "queued", conclusion: null },
    repository: { full_name: r, default_branch: "main" },
    sender: { login: "probe" },
  });

async function post({ payload = body(), id = randomUUID(), event = "workflow_run", sig, ctype = "application/json" } = {}) {
  const headers = { "content-type": ctype, "x-github-event": event, "x-github-delivery": id, "user-agent": "br-hooks-probe" };
  const s = sig === undefined ? sign(secret, payload) : sig;
  if (s) headers["x-hub-signature-256"] = s;
  const res = await fetch(hook, { method: "POST", headers, body: payload });
  let json = {};
  try {
    json = await res.json();
  } catch {}
  return { status: res.status, json };
}

const replayId = randomUUID();
const replayBody = body();
const cases = [
  ["health responds", async () => (await fetch(new URL("/health", base))).status, 200],
  ["GET on hook is refused", async () => (await fetch(hook)).status, 405],
  ["no signature", async () => (await post({ sig: "" })).status, 401],
  ["wrong secret", async () => (await post({ sig: sign("not-the-secret", body()) })).status, 401],
  ["tampered body", async () => {
    const b = body();
    return (await post({ payload: b.replace("probe", "evil"), sig: sign(secret, b) })).status;
  }, 401],
  ["legacy sha1 header only", async () => (await post({ sig: "sha1=" + "0".repeat(40) })).status, 401],
  ["form-encoded", async () => (await post({ ctype: "application/x-www-form-urlencoded" })).status, 415],
  ["signed, not JSON", async () => (await post({ payload: "not json" })).status, 400],
  ["signed, other repo", async () => (await post({ payload: body("someone/else") })).status, 403],
  ["signed delivery accepted", async () => (await post({ id: replayId, payload: replayBody })).json.outcome, "ignored"],
  ["same delivery replayed", async () => (await post({ id: replayId, payload: replayBody })).json.outcome, "duplicate"],
  ["same id, different body", async () => (await post({ id: replayId, payload: body(repo, 7) })).status, 409],
];

let failed = 0;
for (const [name, run, want] of cases) {
  let got;
  try {
    got = await run();
  } catch (e) {
    got = `error: ${e.message}`;
  }
  const ok = got === want;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name.padEnd(26)} got ${got}${ok ? "" : `, want ${want}`}`);
}
console.log(`\n${cases.length - failed}/${cases.length} probe checks passed against ${hook}`);
process.exit(failed ? 1 : 0);
