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
