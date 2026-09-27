-- D1 schema for the webhook receiver. Apply per environment:
--   npx wrangler d1 execute br-hooks-sandbox    --remote --file schema.sql --env sandbox
--   npx wrangler d1 execute br-hooks-production --remote --file schema.sql --env production

-- One row per verified delivery. Unsigned or badly signed requests never get
-- here, so nobody without the secret can claim a delivery id.
CREATE TABLE IF NOT EXISTS deliveries (
  id           TEXT PRIMARY KEY,          -- X-GitHub-Delivery
  event        TEXT NOT NULL,             -- X-GitHub-Event
  action       TEXT,
  repo         TEXT,
  body_sha256  TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  attempts     INTEGER NOT NULL DEFAULT 1,
  status       TEXT NOT NULL,             -- received | processed | ignored | failed
  detail       TEXT,
  finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS deliveries_received ON deliveries (received_at);

-- Last known result per workflow and branch, so alerts fire on a change
-- (passing -> failing, failing -> passing) rather than on every run.
CREATE TABLE IF NOT EXISTS workflow_state (
  key          TEXT PRIMARY KEY,          -- <workflow_id>:<branch>
  run_id       INTEGER NOT NULL,
  run_number   INTEGER NOT NULL,
  run_attempt  INTEGER NOT NULL,
  conclusion   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

-- Sandbox only (STORE_BODIES = "1"): raw deliveries, exported as test fixtures.
CREATE TABLE IF NOT EXISTS payloads (
  id           TEXT PRIMARY KEY,
  event        TEXT NOT NULL,
  signature    TEXT NOT NULL,
  body         TEXT NOT NULL,
  received_at  TEXT NOT NULL
);
