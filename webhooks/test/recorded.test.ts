// Replays real deliveries captured by the sandbox (scripts/export-fixtures.mjs).
// Empty until the sandbox has run; every file added after that becomes a
// permanent regression check.
//
// Two checks per recording:
//   1. GitHub's original signature verifies against the stored bytes. Needs the
//      sandbox secret in SANDBOX_WEBHOOK_SECRET; skipped without it (CI has none).
//   2. The body, re-signed with the test secret, goes through the full handler
//      without a 4xx/5xx. This is what catches a payload shape the rules
//      didn't expect.

import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";
import { verifySignature } from "../src/signature.ts";
import { harness } from "./helpers.ts";

const dir = new URL("fixtures/recorded/", import.meta.url);
const files = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".json")).sort() : [];
const sandboxSecret = process.env.SANDBOX_WEBHOOK_SECRET ?? "";

test("recorded fixtures present (informational)", () => {
  if (files.length === 0) console.log("# no recorded deliveries yet; run scripts/export-fixtures.mjs after the sandbox is live");
});

for (const f of files) {
  const rec = JSON.parse(readFileSync(new URL(f, dir), "utf8"));

  test(`${f}: GitHub's own signature verifies`, { skip: !sandboxSecret && "SANDBOX_WEBHOOK_SECRET not set" }, async () => {
    assert.equal(await verifySignature([sandboxSecret], new TextEncoder().encode(rec.body), rec.signature), true);
  });

  test(`${f}: replays through the handler`, async () => {
    const repo = JSON.parse(rec.body).repository?.full_name;
    const h = harness({ allowedRepo: repo });
    const r = await h.deliver(rec.event, rec.body);
    await h.settle();
    assert.equal(r.status, 200, await r.text());
  });
}
