CREATE TABLE IF NOT EXISTS tenants (
  tenant_id text PRIMARY KEY,
  status    text NOT NULL CHECK (status IN ('active', 'erased')),
  erased_at timestamptz
);
CREATE TABLE IF NOT EXISTS tenant_keys (
  tenant_id   text PRIMARY KEY REFERENCES tenants,
  wrapped_dek bytea NOT NULL
);
ALTER TABLE tenant_keys ALTER COLUMN wrapped_dek SET STATISTICS 0;
CREATE TABLE IF NOT EXISTS hot_events (
  tenant_id      text NOT NULL,
  event_id       text COLLATE "C" NOT NULL,
  occurred_at_ms bigint NOT NULL,
  customer_key   bytea,
  payload        bytea NOT NULL,
  PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS hot_events_order ON hot_events (tenant_id, occurred_at_ms, event_id);
CREATE INDEX IF NOT EXISTS hot_events_customer ON hot_events (tenant_id, customer_key) WHERE customer_key IS NOT NULL;
ALTER TABLE hot_events ALTER COLUMN payload SET STATISTICS 0;
CREATE TABLE IF NOT EXISTS tombstones (
  tenant_id    text NOT NULL,
  customer_key bytea NOT NULL,
  status       text NOT NULL CHECK (status IN ('pending', 'done')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, customer_key)
);
CREATE TABLE IF NOT EXISTS tenant_cold (
  tenant_id       text PRIMARY KEY REFERENCES tenants,
  cold_until      bigint NOT NULL DEFAULT (-9223372036854775807 - 1),
  snapshot_object text,
  reducer_version text NOT NULL DEFAULT 'v1',
  dirty           boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS cold_manifest (
  tenant_id text NOT NULL,
  day       bigint NOT NULL,
  object    text NOT NULL,
  events    integer NOT NULL,
  bytes     integer NOT NULL,
  PRIMARY KEY (tenant_id, day)
);
CREATE TABLE IF NOT EXISTS garbage (
  object      text PRIMARY KEY,
  tenant_id   text NOT NULL,
  replaced_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- CREATE TABLE IF NOT EXISTS leaves an existing table alone; the grace period
-- must run from the insert, not from the start of the transaction.
ALTER TABLE garbage ALTER COLUMN replaced_at SET DEFAULT clock_timestamp();
CREATE TABLE IF NOT EXISTS customer_days (
  tenant_id    text NOT NULL,
  customer_key bytea NOT NULL,
  day          bigint NOT NULL,
  PRIMARY KEY (tenant_id, customer_key, day)
);
CREATE TABLE IF NOT EXISTS sku_moves (
  tenant_id      text NOT NULL,
  sku_key        bytea NOT NULL,
  occurred_at_ms bigint NOT NULL,
  event_id       text COLLATE "C" NOT NULL,
  line_no        integer NOT NULL,
  value          bytea NOT NULL,
  PRIMARY KEY (tenant_id, sku_key, occurred_at_ms, event_id, line_no)
);
ALTER TABLE sku_moves ALTER COLUMN value SET STATISTICS 0;
CREATE INDEX IF NOT EXISTS sku_moves_event ON sku_moves (tenant_id, event_id);
