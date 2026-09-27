// Delivery log and workflow state, written against the small slice of the D1
// API this needs (prepare -> bind -> first/run). Tests run the same SQL on
// node:sqlite through an adapter, so the statements are checked on a real
// SQLite engine rather than a hand-written fake.

export interface Stmt {
  bind(...values: unknown[]): Stmt;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  run(): Promise<unknown>;
}
export interface Db {
  prepare(sql: string): Stmt;
}

export type Claim = "new" | "retry" | "duplicate" | "conflict";
export type Status = "received" | "processed" | "ignored" | "failed";

export interface WorkflowState {
  key: string;
  runId: number;
  runNumber: number;
  runAttempt: number;
  conclusion: string;
  updatedAt: string;
}

// A delivery that started but never finished (the worker died mid-request) can
// be claimed again after this long. Anything that finished cleanly never can.
export const STUCK_AFTER_MS = 5 * 60 * 1000;

export class Store {
  private db: Db;
  constructor(db: Db) {
    this.db = db;
  }

  /**
   * Record a verified delivery and decide whether to process it.
   *   new       first time this delivery id has been seen
   *   retry     seen before, but it failed or got stuck, so run it again
   *   duplicate seen and finished; GitHub redelivered it or someone replayed it
   *   conflict  same id, different body: not a redelivery, something is wrong
   * The primary key makes this safe under concurrent identical deliveries:
   * exactly one INSERT wins.
   */
  async claim(d: {
    id: string;
    event: string;
    action: string | null;
    repo: string | null;
    bodySha: string;
    now: Date;
  }): Promise<Claim> {
    const now = d.now.toISOString();
    const stuckBefore = new Date(d.now.getTime() - STUCK_AFTER_MS).toISOString();
    const row = await this.db
      .prepare(
        `INSERT INTO deliveries (id, event, action, repo, body_sha256, received_at, status, attempts)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'received', 1)
         ON CONFLICT(id) DO UPDATE SET
           status = 'received', attempts = deliveries.attempts + 1,
           received_at = ?6, detail = NULL, finished_at = NULL
         WHERE deliveries.body_sha256 = ?5
           AND (deliveries.status = 'failed'
                OR (deliveries.status = 'received' AND deliveries.received_at < ?7))
         RETURNING attempts`,
      )
      .bind(d.id, d.event, d.action, d.repo, d.bodySha, now, stuckBefore)
      .first<{ attempts: number }>();
    if (row) return row.attempts > 1 ? "retry" : "new";
    const prior = await this.db
      .prepare(`SELECT body_sha256 FROM deliveries WHERE id = ?1`)
      .bind(d.id)
      .first<{ body_sha256: string }>();
    return prior && prior.body_sha256 !== d.bodySha ? "conflict" : "duplicate";
  }

  async finish(id: string, status: Status, detail: string, now: Date): Promise<void> {
    await this.db
      .prepare(`UPDATE deliveries SET status = ?2, detail = ?3, finished_at = ?4 WHERE id = ?1`)
      .bind(id, status, detail.slice(0, 500), now.toISOString())
      .run();
  }

  async getWorkflow(key: string): Promise<WorkflowState | null> {
    const r = await this.db
      .prepare(
        `SELECT key, run_id AS runId, run_number AS runNumber, run_attempt AS runAttempt,
                conclusion, updated_at AS updatedAt
         FROM workflow_state WHERE key = ?1`,
      )
      .bind(key)
      .first<WorkflowState>();
    return r ?? null;
  }

  /** Only moves forward: an older run arriving late never overwrites a newer one. */
  async putWorkflow(s: WorkflowState): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO workflow_state (key, run_id, run_number, run_attempt, conclusion, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(key) DO UPDATE SET
           run_id = ?2, run_number = ?3, run_attempt = ?4, conclusion = ?5, updated_at = ?6
         WHERE (?3 > workflow_state.run_number)
            OR (?3 = workflow_state.run_number AND ?4 > workflow_state.run_attempt)`,
      )
      .bind(s.key, s.runId, s.runNumber, s.runAttempt, s.conclusion, s.updatedAt)
      .run();
  }

  /** Sandbox only: keep the raw body and GitHub's signature so real deliveries become fixtures. */
  async savePayload(id: string, event: string, signature: string, body: string, now: Date): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO payloads (id, event, signature, body, received_at) VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT(id) DO NOTHING`,
      )
      .bind(id, event, signature, body, now.toISOString())
      .run();
  }
}
