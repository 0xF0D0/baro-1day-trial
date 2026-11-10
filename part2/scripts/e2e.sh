#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> e2e.sh <data-dir>
# Rebuilds the stack from empty storage, replays the data and verifies. Exits with verify.py's code.
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: e2e.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../docker-compose.yml"
export TENANTS_FILE="$DATA/tenants.json"
docker compose -f "$COMPOSE" down -v
docker compose -f "$COMPOSE" up -d --build --wait
"$HERE/replay.sh" "$DATA"
"$HERE/verify.sh" "$DATA"
