#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> verify.sh <data-dir>
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: verify.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/$(basename "$DATA")"
python3 "$INFRA/verify.py" --target "${TARGET:-http://localhost:8080}" \
  --tenants "$DATA/tenants.json" --expected "$DATA/expected/v1.json" \
  --responses "$OUT/replay_responses.json" --ranges "$DATA/expected/ranges.json"
