"""In-memory oracle: checks that our reading of SPEC.md reproduces expected/v1.json and ranges.json.

Usage: python3 part2/analysis/oracle.py <infrastructure dir> [<data dir>]
Analysis only, not the service. Standard library plus the supplied reducer.py.
"""
import base64, collections, gzip, hashlib, hmac, json, sys
from datetime import datetime, timezone

infra = sys.argv[1]
data_dir = sys.argv[2] if len(sys.argv) > 2 else infra + "/data"
sys.path.insert(0, infra)
import reducer  # noqa: E402

meta = json.load(open(f"{data_dir}/tenants.json"))
by_acct = {t["vendor_a"]["account"]: t for t in meta["tenants"]}
by_shop = {t["vendor_b"]["shop_domain"]: t for t in meta["tenants"]}
expected = json.load(open(f"{data_dir}/expected/v1.json"))
ranges = json.load(open(f"{data_dir}/expected/ranges.json"))


def iso_ms(s):
    dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp()) * 1000 + dt.microsecond // 1000


def normalize(vendor, b, tid):
    if vendor == "a":
        kind, obj = b["type"], b["data"]["object"]
        base = {"event_id": b["id"], "tenant_id": tid, "occurred_at_ms": b["created"]}
        if kind == "order.created":
            c = obj["customer"]
            return dict(base, type=kind, customer_id=c["id"], data={
                "order_id": obj["order_id"],
                "lines": [{"sku": l["sku"], "qty": l["quantity"], "unit_cents": l["unit_amount"]} for l in obj["line_items"]],
                "email": c["email"], "name": c["name"]})
        if kind == "charge.refunded":
            return dict(base, type="order.refunded", customer_id=obj["customer_id"],
                        data={"order_id": obj["order_id"], "amount_cents": obj["amount_refunded"]})
        if kind == "ads.metric":
            return dict(base, type="ad.metric", customer_id=None, data={
                "campaign_id": obj["campaign_id"], "spend_cents": obj["spend"],
                "impressions": obj["impressions"], "clicks": obj["clicks"]})
        return dict(base, type=kind, customer_id=obj.get("customer_id"), data=obj)
    kind, p = b["event"], b["payload"]
    base = {"event_id": b["event_uuid"], "tenant_id": tid, "occurred_at_ms": iso_ms(b["timestamp"])}
    if kind == "shipment.updated":
        return dict(base, type=kind, customer_id=p["customer_id"], data={
            "order_id": p["order_id"], "status": p["status"], "carrier": p["carrier"], "tracking": p["tracking"]})
    if kind == "inventory.adjusted":
        return dict(base, type=kind, customer_id=None, data={"sku": p["sku"], "delta": p["delta"], "reason": p["reason"]})
    if kind == "message.received":
        return dict(base, type=kind, customer_id=p["customer_id"], data={
            "channel": p["channel"], "email": p["customer_email"], "body": p["body"]})
    return dict(base, type=kind, customer_id=p.get("customer_id"), data=p)


def accept(row):
    """Returns (status, canonical event or None)."""
    raw = row["body"].encode()
    try:
        b = json.loads(raw)
    except ValueError:
        return 400, None
    if row["path"] == "/webhooks/vendor-a":
        t = by_acct.get(b.get("account"))
        if t is None:
            return 404, None
        parts = dict(kv.split("=", 1) for kv in row["headers"]["Vendor-A-Signature"].split(","))
        mac = hmac.new(t["vendor_a"]["signing_secret"].encode(), f"{parts['t']}.".encode() + raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, parts.get("v1", "")):
            return 401, None
        return 200, normalize("a", b, t["tenant_id"])
    t = by_shop.get(b.get("shop_domain"))
    if t is None:
        return 404, None
    mac = base64.b64encode(hmac.new(t["vendor_b"]["signing_secret"].encode(), raw, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(mac, row["headers"]["X-VendorB-Hmac-SHA256"]):
        return 401, None
    return 200, normalize("b", b, t["tenant_id"])


store = collections.defaultdict(dict)       # tid -> event_id -> event
erased_customers = collections.defaultdict(set)
erased_tenants = set()
responses = {}
stats = collections.Counter()
max_seen = {}                                # tid -> max occurred_at seen so far (arrival order)
lateness = []
redelivery_delay = []
first_behind_max = 0

for line in gzip.open(f"{data_dir}/deliveries.jsonl.gz", "rt"):
    row = json.loads(line)
    if row["kind"] == "erase_customer":
        erased_customers[row["tenant_id"]].add(row["customer_id"])
        responses[row["seq"]] = 202
        continue
    if row["kind"] == "erase_tenant":
        erased_tenants.add(row["tenant_id"])
        responses[row["seq"]] = 202
        continue
    status, ev = accept(row)
    responses[row["seq"]] = status
    if ev is None:
        stats[f"reject_{status}"] += 1
        continue
    tid = ev["tenant_id"]
    if tid in erased_tenants:
        stats["after_tenant_erase"] += 1
        continue
    if ev["customer_id"] in erased_customers[tid]:
        stats["after_customer_erase"] += 1
        continue
    if ev["event_id"] in store[tid]:
        stats["duplicate"] += 1
        redelivery_delay.append(row["at_ms"] - ev["occurred_at_ms"])
        if store[tid][ev["event_id"]] != ev:
            stats["duplicate_conflict"] += 1
        continue
    if tid in max_seen and ev["occurred_at_ms"] < max_seen[tid]:
        stats["out_of_order"] += 1
        first_behind_max = max(first_behind_max, max_seen[tid] - ev["occurred_at_ms"])
    max_seen[tid] = max(max_seen.get(tid, 0), ev["occurred_at_ms"])
    lateness.append(row["at_ms"] - ev["occurred_at_ms"])
    store[tid][ev["event_id"]] = ev

# erasure is retroactive: drop every stored event of an erased customer
for tid, cids in erased_customers.items():
    before = len(store[tid])
    store[tid] = {k: e for k, e in store[tid].items() if e["customer_id"] not in cids}
    stats["retro_erased_events"] += before - len(store[tid])

print("stats", dict(stats))
lateness.sort()
for q in (0.5, 0.9, 0.96, 0.99, 0.999, 1.0):
    print(f"  lateness p{q*100:g}: {lateness[min(len(lateness)-1, int(q*len(lateness)))]/3600000:.2f} h")
print(f"  first copy, max behind tenant's max event time: {first_behind_max/3600000:.2f} h")
print(f"  redelivery, max delay after occurrence: {max(redelivery_delay)/3600000:.2f} h "
      f"({sum(d > 72 * 3600000 for d in redelivery_delay)} over 72 h)")

invalid = set(expected["invalid_seqs"])
lenient = set(expected["lenient_seqs"])
bad = [s for s, st in responses.items() if (s in invalid) != (400 <= st < 500) and s not in lenient]
print("response mismatches", len(bad), bad[:10])

ok = badn = 0
for tid, exp in expected["tenants"].items():
    if exp["erased"]:
        ok += tid in erased_tenants
        badn += tid not in erased_tenants
        continue
    st = reducer.fold(tid, list(store[tid].values()))
    if reducer.state_hash(st) == exp["hash"]:
        ok += 1
    else:
        badn += 1
        got = reducer.field_hashes(st)
        print("MISMATCH", tid, [k for k in got if got[k] != exp["fields"].get(k)])
print(f"state ok={ok} bad={badn}")

rb = 0
for w in ranges:
    evs = sorted((e for e in store[w["tenant_id"]].values() if w["from_ms"] <= e["occurred_at_ms"] < w["to_ms"]),
                 key=reducer.sort_key)
    ids = [e["event_id"] for e in evs]
    if len(ids) != w["count"] or hashlib.sha256("\n".join(ids).encode()).hexdigest() != w["ids_sha256"]:
        rb += 1
print(f"ranges ok={len(ranges)-rb} bad={rb}")

sizes = sorted(((len(v), k) for k, v in store.items()), reverse=True)
print("largest tenants", sizes[:5], "smallest", sizes[-3:])
print("total retained", sum(len(v) for v in store.values()))
canon_bytes = [len(json.dumps(e, separators=(",", ":"))) for v in store.values() for e in v.values()]
print("canonical json bytes avg", sum(canon_bytes) / len(canon_bytes))
