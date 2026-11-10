#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> replay.sh <data-dir>
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: replay.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/$(basename "$DATA")"
mkdir -p "$OUT"
python3 "$INFRA/replay.py" --target "${TARGET:-http://localhost:8080}" \
  --tenants "$DATA/tenants.json" --deliveries "$DATA/deliveries.jsonl.gz" \
  --responses-out "$OUT/replay_responses.json"
