#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> crash.sh <data-dir>
# Replays the data while the worker is repeatedly killed with SIGKILL and its crash points are armed,
# then settles (sweep with grace 0), runs verify.py and the consistency checker, and writes
# part2/out/<data>/crash-report.txt. Exits 0 only if both pass.
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: crash.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../docker-compose.yml"
NAME="$(basename "$DATA")"
OUT="$HERE/../out/$NAME"
mkdir -p "$HERE/../out/secrets" "$OUT"
OUT="$(cd "$OUT" && pwd)"

export TENANTS_FILE="$DATA/tenants.json"
export FLUSH_MARGIN="${FLUSH_MARGIN:-1h}"
export FLUSH_INTERVAL="${FLUSH_INTERVAL:-2s}"
export SWEEP_INTERVAL="${SWEEP_INTERVAL:-10s}"
export GARBAGE_GRACE="${GARBAGE_GRACE:-20s}"
export CRASH_POINTS="${CRASH_POINTS:-flush.after_bucket,flush.after_snapshot,flush.before_commit,rebuild.after_bucket,rebuild.after_snapshot,rebuild.before_commit}"
export CRASH_PROBABILITY="${CRASH_PROBABILITY:-0.02}"
KILL_MIN_S="${KILL_MIN_S:-3}"
KILL_MAX_S="${KILL_MAX_S:-10}"
CHAOS_TAIL_S="${CHAOS_TAIL_S:-30}"
SETTLE_TIMEOUT_S="${SETTLE_TIMEOUT_S:-180}"

KILLS_FILE="$OUT/kills.count"
LOOP_PID=""
stop_loop() {
  if [ -n "$LOOP_PID" ]; then
    kill "$LOOP_PID" 2>/dev/null || true
    wait "$LOOP_PID" 2>/dev/null || true
    LOOP_PID=""
  fi
}
trap stop_loop EXIT INT TERM

dc() { docker compose -f "$COMPOSE" "$@"; }

dc down -v
dc up -d --build --wait

: > "$KILLS_FILE"
(
  while true; do
    sleep $((KILL_MIN_S + RANDOM % (KILL_MAX_S - KILL_MIN_S + 1)))
    if dc kill -s KILL worker >/dev/null 2>&1; then
      echo k >> "$KILLS_FILE"
    fi
    dc start worker >/dev/null 2>&1 || true
  done
) &
LOOP_PID=$!

"$HERE/replay.sh" "$DATA" 2>&1 | tee "$OUT/replay-chaos.txt"
sleep "$CHAOS_TAIL_S"
stop_loop

KILLS="$(wc -l < "$KILLS_FILE" | tr -d ' ')"
dc logs --no-color worker > "$OUT/worker-chaos.log" 2>&1 || true
point_hits() { grep -c "\"msg\":\"crash point\".*\"point\":\"$1\"" "$OUT/worker-chaos.log" || true; }
REBUILDS="$(grep -c '"msg":"tenant rebuilt"' "$OUT/worker-chaos.log" || true)"
TICKS="$(grep -c '"msg":"flush tick"' "$OUT/worker-chaos.log" || true)"

# Settle: disarmed, sweeping with grace 0, until one sweep completes.
CRASH_POINTS= CRASH_PROBABILITY=0 GARBAGE_GRACE=0s dc up -d worker
SETTLED=0
deadline=$((SECONDS + SETTLE_TIMEOUT_S))
while [ "$SECONDS" -lt "$deadline" ]; do
  if dc logs --no-color worker 2>&1 | grep -q '"msg":"sweep done"'; then SETTLED=1; break; fi
  sleep 2
done
dc stop worker || true

rc=0
if [ "$SETTLED" -ne 1 ]; then
  echo "settle: no sweep completed within ${SETTLE_TIMEOUT_S}s" | tee "$OUT/settle.txt"
  rc=1
fi
vrc=0
"$HERE/verify.sh" "$DATA" 2>&1 | tee "$OUT/verify-chaos.txt" || vrc=${PIPESTATUS[0]}
STATS="$("$HERE/tier-stats.sh" "$DATA" || true)"
crc=0
DATA_DIR="$DATA" dc run --rm check -deliveries /data/deliveries.jsonl.gz \
  -responses "/out/$NAME/replay_responses.json" 2>&1 | tee "$OUT/check-chaos.txt" || crc=${PIPESTATUS[0]}
[ "$vrc" -eq 0 ] && [ "$crc" -eq 0 ] || rc=1

{
  echo "== crash test report =="
  echo "settings: FLUSH_MARGIN=$FLUSH_MARGIN FLUSH_INTERVAL=$FLUSH_INTERVAL SWEEP_INTERVAL=$SWEEP_INTERVAL GARBAGE_GRACE=$GARBAGE_GRACE"
  echo "settings: CRASH_POINTS=$CRASH_POINTS CRASH_PROBABILITY=$CRASH_PROBABILITY"
  echo "settings: KILL_MIN_S=$KILL_MIN_S KILL_MAX_S=$KILL_MAX_S CHAOS_TAIL_S=$CHAOS_TAIL_S SETTLE_TIMEOUT_S=$SETTLE_TIMEOUT_S"
  echo "external kills (successful): $KILLS"
  echo "crash point hits:"
  IFS=, read -ra pts <<< "$CRASH_POINTS"
  for p in "${pts[@]}"; do echo "  $p: $(point_hits "$p")"; done
  echo "tenant rebuilt lines: $REBUILDS"
  echo "flush tick lines: $TICKS"
  echo "settled: $([ "$SETTLED" -eq 1 ] && echo yes || echo NO)"
  echo "replay:"
  grep -E '^done:' "$OUT/replay-chaos.txt" | sed 's/^/  /' || true
  echo "verify.py:"
  grep -E '^(state:|isolation:|ranges:|PASS|FAIL)' "$OUT/verify-chaos.txt" | sed 's/^/  /' || true
  echo "tier-stats: $STATS"
  echo "checker:"
  grep -E '^(check:|CHECK )|lost=' "$OUT/check-chaos.txt" | sed 's/^/  /' || true
  echo "result: $([ "$rc" -eq 0 ] && echo PASS || echo FAIL)"
} > "$OUT/crash-report.txt"
cat "$OUT/crash-report.txt"
exit "$rc"
