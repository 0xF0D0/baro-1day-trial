#!/usr/bin/env bash
# Usage: tier-stats.sh <data-dir>
# Prints "hot=<rows in hot_events> cold=<events in cold buckets> dirty=<dirty tenants>".
set -euo pipefail
DATA="${1:?usage: tier-stats.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
COMPOSE="$(cd "$(dirname "$0")/.." && pwd)/docker-compose.yml"
export TENANTS_FILE="$DATA/tenants.json"
docker compose -f "$COMPOSE" exec -T postgres psql -U postgres -tAc \
  "SELECT 'hot=' || (SELECT count(*) FROM hot_events) || ' cold=' || (SELECT coalesce(sum(events), 0) FROM cold_manifest) || ' dirty=' || (SELECT count(*) FROM tenant_cold WHERE dirty)"
