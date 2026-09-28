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
import { fileURLToPath } from "node:url";

const limit = Number(process.argv[2] ?? 50);
const sql = `SELECT id, event, signature, body, received_at FROM payloads ORDER BY received_at DESC LIMIT ${limit}`;
// Run wrangler's own entry point with this same node, no shell. Going through
// npx on Windows needs shell: true, and the shell splits the SQL at every space
// (9/27: "Unknown arguments: id,, event,, ..."). No shell, no quoting problem.
const wrangler = fileURLToPath(new URL("../node_modules/wrangler/bin/wrangler.js", import.meta.url));
const args = [wrangler, "d1", "execute", "br-hooks-sandbox", "--remote", "--env", "sandbox", "--json", "--command", sql];
let out;
try {
  out = execFileSync(process.execPath, args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
} catch (e) {
  // Wrangler on Windows can crash while exiting (libuv "UV_HANDLE_CLOSING"
  // assertion) after printing a complete result. Keep the output if it parses.
  out = e.stdout ?? "";
  try {
    JSON.parse(out);
    console.error("note: wrangler exited abnormally after returning results; using them");
  } catch {
    console.error(e.stderr || e.message);
    process.exit(1);
  }
}
const parsed = JSON.parse(out);
if (!Array.isArray(parsed) || !parsed[0] || !Array.isArray(parsed[0].results)) {
  console.error("wrangler returned something other than query results:");
  console.error(JSON.stringify(parsed, null, 2).slice(0, 2000));
  process.exit(1);
}
const rows = parsed[0].results;
const dir = new URL("../test/fixtures/recorded/", import.meta.url);
mkdirSync(dir, { recursive: true });
let skipped = 0;
for (const r of rows) {
  const payload = JSON.parse(r.body);
  // scripts/probe.mjs signs its own test requests; those aren't GitHub's.
  if (payload.sender?.login === "probe") {
    skipped++;
    continue;
  }
  const name = `${r.event}${payload.action ? "-" + payload.action : ""}-${r.id.slice(0, 8)}.json`;
  writeFileSync(new URL(name, dir), JSON.stringify({ delivery: r.id, event: r.event, signature: r.signature, received_at: r.received_at, body: r.body }, null, 2) + "\n");
  console.log("wrote", name);
}
console.log(`${rows.length - skipped} fixtures in test/fixtures/recorded/${skipped ? ` (${skipped} probe requests skipped)` : ""}`);
