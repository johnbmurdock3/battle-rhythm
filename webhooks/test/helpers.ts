import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { handle, type Config, type Ctx, type Deps } from "../src/handler.ts";
import type { Notifier, SendResult } from "../src/notify.ts";
import { sign } from "../src/signature.ts";
import { Store, type Db, type Stmt } from "../src/store.ts";

const HERE = new URL(".", import.meta.url);
export const SECRET = "test-secret-not-a-real-one";
export const REPO = "johnbmurdock3/battle-rhythm";

/** The D1 slice the Store uses, backed by a real SQLite database in memory. */
export function sqliteDb(): Db {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../schema.sql", HERE), "utf8"));
  return {
    prepare(sql: string): Stmt {
      const st = db.prepare(sql);
      let values: unknown[] = [];
      const stmt: Stmt = {
        bind(...v: unknown[]) {
          values = v;
          return stmt;
        },
        async first<T>() {
          return ((st.get(...(values as any[])) as T) ?? null) as T | null;
        },
        async run() {
          return st.run(...(values as any[]));
        },
      };
      return stmt;
    },
  };
}

export function fixture(name: string): string {
  return readFileSync(new URL(`fixtures/${name}.json`, HERE), "utf8");
}

export interface Harness {
  store: Store;
  sent: string[];
  logs: Record<string, unknown>[];
  pending: Promise<unknown>[];
  clock: { t: number };
  notifyResult: SendResult;
  call(req: Request): Promise<Response>;
  deliver(event: string, body: string, opts?: { id?: string; secret?: string; headers?: Record<string, string> }): Promise<Response>;
  settle(): Promise<void>;
}

export function harness(over: Partial<Config> = {}, withNotifier = true): Harness {
  const store = new Store(sqliteDb());
  const h: Harness = {
    store,
    sent: [],
    logs: [],
    pending: [],
    clock: { t: Date.parse("2026-09-27T06:00:00Z") },
    notifyResult: { ok: true, status: 204, attempts: 1 },
    async call(req) {
      return handle(req, cfg, deps, ctx);
    },
    async deliver(event, body, opts = {}) {
      const id = opts.id ?? crypto.randomUUID();
      const headers: Record<string, string> = {
        "content-type": "application/json",
        "x-github-event": event,
        "x-github-delivery": id,
        "x-hub-signature-256": await sign(opts.secret ?? SECRET, body),
        "user-agent": "GitHub-Hookshot/test",
        ...opts.headers,
      };
      for (const [k, v] of Object.entries(headers)) if (v === "") delete headers[k];
      return h.call(new Request("https://hooks.test/github", { method: "POST", headers, body }));
    },
    async settle() {
      while (h.pending.length) await h.pending.shift();
    },
  };
  const notifier: Notifier = async (text) => {
    if (h.notifyResult.ok) h.sent.push(text);
    return h.notifyResult;
  };
  const cfg: Config = { secrets: [SECRET], allowedRepo: REPO, envName: "test", storeBodies: false, maxBytes: 64 * 1024, ...over };
  const deps: Deps = {
    store,
    notifier: withNotifier ? notifier : null,
    now: () => new Date(h.clock.t),
    log: (e) => h.logs.push(e),
  };
  const ctx: Ctx = { waitUntil: (p) => h.pending.push(p) };
  return h;
}

export async function json(res: Response): Promise<Record<string, any>> {
  return (await res.json()) as Record<string, any>;
}
