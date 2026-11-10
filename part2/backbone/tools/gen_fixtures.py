"""Generate fold fixtures from the reference reducer.

Usage (from part2/backbone): python3 -I tools/gen_fixtures.py <infrastructure dir>

Runs part2/analysis/oracle.py (stdout suppressed) to get the retained events per
tenant, then writes events (shuffled, seeded) and the reducer's expected state.
"""
import contextlib
import io
import json
import random
import sys
from pathlib import Path

KNOWN = {"order.created", "order.refunded", "shipment.updated",
         "inventory.adjusted", "message.received", "ad.metric"}


def load_oracle(infra):
    oracle = Path(__file__).resolve().parents[2] / "analysis" / "oracle.py"
    g = {"__name__": "oracle", "__file__": str(oracle)}
    saved = sys.argv
    sys.argv = [str(oracle), infra]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(oracle.read_text(), str(oracle), "exec"), g)
    finally:
        sys.argv = saved
    return g


def ev(event_id, t, kind, customer, data, tenant="t_edge"):
    return {"event_id": event_id, "tenant_id": tenant, "type": kind,
            "occurred_at_ms": t, "customer_id": customer, "data": data}


def order(oid, lines, email="a@example.com", name="A"):
    return {"order_id": oid, "lines": [{"sku": s, "qty": q, "unit_cents": u} for s, q, u in lines],
            "email": email, "name": name}


def edge_cases():
    return {
        "empty": [],
        "orphans_and_caps": [
            ev("e1", 1, "order.refunded", "cus_1", {"order_id": "o1", "amount_cents": 300}),
            ev("e2", 2, "order.created", "cus_1", order("o1", [("A", 1, 1000)])),
            ev("e3", 3, "order.refunded", "cus_1", {"order_id": "o1", "amount_cents": 600}),
            ev("e4", 4, "order.refunded", "cus_1", {"order_id": "o1", "amount_cents": 600}),
            ev("e5", 5, "shipment.updated", "cus_1",
               {"order_id": "o2", "status": "shipped", "carrier": "ups", "tracking": "T1"}),
        ],
        "duplicate_order": [
            ev("evt_b", 10, "order.created", "cus_1", order("o1", [("A", 1, 500)])),
            ev("0aa1b2c3-0000-4000-8000-000000000000", 10, "order.created", "cus_2",
               order("o1", [("B", 2, 700)])),
        ],
        "inventory_clamp": [
            ev("e1", 1, "inventory.adjusted", None, {"sku": "A", "delta": -10, "reason": "shrink"}),
            ev("e2", 2, "inventory.adjusted", None, {"sku": "A", "delta": 3, "reason": "restock"}),
            ev("e3", 3, "order.created", "cus_1", order("o1", [("A", 5, 100)])),
        ],
        "shipment_status": [
            ev("e1", 1, "order.created", "cus_1", order("o1", [("A", 1, 1000)])),
            ev("e2", 2, "order.created", "cus_2", order("o2", [("B", 1, 2000)])),
            ev("e3", 3, "order.created", "cus_3", order("o3", [("C", 1, 3000)])),
            ev("e4", 4, "shipment.updated", "cus_1",
               {"order_id": "o1", "status": "shipped", "carrier": "ups", "tracking": "T1"}),
            ev("e5", 5, "shipment.updated", "cus_1",
               {"order_id": "o1", "status": "delivered", "carrier": "ups", "tracking": "T1"}),
            ev("e6", 6, "order.refunded", "cus_2", {"order_id": "o2", "amount_cents": 2000}),
        ],
        "orphans_without_fields": [
            ev("e1", 1, "order.refunded", "cus_1", {"order_id": "o9"}),
            ev("e2", 2, "shipment.updated", "cus_1", {"order_id": "o9"}),
            ev("e3", 3, "order.created", "cus_1", order("o1", [("A", 1, 100)])),
            ev("e4", 4, "shipment.updated", "cus_1", {"order_id": "o1", "status": "shipped"}),
        ],
        "unknown_and_null": [
            ev("e1", 1, "shipment.patch", "cus_9", {"order_id": "o1", "note": "x"}),
            ev("e2", 2, "ad.metric", None,
               {"campaign_id": "c1", "spend_cents": 100, "impressions": 1000, "clicks": 10}),
            ev("e3", 3, "ad.metric", None,
               {"campaign_id": "c1", "spend_cents": 50, "impressions": 500, "clicks": 5}),
            ev("e4", 4, "message.received", "cus_1", {"channel": "email", "email": "a@example.com", "body": "hi"}),
            ev("e5", 9, "message.received", "cus_2", {"channel": "chat", "email": "b@example.com", "body": "yo"}),
        ],
    }


def write(out, name, tid, events, reducer):
    shuffled = list(events)
    random.Random(7).shuffle(shuffled)
    with open(out / f"{name}.events.jsonl", "w") as f:
        for e in shuffled:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    (out / f"{name}.expected.json").write_text(
        json.dumps(reducer.fold(tid, events), sort_keys=True) + "\n")


def main():
    infra = sys.argv[1]
    g = load_oracle(infra)
    store, erased, reducer = g["store"], g["erased_customers"], g["reducer"]
    out = Path(__file__).resolve().parents[1] / "internal" / "fold" / "testdata"
    out.mkdir(parents=True, exist_ok=True)

    # The first four qualifying tenants have no erasures, so take the first two
    # with erased customers and the first two without.
    fit = [t for t in sorted(store) if 200 <= len(store[t]) <= 1500]
    chosen = sorted([t for t in fit if erased.get(t)][:2] + [t for t in fit if not erased.get(t)][:2])
    assert len(chosen) == 4, chosen
    assert sum(1 for t in chosen if erased.get(t)) >= 2, "need 2 tenants with erased customers"
    types = {e["type"] for t in chosen for e in store[t].values()}
    assert KNOWN <= types and (types - KNOWN), f"type coverage: {sorted(types)}"
    for t in chosen:
        write(out, t, t, list(store[t].values()), reducer)
        print(t, len(store[t]), "events", len(erased.get(t, ())), "erased customers")
    for name, events in edge_cases().items():
        write(out, f"edge_{name}", "t_edge", events, reducer)


main()
