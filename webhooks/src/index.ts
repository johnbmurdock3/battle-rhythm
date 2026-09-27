// Cloudflare Worker entry point. Everything testable lives in handler.ts; this
// file only turns bindings and secrets into a Config and Deps.

import { handle, type Config } from "./handler.ts";
import { discordNotifier } from "./notify.ts";
import { Store } from "./store.ts";

export interface Env {
  DB: D1Database;
  GITHUB_WEBHOOK_SECRET: string; // wrangler secret put
  GITHUB_WEBHOOK_SECRET_PREVIOUS?: string; // only while rotating
  DISCORD_WEBHOOK_URL?: string; // wrangler secret put; unset = no alerts
  ALLOWED_REPO: string; // [vars] in wrangler.toml
  ENV_NAME: string;
  STORE_BODIES?: string; // "1" in sandbox only
}

const MAX_BYTES = 2 * 1024 * 1024;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cfg: Config = {
      secrets: [env.GITHUB_WEBHOOK_SECRET ?? "", env.GITHUB_WEBHOOK_SECRET_PREVIOUS ?? ""],
      allowedRepo: env.ALLOWED_REPO,
      envName: env.ENV_NAME,
      storeBodies: env.STORE_BODIES === "1",
      maxBytes: MAX_BYTES,
    };
    if (!env.GITHUB_WEBHOOK_SECRET) {
      // Fail closed. A receiver with no secret would accept anything.
      return new Response(JSON.stringify({ error: "receiver not configured" }), { status: 503 });
    }
    return handle(
      req,
      cfg,
      {
        store: new Store(env.DB),
        notifier: env.DISCORD_WEBHOOK_URL ? discordNotifier(env.DISCORD_WEBHOOK_URL) : null,
        now: () => new Date(),
        log: (entry) => console.log(JSON.stringify({ env: env.ENV_NAME, ...entry })),
      },
      ctx,
    );
  },
};
