"""Amazon raw collector (spec.md). Standard library only; no retries."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.apify.com/v2"
SEARCH_RESULTS, TOP_N, MIN_RATINGS_TO_MERGE, DETAIL_CANDIDATES, REVIEWS_PER_PRODUCT = 60, 10, 100, 15, 10
RUN_TIMEOUT_S, POLL_S, WAIT_MARGIN_S, CHARGE_READ_DELAY_S, HTTP_TIMEOUT_S = 600, 3, 120, 30, 60
SEARCH = ("apt_marble~amazon-search-results-scraper", 512, 0.10)
DETAIL = ("junglee~Amazon-crawler", 4096, 0.10)
REVIEWS = ("delicious_zebu~amazon-reviews-scraper-with-advanced-filters", 256, 0.70)
ENDED = {"SUCCEEDED": None, "FAILED": "failed", "ABORTED": "aborted", "TIMED-OUT": "timed_out"}
PERSONAL = ("Reviewer", "ReviewerProfileUrl", "ReviewerId", "Images", "Videos")


def ts(s):
    return s[:19] + "Z"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- pure functions ----------
def brand_ok(brand, names):
    if not isinstance(brand, str):
        return False
    b = " ".join(brand.split()).casefold()
    return any(b == n or b.startswith(n + " ") for n in names)


def select_candidates(rows, brand_names):
    for r in rows:
        if any(k not in r for k in ("asin", "position", "isSponsored")):
            raise ValueError("search row lacks asin, position or isSponsored")
    names = [n.casefold() for n in brand_names]
    cands, merged, seen = [], {}, set()
    for r in sorted(rows, key=lambda r: r["position"]):
        p = r.get("price")
        if (r["isSponsored"] is True or r["asin"] in seen or isinstance(p, bool)
                or not isinstance(p, (int, float)) or not brand_ok(r.get("brand"), names)):
            continue
        seen.add(r["asin"])
        rc = r.get("ratingsCount")
        twin = None
        if isinstance(rc, int) and rc >= MIN_RATINGS_TO_MERGE:
            twin = next((c for c in cands if c.get("rating") == r.get("rating") and c.get("ratingsCount") == rc), None)
        if twin:
            merged[twin["asin"]].append(r["asin"])
        else:
            cands.append(r)
            merged[r["asin"]] = []
    return cands, merged


def select_top(candidates, details, top_n):
    selected, merged = [], {}
    for a in candidates:
        d = details.get(a)
        target = None
        for s in selected:
            e = details.get(s)
            if (d and e and isinstance(d.get("reviewsCount"), int) and d["reviewsCount"] == e.get("reviewsCount")
                    and (a in (e.get("variantAsins") or []) or s in (d.get("variantAsins") or []))):
                target = s
                break
        if target:
            merged[target].append(a)
        else:
            selected.append(a)
            merged[a] = []
            if len(selected) == top_n:
                break
    return selected, merged


def group_reviews(rows, asins, per_product):
    out = {a: [] for a in asins}
    for r in rows:
        if not r.get("ReviewId") or r.get("ASIN") not in out:
            raise ValueError("review row lacks ReviewId or has an unrequested ASIN")
        n = len(r["Images"]) if isinstance(r.get("Images"), list) else 0
        out[r["ASIN"]].append(({**r, **dict.fromkeys(PERSONAL)}, n))
    if any(len(v) > per_product for v in out.values()):
        raise ValueError("more rows than per_product for one ASIN")
    return out


def detail_error(item, asin):
    if item is None:
        return "no_item"
    if "error" in item:
        return str(item["error"])
    if item.get("asin") != asin:
        return "asin_mismatch"
    if "reviewsCount" not in item or not isinstance(item.get("variantAsins"), list):
        return "shape_changed"
    return None


# ---------- Apify ----------
class Fail(Exception):
    pass


def call(st, method, url, token, body=None):
    st["requests"] += 1
    req = urllib.request.Request(url, method=method, headers={"Authorization": "Bearer " + token})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=HTTP_TIMEOUT_S) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Fail("http_%d" % e.code)
    except (OSError, ValueError):
        raise Fail("request_error")


def run_actor(st, token, actor, body):
    """Returns (error, items, finished_at). Adds the run's cost to st['cost']."""
    name, mem, cap = actor
    q = "timeout=%d&memory=%d&maxTotalChargeUsd=%s" % (RUN_TIMEOUT_S, mem, cap)
    try:
        run = call(st, "POST", "%s/acts/%s/runs?%s" % (API, name, q), token, body)["data"]
    except Fail as e:
        return str(e), [], None
    except (KeyError, TypeError):
        return "request_error", [], None
    cost, err, items, status, t0 = 0.0, None, [], None, time.monotonic()
    while True:
        time.sleep(POLL_S)
        try:
            run = call(st, "GET", "%s/actor-runs/%s" % (API, run["id"]), token)["data"]
        except Fail as e:
            err = str(e)
            break
        except (KeyError, TypeError):
            err = "request_error"
            break
        cost = run.get("usageTotalUsd") or cost
        status = run.get("status")
        if status in ENDED:
            break
        if time.monotonic() - t0 > RUN_TIMEOUT_S + WAIT_MARGIN_S:
            err = "wait_exceeded"
            break
    if err is None:
        err = ENDED[status]
        if err is None:
            try:
                items = call(st, "GET", "%s/datasets/%s/items?format=json&clean=true" % (API, run["defaultDatasetId"]), token)
            except Fail as e:
                err = str(e)
            except KeyError:
                err = "request_error"
    fin = run.get("finishedAt") if status in ENDED else None
    end = datetime.strptime(fin[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() if fin else None
    st["runs"].append({"id": run["id"], "cost": cost, "end": end})
    st["cost"] += cost
    return err, items, (ts(fin) if fin else None)


def settle(st, token):
    """Once per brand, after its last run: replace each ended run's last-seen cost with its settled usageTotalUsd (F12)."""
    ended = [r for r in st["runs"] if r["end"] is not None]
    if not ended:
        return
    time.sleep(max(0.0, max(r["end"] for r in ended) + CHARGE_READ_DELAY_S - time.time()))
    for r in ended:
        try:
            v = call(st, "GET", "%s/actor-runs/%s" % (API, r["id"]), token)["data"]["usageTotalUsd"]
        except (Fail, KeyError, TypeError):
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        st["cost"] += v - r["cost"]
        r["cost"] = v


# ---------- brand run ----------
def get_token():
    t = os.environ.get("APIFY_TOKEN", "").strip()
    env = HERE.parents[2] / ".env"
    if not t and env.is_file():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "APIFY_TOKEN":
                t = v.strip().strip("'\"")
    return t


def collect(st, cfg, token, emit):
    """Returns (status, reason). Writes records through emit(record)."""
    if not token:
        return "could_not_look", "missing_token"
    err, rows, _ = run_actor(st, token, SEARCH, {
        "keywords": [cfg["keyword"]], "maxResultsPerKeyword": SEARCH_RESULTS, "sortBy": "relevance",
        "excludeSponsored": False, "primeOnly": False, "marketplace": "us", "maxConcurrency": 1})
    if err:
        return "could_not_look", "search_" + err
    if not rows:
        return "could_not_look", "search_empty"
    st["extra"]["search_rows"] = len(rows)
    try:
        cands, merged_b = select_candidates(rows, cfg["brand_names"])
    except ValueError:
        return "could_not_look", "search_shape_changed"
    st["extra"]["candidates"] = len(cands)
    if not cands:
        return "could_not_look", "no_matching_products"

    checked = cands[:DETAIL_CANDIDATES]
    err, items, det_at = run_actor(st, token, DETAIL, {
        "categoryOrProductUrls": [{"url": "https://www.amazon.com/dp/" + c["asin"]} for c in checked],
        "maxItemsPerStartUrl": 1, "scrapeProductDetails": True, "useCaptchaSolver": False, "maxOffers": 0,
        "scrapeSellers": False, "scrapeProductVariantPrices": False, "maxProductVariantsAsSeparateResults": 0,
        "proxyCountry": "AUTO_SELECT_PROXY_COUNTRY"})
    by_input = {i.get("input"): i for i in items if isinstance(i, dict)}
    details, derr = {}, {}
    for c in checked:
        a = c["asin"]
        derr[a] = err or detail_error(by_input.get("https://www.amazon.com/dp/" + a), a)
        details[a] = None if derr[a] else by_input["https://www.amazon.com/dp/" + a]
    selected, merged_d = select_top([c["asin"] for c in checked], details, TOP_N)
    st["extra"]["selected"] = len(selected)

    rev_err, groups, rev_at = run_actor(st, token, REVIEWS, {
        "ASIN_or_URL": selected, "country": "United States", "max_reviews": REVIEWS_PER_PRODUCT,
        "sort_reviews_by": ["helpful"], "filter_by_verified_purchase_only": ["all_reviews"],
        "filter_by_ratings": ["all_stars"], "filter_by_mediaType": ["all_contents"], "variant_scope": "all_variants",
        "unique_only": True, "get_customers_say": True, "include_personal_data": False, "filter_by_keywords": []})
    if not rev_err:
        try:
            groups = group_reviews(groups, selected, REVIEWS_PER_PRODUCT)
        except ValueError:
            rev_err = "shape_changed"
    by_asin = {c["asin"]: c for c in cands}
    written, short, bad_details = set(), 0, sum(1 for a in selected if derr[a])
    for rank, a in enumerate(selected, 1):
        d = details[a]
        rows_a = [] if rev_err else groups[a]
        if rev_err:
            state = "failed"
        else:
            total = rows_a[0][0].get("RatingTypeTotalReviewsCount") if rows_a else None
            ok = (len(rows_a) >= REVIEWS_PER_PRODUCT or (rows_a and len(rows_a) == total)
                  or (not rows_a and d is not None and d["reviewsCount"] == 0))
            state = "complete" if ok else "short"
            short += state == "short"
        emit({"key": a, "kind": "product", "url": "https://www.amazon.com/dp/" + a,
              "fetched_at": det_at if d is not None else ts(by_asin[a]["scrapedAt"]),
              "raw": {"rank": rank, "search_item": by_asin[a], "merged_asins": merged_b[a] + merged_d[a],
                      "detail": d, "detail_error": derr[a], "reviews": state}})
        for n, (row, images) in enumerate(rows_a, 1):
            if row["ReviewId"] in written:
                continue
            written.add(row["ReviewId"])
            emit({"key": row["ReviewId"], "kind": "review",
                  "url": "https://www.amazon.com/portal/customer-reviews/srp/-/" + row["ReviewId"],
                  "fetched_at": rev_at, "raw": {"product_asin": a, "rank_in_product": n, "image_count": images, "item": row}})

    parts = []
    complete = len(selected) == TOP_N or (len(cands) <= len(checked) and len(rows) >= SEARCH_RESULTS)
    if not complete:
        if len(rows) < SEARCH_RESULTS:
            parts.append("search_short(rows=%d)" % len(rows))
        if len(cands) > len(checked):
            parts.append("candidates_unchecked=%d" % (len(cands) - len(checked)))
    if bad_details:
        parts.append("details_failed=%d" % bad_details)
    if rev_err:
        parts.append("reviews_failed(%s)" % rev_err)
    if short:
        parts.append("reviews_short=%d" % short)
    return ("partial", "; ".join(parts)) if parts else ("ok", "")


def run_brand(slug, cfg, token):
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    d = HERE / "raw" / slug
    d.mkdir(parents=True, exist_ok=True)
    part = d / (run_id + ".jsonl.part")
    st = {"requests": 0, "cost": 0.0, "runs": [], "extra": {"search_rows": 0, "candidates": 0, "selected": 0}}
    kinds, failed = {}, False
    with open(part, "w", encoding="utf-8") as f:
        def emit(rec):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            kinds[rec["kind"]] = kinds.get(rec["kind"], 0) + 1
        try:
            status, reason = collect(st, cfg, token, emit)
        except Exception as e:
            failed = True
            status = "partial" if kinds else "could_not_look"
            reason = "exception: %s: %s" % (type(e).__name__, e)
    settle(st, token)
    part.rename(d / (run_id + ".jsonl"))
    result = {"source": "amazon", "brand": slug, "run_id": run_id, "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "finished_at": now(), "status": status, "reason": reason, "records": sum(kinds.values()),
              "records_by_kind": kinds, "expected_total": None, "requests": st["requests"],
              "cost_usd": round(st["cost"], 6), "extra": st["extra"]}
    (d / (run_id + ".run.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(slug, status, reason, "records=%d cost=%s" % (result["records"], result["cost_usd"]))
    return failed


def main():
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand", choices=sorted(inputs))
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()
    token = get_token()
    slugs = list(inputs) if args.all else [args.brand]
    return 1 if any([run_brand(s, inputs[s], token) for s in slugs]) else 0


if __name__ == "__main__":
    sys.exit(main())
