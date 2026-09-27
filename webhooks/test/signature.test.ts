import assert from "node:assert/strict";
import { test } from "node:test";
import { sign, verifySignature } from "../src/signature.ts";

const enc = new TextEncoder();

// The worked example in GitHub's "Validating webhook deliveries" docs.
test("matches GitHub's published test vector", async () => {
  const header = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17";
  assert.equal(await sign("It's a Secret to Everybody", "Hello, World!"), header);
  assert.equal(await verifySignature(["It's a Secret to Everybody"], enc.encode("Hello, World!"), header), true);
});

test("rejects a signature made with a different secret", async () => {
  const body = enc.encode('{"a":1}');
  assert.equal(await verifySignature(["right"], body, await sign("wrong", body)), false);
});

test("rejects when one byte of the body changes", async () => {
  const header = await sign("s", '{"a":1}');
  assert.equal(await verifySignature(["s"], enc.encode('{"a":2}'), header), false);
  // Re-serialized JSON is a different byte string even when it means the same thing.
  assert.equal(await verifySignature(["s"], enc.encode('{ "a": 1 }'), header), false);
});

test("rejects missing, legacy sha1, and malformed headers", async () => {
  const body = enc.encode("x");
  for (const h of [null, "", "sha1=" + "0".repeat(40), "sha256=", "sha256=zz" + "0".repeat(62), "0".repeat(64)]) {
    assert.equal(await verifySignature(["s"], body, h), false, String(h));
  }
});

test("accepts uppercase hex and surrounding whitespace", async () => {
  const h = await sign("s", "x");
  assert.equal(await verifySignature(["s"], enc.encode("x"), " sha256=" + h.slice(7).toUpperCase() + " "), true);
});

test("rotation: the previous secret still verifies until it is removed", async () => {
  const body = enc.encode("x");
  const old = await sign("old", body);
  assert.equal(await verifySignature(["new", "old"], body, old), true);
  assert.equal(await verifySignature(["new", ""], body, old), false);
});

test("fails closed when no secret is configured", async () => {
  await assert.rejects(verifySignature(["", ""], enc.encode("x"), "sha256=" + "0".repeat(64)), /no webhook secret/);
});
