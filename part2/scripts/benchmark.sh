#!/usr/bin/env bash
# Usage: INFRA=<supplied infrastructure dir> benchmark.sh <data-dir>
# Brings the stack up from scratch, replays the data, waits for the worker to settle, verifies,
# measures read latency through the load balancer, collects storage and memory numbers, and writes
# part2/out/<data>/benchmark.txt. Exits 0 only if verify and the latency run both succeed.
# Customer IDs are never printed: only summary lines of each tool are kept.
set -euo pipefail
: "${INFRA:?set INFRA to the supplied infrastructure directory}"
DATA="${1:?usage: benchmark.sh <data-dir>}"
DATA="$(cd "$DATA" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../docker-compose.yml"
NAME="$(basename "$DATA")"
OUT="$HERE/../out/$NAME"
mkdir -p "$HERE/../out/secrets" "$OUT"
OUT="$(cd "$OUT" && pwd)"

export TENANTS_FILE="$DATA/tenants.json"
export FLUSH_INTERVAL="${FLUSH_INTERVAL:-10s}"
SETTLE_TIMEOUT_S="${SETTLE_TIMEOUT_S:-600}"
ROUNDS="${ROUNDS:-5}"
CONCURRENCY="${CONCURRENCY:-8}"

dc() { docker compose -f "$COMPOSE" "$@"; }

dc down -v
dc up -d --build --wait

rc=0
fail() { echo "benchmark: $*" >&2; rc=1; }

# 2. Ingest throughput from the replay's own summary line.
src=0
"$HERE/replay.sh" "$DATA" > "$OUT/bench-replay.txt" 2>&1 || src=$?
REPLAY_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DONE_LINE="$(grep -E '^done:' "$OUT/bench-replay.txt" | tail -n 1 || true)"
if [ "$src" -ne 0 ] || [ -z "$DONE_LINE" ]; then fail "replay failed (exit $src)"; fi

# 3. Settle: a flush tick that moved nothing, among ticks logged after the replay ended.
# The first tick logged after the replay may have started before it ended, so it is skipped.
SETTLED=0
SETTLE_S=""
if [ "$rc" -eq 0 ]; then
  t0=$SECONDS
  deadline=$((SECONDS + SETTLE_TIMEOUT_S))
  while [ "$SECONDS" -lt "$deadline" ]; do
    # Capture first and match afterwards: grep -q would close the pipe early, and pipefail would
    # turn the resulting SIGPIPE into a false "not settled".
    ticks="$(dc logs --no-color --since "$REPLAY_END" worker 2>&1 | grep '"msg":"flush tick"' || true)"
    if [ "$(printf '%s\n' "$ticks" | tail -n +2 | grep -c '"days_flushed":0[,}]' || true)" -gt 0 ]; then
      SETTLED=1
      SETTLE_S=$((SECONDS - t0))
      break
    fi
    sleep 2
  done
  if [ "$SETTLED" -ne 1 ]; then fail "worker did not settle within ${SETTLE_TIMEOUT_S}s"; fi
fi

# 4. Verify.
vrc=0
VERIFY_LINES=""
if [ "$rc" -eq 0 ]; then
  "$HERE/verify.sh" "$DATA" > "$OUT/bench-verify.txt" 2>&1 || vrc=$?
  VERIFY_LINES="$(grep -E '^(state:|isolation:|ranges:|PASS|FAIL)' "$OUT/bench-verify.txt" || true)"
  if [ "$vrc" -ne 0 ]; then fail "verify failed (exit $vrc)"; fi
fi

# 5. Latency.
brc=0
BENCH_LINES=""
if [ "$rc" -eq 0 ]; then
  dc --profile tools build bench
  DATA_DIR="$DATA" dc run --rm -T bench -tenants /config/tenants.json \
    -deliveries /data/deliveries.jsonl.gz -rounds "$ROUNDS" -concurrency "$CONCURRENCY" \
    > "$OUT/bench-latency.txt" 2>&1 || brc=$?
  BENCH_LINES="$(grep -E '^(state |range_cold |range_hot |slowest_state |skipped_erased=|errors=)' "$OUT/bench-latency.txt" || true)"
  if [ "$brc" -ne 0 ]; then fail "bench failed (exit $brc)"; fi
fi

# 6. Storage numbers from Postgres.
SQL="SELECT
  coalesce(round((SELECT pg_total_relation_size('hot_events')::numeric / nullif(count(*), 0) FROM hot_events), 1)::text, 'n/a'),
  (SELECT count(*) FROM hot_events),
  coalesce(round((SELECT sum(bytes)::numeric / nullif(sum(events), 0) FROM cold_manifest), 1)::text, 'n/a'),
  (SELECT coalesce(sum(events), 0) FROM cold_manifest),
  coalesce(round((pg_total_relation_size('customer_days') + pg_total_relation_size('sku_moves'))::numeric
    / nullif((SELECT sum(events) FROM cold_manifest), 0), 1)::text, 'n/a')"
STORAGE="$(dc exec -T postgres psql -U postgres -tA -F '|' -c "$SQL" 2>/dev/null || echo 'n/a|n/a|n/a|n/a|n/a')"
IFS='|' read -r HOT_BPE HOT_N COLD_BPE COLD_N IDX_BPE <<< "$STORAGE"

# 7. Peak memory per service (cgroup v2 memory.peak), in MiB.
mem() {
  local v
  v="$(dc exec -T "$1" cat /sys/fs/cgroup/memory.peak 2>/dev/null | tr -d '\r\n' || true)"
  if [[ "$v" =~ ^[0-9]+$ ]]; then
    awk -v b="$v" 'BEGIN { printf "%.1f MiB", b / 1048576 }'
  else
    echo "n/a"
  fi
}
MEM=""
for s in api1 api2 worker postgres minio; do
  MEM="$MEM  $s: $(mem "$s")"$'\n'
done

DOCKER_MEM_B="$(docker info --format '{{.MemTotal}}' 2>/dev/null || true)"
DOCKER_MEM="n/a"
[ -n "$DOCKER_MEM_B" ] && DOCKER_MEM="$(awk -v b="$DOCKER_MEM_B" 'BEGIN { printf "%.1f GiB", b / 1073741824 }')"
DOCKER_CPU="$(docker info --format '{{.NCPU}}' 2>/dev/null || true)"
DOCKER_CPU="${DOCKER_CPU:-n/a}"

# 8. Report.
{
  echo "== benchmark report =="
  echo "data: $NAME"
  echo "machine: $(uname -m), docker cpus: $DOCKER_CPU, docker memory: $DOCKER_MEM"
  echo "settings: FLUSH_INTERVAL=$FLUSH_INTERVAL SETTLE_TIMEOUT_S=$SETTLE_TIMEOUT_S ROUNDS=$ROUNDS CONCURRENCY=$CONCURRENCY (other settings are the compose defaults)"
  echo
  echo "ingest throughput: ${DONE_LINE:-not measured}"
  echo "  method: replay.py's own summary line (deliveries per second through the load balancer)."
  echo "settle: $([ "$SETTLED" -eq 1 ] && echo "worker idle ${SETTLE_S}s after replay" || echo "not settled")"
  echo "  method: first flush tick logged after the replay ended with days_flushed=0 (the first tick after the replay is skipped)."
  echo
  echo "read latency (ms, through the load balancer):"
  echo "${BENCH_LINES:-not measured}" | sed 's/^/  /'
  echo "  method: cmd/bench, $ROUNDS rounds x all tenants, concurrency $CONCURRENCY; state, then the first page of the first-day (cold) and last-day (hot) range of the deliveries; nearest-rank percentiles; 410 on the first state read skips the tenant."
  echo
  echo "storage:"
  echo "  hot bytes per event: $HOT_BPE (hot events: $HOT_N)"
  echo "    method: pg_total_relation_size('hot_events') / count(*) from hot_events."
  echo "  cold bytes per event: $COLD_BPE (cold events: $COLD_N)"
  echo "    method: sum(bytes) / sum(events) from cold_manifest."
  echo "  index bytes per cold event: $IDX_BPE"
  echo "    method: (pg_total_relation_size('customer_days') + pg_total_relation_size('sku_moves')) / sum(events) from cold_manifest."
  echo
  echo "peak memory:"
  printf '%s' "$MEM"
  echo "  method: cat /sys/fs/cgroup/memory.peak in each container, in MiB; n/a if unreadable."
  echo
  echo "verify.py:"
  echo "${VERIFY_LINES:-not run}" | sed 's/^/  /'
  echo "result: $([ "$rc" -eq 0 ] && echo PASS || echo FAIL)"
} > "$OUT/benchmark.txt"
cat "$OUT/benchmark.txt"
exit "$rc"
