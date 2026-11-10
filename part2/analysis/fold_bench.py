"""Rough cost of decoding and folding 1M canonical events (t_0000 replicated with new ids).

Usage: python3 part2/analysis/fold_bench.py <infrastructure dir>
Replicated payloads compress better than real data, so the zlib number is optimistic.
"""
import contextlib, io, json, os, runpy, time, zlib

with contextlib.redirect_stdout(io.StringIO()):
    ns = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle.py"), run_name="oracle")
store, reducer = ns["store"], ns["reducer"]

base = list(store["t_0000"].values())
big, k = [], 0
while len(big) < 1_000_000:
    big.extend(dict(e, event_id=f"{e['event_id']}_{k}") for e in base)
    k += 1
big = big[:1_000_000]
blob = [json.dumps(e, separators=(",", ":")) for e in big]
t0 = time.perf_counter(); evs = [json.loads(s) for s in blob]
t1 = time.perf_counter(); reducer.fold("t_0000", evs)
t2 = time.perf_counter(); raw = "\n".join(blob).encode(); c = zlib.compress(raw, 6)
t3 = time.perf_counter()
print(f"1M events: json.loads {t1-t0:.2f}s, reducer.fold {t2-t1:.2f}s, zlib-6 {t3-t2:.2f}s")
print(f"bytes/event: raw json {len(raw)/1e6:.1f}, zlib-6 {len(c)/1e6:.1f}")
