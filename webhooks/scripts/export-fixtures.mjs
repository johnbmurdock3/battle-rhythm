#!/usr/bin/env node
// Pull real deliveries the sandbox receiver stored (STORE_BODIES = "1") and
// write them as regression fixtures. Each file keeps GitHub's own signature
// next to the exact body, so test/recorded.test.ts can prove the receiver
// verifies GitHub-made signatures, not only ones the tests made themselves.
//
//   node scripts/export-fixtures.mjs            # newest 50
//   node scripts/export-fixtures.mjs 200

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const limit = Number(process.argv[2] ?? 50);
const sql = `SELECT id, event, signature, body, received_at FROM payloads ORDER BY received_at DESC LIMIT ${limit}`;
const out = execFileSync(
  "npx",
  ["wrangler", "d1", "execute", "br-hooks-sandbox", "--remote", "--env", "sandbox", "--json", "--command", sql],
  { encoding: "utf8", shell: process.platform === "win32" },
);
const rows = JSON.parse(out)[0].results;
const dir = new URL("../test/fixtures/recorded/", import.meta.url);
mkdirSync(dir, { recursive: true });
for (const r of rows) {
  const payload = JSON.parse(r.body);
  const name = `${r.event}${payload.action ? "-" + payload.action : ""}-${r.id.slice(0, 8)}.json`;
  writeFileSync(new URL(name, dir), JSON.stringify({ delivery: r.id, event: r.event, signature: r.signature, received_at: r.received_at, body: r.body }, null, 2) + "\n");
  console.log("wrote", name);
}
console.log(`${rows.length} fixtures in test/fixtures/recorded/`);
