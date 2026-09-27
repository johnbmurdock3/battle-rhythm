import assert from "node:assert/strict";
import { test } from "node:test";
import { discordNotifier, isDiscordWebhookUrl } from "../src/notify.ts";

const URL_OK = "https://discord.com/api/webhooks/9000000000000000001/abcDEF_ghi-JKL";

function fakeFetch(responses: (Response | Error)[]) {
  const calls: { url: string; body: any }[] = [];
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url, body: JSON.parse(String(init.body)) });
    const next = responses.shift()!;
    if (next instanceof Error) throw next;
    return next;
  }) as unknown as typeof fetch;
  return { f, calls };
}
const noSleep = async () => {};

test("only accepts real Discord webhook URLs", () => {
  assert.equal(isDiscordWebhookUrl(URL_OK), true);
  assert.equal(isDiscordWebhookUrl("http://discord.com/api/webhooks/1/x"), false);
  assert.equal(isDiscordWebhookUrl("https://evil.example/api/webhooks/1/x"), false);
  assert.throws(() => discordNotifier("https://example.com"), /not a Discord webhook URL/);
});

test("posts once on success, with mentions disabled", async () => {
  const { f, calls } = fakeFetch([new Response(null, { status: 204 })]);
  const r = await discordNotifier(URL_OK, f, noSleep)("hello @everyone");
  assert.deepEqual(r, { ok: true, status: 204, attempts: 1 });
  assert.deepEqual(calls[0].body.allowed_mentions, { parse: [] });
  assert.equal(calls[0].body.content, "hello @everyone");
});

test("waits out a 429 using retry_after, then succeeds", async () => {
  const waits: number[] = [];
  const { f } = fakeFetch([
    new Response(JSON.stringify({ retry_after: 1.2 }), { status: 429 }),
    new Response(null, { status: 204 }),
  ]);
  const r = await discordNotifier(URL_OK, f, async (ms) => void waits.push(ms))("x");
  assert.equal(r.ok, true);
  assert.equal(r.attempts, 2);
  assert.deepEqual(waits, [1200]);
});

test("gives up on a 429 that asks for longer than the worker can wait", async () => {
  const { f } = fakeFetch([new Response(JSON.stringify({ retry_after: 30 }), { status: 429 })]);
  const r = await discordNotifier(URL_OK, f, noSleep)("x");
  assert.equal(r.ok, false);
  assert.equal(r.attempts, 1);
});

test("retries 5xx and network errors up to three attempts", async () => {
  const { f, calls } = fakeFetch([new Response(null, { status: 502 }), new Error("reset"), new Response(null, { status: 503 })]);
  const r = await discordNotifier(URL_OK, f, noSleep)("x");
  assert.equal(r.ok, false);
  assert.equal(r.attempts, 3);
  assert.equal(calls.length, 3);
});

test("does not retry other 4xx (deleted webhook, bad body)", async () => {
  const { f, calls } = fakeFetch([new Response(null, { status: 404 })]);
  const r = await discordNotifier(URL_OK, f, noSleep)("x");
  assert.equal(r.status, 404);
  assert.equal(calls.length, 1);
});

test("truncates to Discord's 2,000-character limit", async () => {
  const { f, calls } = fakeFetch([new Response(null, { status: 204 })]);
  await discordNotifier(URL_OK, f, noSleep)("y".repeat(5000));
  assert.equal(calls[0].body.content.length, 2000);
});
