#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> crash.sh <data-dir>
# Replays the data while the worker is repeatedly killed with SIGKILL and its crash points are armed,
# then leaves the store as the last kill left it and checks it (pre-settle), settles (sweep with
# grace 0), runs verify.py and the consistency checker, and writes part2/out/<data>/crash-report.txt.
# Exits 0 only if verify.py, the pre-settle check and the full check all pass.
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
export CRASH_PROBABILITY="${CRASH_PROBABILITY:-0.002}"
KILL_MIN_S="${KILL_MIN_S:-3}"
KILL_MAX_S="${KILL_MAX_S:-10}"
CHAOS_TAIL_S="${CHAOS_TAIL_S:-30}"
SETTLE_TIMEOUT_S="${SETTLE_TIMEOUT_S:-180}"

if ! [[ "$KILL_MIN_S" =~ ^[0-9]+$ && "$KILL_MAX_S" =~ ^[0-9]+$ ]] || [ "$KILL_MIN_S" -lt 1 ] || [ "$KILL_MAX_S" -lt "$KILL_MIN_S" ]; then
  echo "crash.sh: need KILL_MAX_S >= KILL_MIN_S >= 1 (got KILL_MIN_S=$KILL_MIN_S KILL_MAX_S=$KILL_MAX_S)" >&2
  exit 2
fi

KILLS_FILE="$OUT/kills.count"
LOOP_PID=""
stop_loop() {
  if [ -n "$LOOP_PID" ]; then
    kill "$LOOP_PID" 2>/dev/null || true
    wait "$LOOP_PID" 2>/dev/null || true
    LOOP_PID=""
  fi
}
trap stop_loop EXIT
trap 'stop_loop; exit 130' INT
trap 'stop_loop; exit 143' TERM

dc() { docker compose -f "$COMPOSE" "$@"; }

dc down -v
dc up -d --build --wait

: > "$KILLS_FILE"
(
  while true; do
    sleep $((KILL_MIN_S + RANDOM % (KILL_MAX_S - KILL_MIN_S + 1)))
    # Count a kill only when the worker is up: running and not restarting.
    cid="$(dc ps -q worker 2>/dev/null || true)"
    if [ -n "$cid" ] && [ "$(docker inspect -f '{{.State.Running}} {{.State.Restarting}}' "$cid" 2>/dev/null || true)" = "true false" ]; then
      if dc kill -s KILL worker >/dev/null 2>&1; then
        echo k >> "$KILLS_FILE"
      fi
    fi
    dc start worker >/dev/null 2>&1 || true
  done
) &
LOOP_PID=$!

"$HERE/replay.sh" "$DATA" 2>&1 | tee "$OUT/replay-chaos.txt"
sleep "$CHAOS_TAIL_S"
stop_loop

# Leave the store exactly as a crash leaves it: one last kill, then stop the worker.
dc kill -s KILL worker >/dev/null 2>&1 || true
dc stop worker >/dev/null 2>&1 || true

KILLS="$(wc -l < "$KILLS_FILE" | tr -d ' ')"
dc logs --no-color worker > "$OUT/worker-chaos.log" 2>&1 || true
point_hits() { grep -c "\"msg\":\"crash point\".*\"point\":\"$1\"" "$OUT/worker-chaos.log" || true; }
REBUILDS="$(grep -c '"msg":"tenant rebuilt"' "$OUT/worker-chaos.log" || true)"
TICKS="$(grep -c '"msg":"flush tick"' "$OUT/worker-chaos.log" || true)"
SWEEPS="$(grep -c '"msg":"sweep done"' "$OUT/worker-chaos.log" || true)"

dc --profile tools build check
run_check() { # run_check <extra checker flags...>
  DATA_DIR="$DATA" dc run --rm -T check "$@" -deliveries /data/deliveries.jsonl.gz \
    -responses "/out/$NAME/replay_responses.json"
}

# Pre-settle: the store as the last kill left it.
STATS_PRE="$("$HERE/tier-stats.sh" "$DATA" || true)"
prc=0
run_check -unsettled 2>&1 | tee "$OUT/check-presettle.txt" || prc=${PIPESTATUS[0]}

# Settle: disarmed, sweeping with grace 0, until one sweep completes.
CRASH_POINTS= CRASH_PROBABILITY=0 GARBAGE_GRACE=0s dc up -d --force-recreate worker
SETTLED=0
deadline=$((SECONDS + SETTLE_TIMEOUT_S))
while [ "$SECONDS" -lt "$deadline" ]; do
  if dc logs --no-color worker 2>&1 | grep -q '"msg":"sweep done"'; then SETTLED=1; break; fi
  sleep 2
done
dc logs --no-color worker > "$OUT/worker-settle.log" 2>&1 || true
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
run_check 2>&1 | tee "$OUT/check-chaos.txt" || crc=${PIPESTATUS[0]}
[ "$vrc" -eq 0 ] && [ "$prc" -eq 0 ] && [ "$crc" -eq 0 ] || rc=1

NEVER=""
IFS=, read -ra pts <<< "$CRASH_POINTS"
for p in "${pts[@]}"; do
  [ -n "$p" ] && [ "$(point_hits "$p")" -eq 0 ] && NEVER="${NEVER:+$NEVER, }$p"
done

{
  echo "== crash test report =="
  echo "settings: FLUSH_MARGIN=$FLUSH_MARGIN FLUSH_INTERVAL=$FLUSH_INTERVAL SWEEP_INTERVAL=$SWEEP_INTERVAL GARBAGE_GRACE=$GARBAGE_GRACE"
  echo "settings: CRASH_POINTS=$CRASH_POINTS CRASH_PROBABILITY=$CRASH_PROBABILITY"
  echo "settings: KILL_MIN_S=$KILL_MIN_S KILL_MAX_S=$KILL_MAX_S CHAOS_TAIL_S=$CHAOS_TAIL_S SETTLE_TIMEOUT_S=$SETTLE_TIMEOUT_S"
  echo "external kills (worker running, counted): $KILLS"
  echo "crash point hits:"
  for p in "${pts[@]}"; do echo "  $p: $(point_hits "$p")"; done
  echo "points never hit: ${NEVER:-none}"
  echo "tenant rebuilt lines: $REBUILDS"
  echo "flush tick lines: $TICKS"
  echo "sweep done lines (chaos log): $SWEEPS"
  echo "settled: $([ "$SETTLED" -eq 1 ] && echo yes || echo NO)"
  echo "replay:"
  grep -E '^done:' "$OUT/replay-chaos.txt" | sed 's/^/  /' || true
  echo "verify.py:"
  grep -E '^(state:|isolation:|ranges:|PASS|FAIL)' "$OUT/verify-chaos.txt" | sed 's/^/  /' || true
  echo "tier-stats (pre-settle): $STATS_PRE"
  echo "tier-stats (post-settle): $STATS"
  echo "pre-settle check (-unsettled):"
  grep -E '^(check:|CHECK )|lost=' "$OUT/check-presettle.txt" | sed 's/^/  /' || true
  echo "full check:"
  grep -E '^(check:|CHECK )|lost=' "$OUT/check-chaos.txt" | sed 's/^/  /' || true
  echo "result: $([ "$rc" -eq 0 ] && echo PASS || echo FAIL)"
} > "$OUT/crash-report.txt"
cat "$OUT/crash-report.txt"
exit "$rc"
