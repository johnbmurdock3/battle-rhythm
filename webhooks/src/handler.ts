// The request pipeline. Order matters and each step is a status code GitHub
// shows in the delivery log:
//
//   route/method ........ 404 / 405
//   content type ........ 415   (the hook must be set to application/json)
//   size ................ 413
//   required headers .... 400
//   signature ........... 401   checked on raw bytes, before parsing anything
//   JSON ................ 400
//   repository .......... 403   signed, but from a repo this endpoint doesn't serve
//   delivery id ......... 200 duplicate / 409 conflict
//   plan + state ........ 200, or 500 so GitHub marks it failed and it can be redelivered
//
// The response goes back as soon as the plan is stored. The Discord post runs
// afterwards (ctx.waitUntil) so a slow Discord never pushes the response past
// GitHub's 10-second timeout.

import { plan, workflowKey } from "./events.ts";
import type { Notifier } from "./notify.ts";
import { sha256Hex, verifySignature } from "./signature.ts";
import type { Store } from "./store.ts";

export interface Config {
  secrets: string[]; // current first, then the previous one during rotation
  allowedRepo: string; // owner/name
  envName: string; // "sandbox" | "production"
  storeBodies: boolean;
  maxBytes: number;
}
export interface Deps {
  store: Store;
  notifier: Notifier | null;
  now: () => Date;
  log: (entry: Record<string, unknown>) => void;
}
export interface Ctx {
  waitUntil(p: Promise<unknown>): void;
}

const DELIVERY_ID = /^[A-Za-z0-9-]{1,64}$/;

function reply(status: number, body: Record<string, unknown>, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export async function handle(req: Request, cfg: Config, deps: Deps, ctx: Ctx): Promise<Response> {
  const url = new URL(req.url);
  if (url.pathname === "/health") {
    if (req.method !== "GET") return reply(405, { error: "method not allowed" }, { allow: "GET" });
    return reply(200, { ok: true, env: cfg.envName });
  }
  if (url.pathname !== "/github") return reply(404, { error: "not found" });
  if (req.method !== "POST") return reply(405, { error: "method not allowed" }, { allow: "POST" });

  const ctype = (req.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  if (ctype !== "application/json") {
    return reply(415, { error: "content type must be application/json (set it in the webhook settings)" });
  }
  const declared = Number(req.headers.get("content-length") ?? "0");
  if (declared > cfg.maxBytes) return reply(413, { error: "payload too large" });
  const body = new Uint8Array(await req.arrayBuffer());
  if (body.byteLength > cfg.maxBytes) return reply(413, { error: "payload too large" });

  const event = req.headers.get("x-github-event");
  const id = req.headers.get("x-github-delivery");
  const signature = req.headers.get("x-hub-signature-256");
  if (!event || !id || !DELIVERY_ID.test(id)) {
    return reply(400, { error: "missing or malformed X-GitHub-Event / X-GitHub-Delivery" });
  }

  if (!(await verifySignature(cfg.secrets, body, signature))) {
    // Logged, never stored: an unsigned request must not be able to use up a delivery id.
    deps.log({ at: "reject", reason: signature ? "bad signature" : "no signature", event, delivery: id });
    return reply(401, { error: "signature does not match" });
  }

  let payload: Record<string, any>;
  try {
    payload = JSON.parse(new TextDecoder().decode(body));
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) throw new Error("not an object");
  } catch {
    return reply(400, { error: "body is not a JSON object", delivery: id });
  }

  const repo: string | null = payload.repository?.full_name ?? null;
  if (!repo || repo.toLowerCase() !== cfg.allowedRepo.toLowerCase()) {
    deps.log({ at: "reject", reason: "repository not allowed", repo, delivery: id });
    return reply(403, { error: "repository not served by this endpoint", delivery: id });
  }

  const now = deps.now();
  const action: string | null = typeof payload.action === "string" ? payload.action : null;
  let claim;
  try {
    claim = await deps.store.claim({ id, event, action, repo, bodySha: await sha256Hex(body), now });
  } catch (e) {
    deps.log({ at: "error", step: "claim", delivery: id, error: String(e) });
    return reply(500, { error: "storage unavailable", delivery: id });
  }
  if (claim === "duplicate") {
    deps.log({ at: "duplicate", event, delivery: id });
    return reply(200, { outcome: "duplicate", delivery: id });
  }
  if (claim === "conflict") {
    deps.log({ at: "conflict", event, delivery: id });
    return reply(409, { error: "delivery id already used with a different body", delivery: id });
  }

  try {
    if (cfg.storeBodies) {
      await deps.store.savePayload(id, event, signature!, new TextDecoder().decode(body), now);
    }
    const key = event === "workflow_run" ? workflowKey(payload) : null;
    const prev = key ? await deps.store.getWorkflow(key) : null;
    const p = plan(event, payload, prev, cfg.envName);

    if (p.message && deps.notifier) {
      const notifier = deps.notifier;
      const message = p.message;
      // State moves only once the alert is out. If Discord fails, the delivery
      // is marked failed with state unchanged, so a redelivery re-plans the
      // same transition and sends the alert again.
      ctx.waitUntil(
        (async () => {
          const sent = await notifier(message);
          if (sent.ok) {
            if (p.state) await deps.store.putWorkflow(p.state);
            await deps.store.finish(id, p.outcome, `${p.detail}; notified`, deps.now());
          } else {
            await deps.store.finish(id, "failed", `${p.detail}; notify failed: ${sent.error} after ${sent.attempts}`, deps.now());
          }
          deps.log({ at: "notify", delivery: id, ok: sent.ok, status: sent.status, attempts: sent.attempts });
        })().catch((e) => deps.log({ at: "error", step: "notify", delivery: id, error: String(e) })),
      );
      deps.log({ at: "accept", event, action, delivery: id, claim, outcome: p.outcome, detail: p.detail, notify: "queued" });
      return reply(200, { outcome: p.outcome, delivery: id, detail: p.detail, notify: "queued" });
    }

    if (p.state) await deps.store.putWorkflow(p.state);
    const detail = p.message ? `${p.detail}; no notifier configured` : p.detail;
    await deps.store.finish(id, p.outcome, detail, deps.now());
    deps.log({ at: "accept", event, action, delivery: id, claim, outcome: p.outcome, detail });
    return reply(200, { outcome: p.outcome, delivery: id, detail });
  } catch (e) {
    deps.log({ at: "error", step: "process", delivery: id, error: String(e) });
    await deps.store.finish(id, "failed", String(e), deps.now()).catch(() => {});
    return reply(500, { error: "processing failed; safe to redeliver", delivery: id });
  }
}
