#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> e2e.sh <data-dir>
# Rebuilds the stack from empty storage, replays the data and verifies. Exits with verify.py's code.
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: e2e.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../docker-compose.yml"
# Create the bind-mounted secrets dir as the user; otherwise a rootful daemon creates it as root.
mkdir -p "$HERE/../out/secrets"
export TENANTS_FILE="$DATA/tenants.json"
export FLUSH_INTERVAL="${FLUSH_INTERVAL:-2s}"
docker compose -f "$COMPOSE" down -v
docker compose -f "$COMPOSE" up -d --build --wait
"$HERE/replay.sh" "$DATA"
rc=0
"$HERE/verify.sh" "$DATA" || rc=$?
"$HERE/tier-stats.sh" "$DATA" || true
exit "$rc"
