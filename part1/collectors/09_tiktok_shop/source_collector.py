"""Source 9: TikTok Shop via the Apify Actor lurkapi/tiktok-shop-scraper. Raw collector; see spec.md."""
import argparse, copy, json, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
START_URL = ("https://api.apify.com/v2/acts/lurkapi~tiktok-shop-scraper/runs?build=0.0.34&memory=1024&timeout=300"
             "&maxTotalChargeUsd={}&waitForFinish=60")
RUN_URL = "https://api.apify.com/v2/actor-runs/{}"
ITEMS_URL = "https://api.apify.com/v2/datasets/{}/items?format=json"
HTTP_TIMEOUT_S, MAX_POLLS, SEARCH_LIMIT = 90, 6, 20
ACTIVE = {"READY", "RUNNING", "TIMING-OUT", "ABORTING"}
TERMINAL = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
FLAGS = {"includeReviews": False, "includeCreatorCount": False, "includeFirstSeen": False}
SUCCESS_KEYS = ("productId", "rank", "title", "currentPrice", "currency", "soldCount", "sellerId", "sellerName",
                "scrapeTimestamp", "productUrl")


def now_z(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def charge_cap_usd(n): return f"{Decimal('0.00005') + Decimal('0.00199') * (n + 1):.5f}"


def strip_personal(row):
    row = copy.deepcopy(row)
    removed = row.pop("reviews", None)
    if "shippingOrigin" in row: row["shippingOrigin"] = None
    return row, len(removed) if isinstance(removed, list) else 0


def classify_part(rows, part, run_id, tracked_ids, search_term, observed_at, part_error=None):
    tracked = part == "tracked"
    want_source = "productId" if tracked else "keyword"
    out = {"records": [], "error": None, "fetched": 0, "unavailable": 0, "failed": 0, "missing": 0,
           "unexpected_rows": 0, "message_rows": 0, "reviews_removed": 0}
    if not tracked: out["ranks_complete"] = False
    at = observed_at or now_z()

    def envelope(pid, state, error, item, removed):
        key = f"product/{pid}" if tracked else f"search/{search_term}/{pid}"
        inp = {"part": "tracked", "product_id": pid} if tracked else {"part": "search", "search_term": search_term, "limit": SEARCH_LIMIT}
        stamp = re.sub(r"\.\d+Z$", "Z", item["scrapeTimestamp"]) if item else at
        return {"key": key, "kind": "product" if tracked else "search_result",
                "url": f"https://www.tiktok.com/shop/pdp/_/{pid}", "fetched_at": stamp,
                "raw": {"item": item, "item_state": state, "item_error": error, "input": inp,
                        "apify_run_id": run_id, "reviews_removed": removed}}

    def missing_all(error):
        out["error"] = error
        if tracked:
            out["records"] = [envelope(p, "missing", error, None, 0) for p in tracked_ids]
            out["missing"] = len(tracked_ids)
        return out

    if part_error: return missing_all(part_error)
    products = [(i, r) for i, r in enumerate(rows) if isinstance(r, dict) and r.get("productId") is not None]
    out["message_rows"] = len(rows) - len(products)
    if not products:
        first = next((r for r in rows if isinstance(r, dict)), None)
        return missing_all(f"no_products: {first.get('status') if first else 'empty dataset'}")
    for i, r in products:
        need = SUCCESS_KEYS if r.get("status") == "Success" else ("productId", "source", "scrapeTimestamp")
        bad = next((k for k in need if r.get(k) is None), None) or (None if r.get("source") == want_source else "source")
        if bad:
            out["error"] = f"shape_changed: row {i} {bad}"
            return out
    if tracked:
        first_rows = {}
        for _, r in products: first_rows.setdefault(r["productId"], r)
        out["unexpected_rows"] = len(products) - sum(p in first_rows for p in tracked_ids)
        chosen = [(p, first_rows.get(p)) for p in tracked_ids]
    else:
        chosen = [(r["productId"], r) for _, r in sorted(products, key=lambda x: x[1].get("rank") or 0)]
    ranks = []
    for pid, r in chosen:
        if r is None:
            out["missing"] += 1
            out["records"].append(envelope(pid, "missing", "no_row", None, 0))
            continue
        item, removed = strip_personal(r)
        status = r.get("status")
        state = "fetched" if status == "Success" else "unavailable" if status == "Not available in US" else "failed"
        out[state] += 1
        if state == "fetched": ranks.append(r["rank"])
        out["reviews_removed"] += removed
        out["records"].append(envelope(pid, state, None if state == "fetched" else status, item, removed))
    if not tracked: out["ranks_complete"] = sorted(ranks) == list(range(1, SEARCH_LIMIT + 1))
    return out


def part_problems(p, part):
    if p.get("error"): return [p["error"]]
    out = []
    if p.get("apify_status") and p["apify_status"] != "SUCCEEDED":
        out.append(f"apify_run_{p['apify_status']}: {p.get('apify_status_message') or ''}")
    for k in ("failed", "unavailable", "missing", "unexpected_rows", "message_rows"):
        if p.get(k) and (k != "unavailable" or part == "search"): out.append(f"{k}={p[k]}")
    if part == "search":
        if p["fetched"] != SEARCH_LIMIT: out.append(f"fetched={p['fetched']}/{SEARCH_LIMIT}")
        elif not p["ranks_complete"]: out.append("ranks_incomplete")
    return out


def decide_status(token_ok, extra):
    if not token_ok: return "could_not_look", "missing_token"
    t, s = extra["tracked"], extra["search"]
    if t["error"] and s["error"]: return "could_not_look", f"tracked: {t['error']}; search: {s['error']}"
    problems = {n: part_problems(extra[n], n) for n in ("tracked", "search")}
    if not any(problems.values()): return "ok", ""
    return "partial", "; ".join(f"{n}: {', '.join(v)}" for n, v in problems.items() if v)


def read_token():
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                v = line.split("=", 1)[1].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
                return v.strip()
    except OSError:
        pass
    return ""


def call(state, token, method, url, body=None):
    """One request, sent once. Returns (status, parsed_json_or_None). Raises on transport error."""
    state["requests"] += 1
    headers, data = {"Authorization": f"Bearer {token}"}, None
    if body is not None: data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, None


class PartError(Exception): pass


def detail(step, fn):
    try: return fn()
    except Exception as e: raise PartError(f"{step}: request_error: {type(e).__name__}") from e


def run_part(state, token, part, actor_input, n, ids, term):
    """Runs one actor run; returns the part summary and its records."""
    info = dict.fromkeys(("apify_run_id", "apify_status", "apify_status_message", "actor_build"))
    run, rows, observed, err = None, None, None, None
    try:
        status, body = detail("apify_start_failed", lambda: call(state, token, "POST", START_URL.format(charge_cap_usd(n)), actor_input))
        if status != 201 or not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            etype = ((body or {}).get("error") or {}).get("type") if isinstance(body, dict) else None
            if status == 402 or any(w in (etype or "").lower() for w in ("limit", "credit")):
                raise PartError(f"apify_credit_exhausted: http_{status} {etype or '-'}")
            raise PartError(f"apify_start_failed: http_{status} {etype or '-'}")
        run = body["data"]
        for _ in range(MAX_POLLS):
            if run.get("status") not in ACTIVE: break
            status, body = detail("apify_poll_failed", lambda: call(state, token, "GET", RUN_URL.format(run["id"]) + "?waitForFinish=60"))
            if status != 200 or not isinstance(body, dict) or "data" not in body: raise PartError(f"apify_poll_failed: http_{status}")
            run = body["data"]
        if run.get("status") not in TERMINAL: raise PartError(f"apify_run_not_finished({run.get('status')})")
        status, rows = detail("apify_dataset_failed", lambda: call(state, token, "GET", ITEMS_URL.format(run["defaultDatasetId"])))
        if status != 200 or not isinstance(rows, list): raise PartError(f"apify_dataset_failed: http_{status}")
        observed = now_z()
    except PartError as e:
        err = str(e)
    if run:
        info.update(apify_run_id=run.get("id"), apify_status=run.get("status"), apify_status_message=run.get("statusMessage"),
                    actor_build=run.get("buildNumber"))
    res = classify_part(rows or [], part, info["apify_run_id"], ids, term, observed or now_z(), err)
    cost, final = 0, False
    if run:
        time.sleep(15)
        try:
            status, body = call(state, token, "GET", RUN_URL.format(run["id"]))
            if status == 200 and isinstance(body, dict) and isinstance(body.get("data"), dict):
                run = body["data"]
                ok_rows = sum(isinstance(r, dict) and r.get("status") == "Success" for r in rows) if rows is not None else None
                ch = run.get("chargedEventCounts") or {}
                final = ok_rows is not None and ch == (run.get("accountedChargedEventCounts") or {}) and ch.get("product-scraped-us", 0) == ok_rows
        except Exception:
            pass
        cost = run.get("usageTotalUsd") or 0
    records = res.pop("records")
    res.pop("reviews_removed")
    if part == "search": res.pop("missing"), res.pop("unexpected_rows")
    return {**info, **res, "cost_usd": cost, "cost_final": final}, records


def run_brand(slug, cfg):
    started = datetime.now(timezone.utc)
    run_id, started_at = started.strftime("%Y%m%dT%H%M%SZ"), started.strftime("%Y-%m-%dT%H:%M:%SZ")
    out_dir = HERE / "raw" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    part, final = out_dir / f"{run_id}.jsonl.part", out_dir / f"{run_id}.jsonl"
    state, extra, by_kind, failed = {"requests": 0}, {}, {"product": 0, "search_result": 0}, False
    token = read_token()
    status, reason = None, ""
    ids, term = cfg["tracked_product_ids"], cfg["search_term"]
    plans = (("tracked", {"country": "US", "productIds": ids, **FLAGS}, len(ids)),
             ("search", {"country": "US", "keywords": [term], "keywordSortBy": "default", "maxProductsPerSource": SEARCH_LIMIT, **FLAGS}, SEARCH_LIMIT))
    out = part.open("w", encoding="utf-8")
    try:
        if token:
            for i, (name, actor_input, n) in enumerate(plans):
                if i: time.sleep(5)
                extra[name], records = run_part(state, token, name, actor_input, n, ids, term)
                for rec in records:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush(); by_kind[rec["kind"]] += 1
        status, reason = decide_status(bool(token), extra)
    except Exception as e:
        failed = True
        status = "partial" if sum(by_kind.values()) else "could_not_look"
        reason = f"exception: {type(e).__name__}: {e}"
    finally:
        out.close()
    part.rename(final)
    cost = round(sum(p["cost_usd"] for p in extra.values()), 5)
    result = {"source": "tiktok_shop", "brand": slug, "run_id": run_id, "started_at": started_at, "finished_at": now_z(),
              "status": status, "reason": reason, "records": sum(by_kind.values()), "records_by_kind": by_kind,
              "expected_total": None, "requests": state["requests"], "cost_usd": cost,
              "extra": {"data_provider": "apify:lurkapi/tiktok-shop-scraper", "verified_against_site": False, **extra}}
    (out_dir / f"{run_id}.run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"{slug}: {status} {reason} records={result['records']} cost_usd={cost}")
    return not failed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand"); g.add_argument("--all", action="store_true")
    args = ap.parse_args()  # argparse exits with 2 on invalid arguments
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    if args.brand and args.brand not in inputs:
        print(f"unknown brand: {args.brand}", file=sys.stderr); return 2
    ok = []
    for i, s in enumerate(list(inputs) if args.all else [args.brand]):
        if i: time.sleep(5)
        ok.append(run_brand(s, inputs[s]))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
