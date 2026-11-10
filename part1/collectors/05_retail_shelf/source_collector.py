"""Raw collector for source 5, retail shelf. See spec.md. No retries, no fallbacks."""
import argparse, hashlib, json, math, os, re, sys, time, urllib.error, urllib.request
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).parent
PRODUCTS_PER_CELL, NAV_TIMEOUT_S, REVIEW_KEY_WAIT_S, REVIEW_FETCH_TIMEOUT_S = 10, 45, 20, 20
ULTA_SPACING_S, MAX_FAILURES_IN_A_ROW = 3, 3
APIFY_TIMEOUT_S, APIFY_POLL_S, APIFY_COST_WAIT_S = 300, 10, 15
BLOCK_WORDS = ("access denied", "captcha", "unusual traffic")
ROW_KEYS = {
    "ulta": ["productId", "brandName", "reviewCount"],
    "target": ["tcin", "position", "brand", "isMarketplace", "itemType", "parentTcin", "reviewCount", "url", "storeId"],
    "sephora": ["page", "position", "productId", "brandName", "reviews", "productUrl"],
    "chewy": ["partNumber", "manufacturer", "ratingCount", "url"],
}
ECOM = ("apify~e-commerce-scraping-tool", "1.00")
CHEWY_REVIEWS = ("automation-lab~chewy-product-reviews-scraper", "0.05")
ULTA_REVIEWS_URL = ("https://display.powerreviews.com/m/6406/l/en_US/product/{}/reviews?paging.from=0&paging.size=10"
                    "&filters=&search=&sort=Newest&image_only=false&page_locale=en_US&native_only=true&apikey={}")
FETCH_JS = ("async (u) => { try { const r = await fetch(u, {signal: AbortSignal.timeout(20000)}); "
            "return {status: r.status, text: await r.text()}; } catch (e) { return {status: 0, text: String(e)}; } }")


PAGE_FETCH_JS = ("async (u) => { const r = await fetch(u, {credentials: \"include\", signal: AbortSignal.timeout(20000)}); return {status: r.status, text: await r.text()}; }")
LD_JSON_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


class Fail(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def msg(e):
    lines = str(e).splitlines()
    return lines[0] if lines else type(e).__name__


# ---------- pure functions (tested) ----------
def find_listing_module(root_query):
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("moduleName") == "ProductListingResults" and isinstance(x.get("items"), list):
                found.append(x)
            x = list(x.values())
        if isinstance(x, list):
            for v in x:
                walk(v)
    walk(root_query)
    if len(found) != 1:
        raise ValueError(f"ProductListingResults with items found {len(found)} times")
    return found[0]


def select(retailer, rows, cell):
    picked, seen = [], set()
    for row in rows:
        if retailer == "chewy":
            ok = row["manufacturer"] == cell["brand_name"]
        elif retailer == "target":
            ok = (row["brand"] == cell["brand_name"] and not row["isMarketplace"]
                  and (cell.get("item_types") is None or row["itemType"] in cell["item_types"]))
            if ok and row["parentTcin"] is not None:
                sig = (row["parentTcin"], row["reviewCount"])
                if sig in seen:
                    continue
                seen.add(sig)
        else:
            ok = row["brandName"] == cell["brand_name"]
        if ok:
            picked.append(row)
            if len(picked) == PRODUCTS_PER_CELL:
                break
    return picked


def review_key(product_key, retailer, review):
    if retailer == "ulta":
        rid = str(review["ugc_id"])
    elif retailer == "chewy":
        rid = review["reviewId"]
    else:
        rid = "h" + hashlib.sha256((review["datePublished"] + "\n" + review["reviewBody"]).encode("utf-8")).hexdigest()[:16]
    return f"{product_key}:{rid}"


def product_page_offer(html, sku):
    """Price, currency and availability of the Product JSON-LD object whose sku is `sku`. Nothing else is returned."""
    for m in LD_JSON_RE.finditer(html):
        try:
            block = json.loads(m.group(1))
        except ValueError:
            continue
        cands = list(block) if isinstance(block, list) else [block]
        if isinstance(block, dict) and isinstance(block.get("@graph"), list):
            cands += block["@graph"]
        for o in cands:
            if not (isinstance(o, dict) and o.get("@type") == "Product" and str(o.get("sku")) == str(sku) and o.get("offers")):
                continue
            offers = o["offers"]
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if not isinstance(offers, dict):
                continue
            price = offers.get("price")
            if isinstance(price, str) and re.fullmatch(r"\d+(\.\d+)?", price.strip()):
                valid = float(price) > 0
            else:
                valid = isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and price > 0
            if not valid:
                raise ValueError("price_not_number")
            avail = offers.get("availability")
            return {"sku": str(sku), "price": price, "currency": offers.get("priceCurrency"),
                    "availability": avail.rsplit("/", 1)[-1] if isinstance(avail, str) else None}
    raise ValueError("product_ld_not_found")


# ---------- helpers ----------
def load_token():
    if "APIFY_TOKEN" in os.environ:
        return os.environ["APIFY_TOKEN"].strip()
    try:
        for line in (HERE.parents[2] / ".env").read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def write(ctx, key, kind, url, raw, ts):
    ctx["fh"].write(json.dumps({"key": key, "kind": kind, "url": url, "fetched_at": ts, "raw": raw}, ensure_ascii=False) + "\n")
    ctx["fh"].flush()
    ctx["kinds"][kind] = ctx["kinds"].get(kind, 0) + 1


def http(method, url, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, text = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, None


def apify(ctx, actor, body, cap):
    token = ctx["token"]
    if not token:
        raise Fail("missing_token")
    try:
        st, d = http("POST", f"https://api.apify.com/v2/acts/{actor}/runs?timeout={APIFY_TIMEOUT_S}&maxTotalChargeUsd={cap}", token, body)
    except Exception as e:
        raise Fail(f"apify_start: {msg(e)}")
    if st != 201:
        raise Fail(f"apify_start: http_{st}")
    t0, run = time.monotonic(), d["data"]
    ctx["requests"] += 1
    ctx["runs"][run["id"]] = run.get("usageTotalUsd") or 0
    while run["status"] not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
        if time.monotonic() - t0 > APIFY_TIMEOUT_S + 60:
            raise Fail("apify_wait_timeout")
        time.sleep(APIFY_POLL_S)
        try:
            st, d = http("GET", f"https://api.apify.com/v2/actor-runs/{run['id']}", token)
            if st != 200:
                raise RuntimeError(f"http_{st}")
        except Exception as e:
            raise Fail(f"apify_poll: {msg(e)}")
        run = d["data"]
        ctx["runs"][run["id"]] = run.get("usageTotalUsd") or ctx["runs"][run["id"]]
    print(f"apify {actor}: {run['status']}", flush=True)
    if run["status"] != "SUCCEEDED":
        raise Fail("apify_" + run["status"].lower())
    try:
        st, items = http("GET", f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?clean=true&format=json", token)
        if st != 200 or not isinstance(items, list):
            raise RuntimeError(f"http_{st}")
    except Exception as e:
        raise Fail(f"apify_dataset: {msg(e)}")
    return items


def apify_cost(ctx):
    time.sleep(APIFY_COST_WAIT_S)
    total = 0.0
    for rid, last in ctx["runs"].items():
        try:
            st, d = http("GET", f"https://api.apify.com/v2/actor-runs/{rid}", ctx["token"])
            total += d["data"]["usageTotalUsd"] if st == 200 else last
        except Exception:
            total += last
    return round(total, 4)


# ---------- Ulta (own code) ----------
def nav(ctx, page, url):
    ctx["requests"] += 1
    resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_S * 1000)
    text = (page.title() + " " + page.evaluate("() => document.body ? document.body.innerText : ''")).lower()
    return (resp is not None and resp.status >= 400) or any(w in text for w in BLOCK_WORDS)


def ulta_list(ctx, page, url):
    try:
        if nav(ctx, page, url):
            raise Fail("blocked")
        root = page.evaluate("() => window.__APOLLO_STATE__ ? window.__APOLLO_STATE__.ROOT_QUERY : null")
    except Fail:
        raise
    except Exception as e:
        raise Fail(f"browser: {msg(e)}")
    try:
        return find_listing_module(root)["items"]
    except ValueError:
        raise Fail("list_shape_changed")


def ulta_find_key(ctx, page, url):
    seen = []

    def on_request(req):
        u = urlparse(req.url)
        if u.hostname == "display.powerreviews.com" and u.path.endswith("/reviews"):
            seen.append(req.url)
    page.on("request", on_request)
    try:
        time.sleep(ULTA_SPACING_S)
        if nav(ctx, page, url):
            return None, "blocked"
        page.wait_for_timeout(3000)
        for _ in range(2):
            page.mouse.wheel(0, 3500)
            page.wait_for_timeout(2500)
        for _ in range(REVIEW_KEY_WAIT_S * 2):
            if seen:
                break
            page.wait_for_timeout(500)
    except Exception as e:
        return None, f"browser: {msg(e)}"
    if not seen:
        return None, "review_key_not_found"
    return parse_qs(urlparse(seen[0]).query)["apikey"][0], None


def ulta_fetch(ctx, page, apikey, p):
    time.sleep(ULTA_SPACING_S)
    ctx["requests"] += 1
    try:
        res = page.evaluate(FETCH_JS, ULTA_REVIEWS_URL.format(p["row"]["productId"], apikey))
    except Exception as e:
        return f"browser: {msg(e)}", None, None
    if res["status"] in (403, 429):
        return "blocked", None, None
    if res["status"] == 0:
        return "timeout", None, None
    if res["status"] != 200:
        return f"http_{res['status']}", None, None
    try:
        data = json.loads(res["text"])
        first = data["results"][0]
        reviews = first["reviews"]
        assert isinstance(reviews, list)
    except Exception:
        return "invalid", None, None
    for rv in reviews:
        if isinstance(rv.get("details"), dict):
            rv["details"]["nickname"] = None
            rv["details"]["location"] = None
        rv["media"] = None
    return None, reviews, {"total_results": (data.get("paging") or {}).get("total_results"), "rollup": first.get("rollup")}


def ulta_product_page(ctx, page, p):
    """Returns (state, error, offer) for one product page, fetched from inside the open Ulta page. Never raises."""
    sku = p["row"].get("skuId")
    if sku is None:
        return "failed", "sku_missing", None
    time.sleep(ULTA_SPACING_S)
    ctx["requests"] += 1
    try:
        res = page.evaluate(PAGE_FETCH_JS, p["url"])
    except Exception as e:
        return "failed", f"browser: {msg(e)}", None
    try:
        if res["status"] in (403, 429):
            return "failed", f"blocked: http_{res['status']}", None
        if res["status"] != 200:
            return "failed", f"http_{res['status']}", None
        return "fetched", None, product_page_offer(res["text"], sku)
    except ValueError as e:
        return "failed", str(e), None
    except Exception as e:
        return "failed", f"{type(e).__name__}: {msg(e)}", None


# ---------- Apify reviews ----------
def apify_reviews(ctx, retailer, p):
    try:
        if retailer == "chewy":
            actor, cap = CHEWY_REVIEWS
            items = apify(ctx, actor, {"productUrls": [{"url": p["url"]}], "maxReviews": 10, "maxReviewsPerProduct": 10, "sort": "newest"}, cap)
            ok = bool(items) and all("reviewId" in i for i in items)
        else:
            actor, cap = ECOM
            items = apify(ctx, actor, {"reviewDetailsUrls": [{"url": p["url"]}], "maxReviewResults": 10,
                                       "sortReview": "Most recent", "additionalReviewProperties": True}, cap)
            ok = bool(items) and all("reviewBody" in i and "datePublished" in i and i.get("inputUrl") == p["url"] for i in items)
    except Fail as f:
        return f.reason, None, None
    if not ok:
        return "invalid", None, None
    for i in items:
        i.pop("reviewerName" if retailer == "chewy" else "author", None)
    return None, items, None


# ---------- cell ----------
def product_key_url(r, row):
    if r == "ulta":
        return f"ulta:{row['productId']}", row["action"]["url"]
    if r == "target":
        return f"target:{row['tcin']}", row["url"]
    if r == "sephora":
        return f"sephora:{row['productId']}", row["productUrl"]
    return f"chewy:{row['partNumber']}", row["url"]


def listed_count(r, row):
    v = {"sephora": row.get("reviews"), "chewy": row.get("ratingCount")}.get(r, row.get("reviewCount"))
    return int(v) if v not in (None, "") else 0


def list_rows(ctx, cell, page):
    r = cell["retailer"]
    if r == "ulta":
        rows = ulta_list(ctx, page, cell["list_url"])
    elif r == "target":
        rows = apify(ctx, "automation-lab~target-scraper", {"searchQueries": [cell["search_term"]], "maxProductsPerSearch": 24,
                     "maxSearchPages": 1, "storeId": "2581", "zipCode": "95054", "sort": "relevance"}, "0.05")
    elif r == "sephora":
        rows = apify(ctx, "igview-owner~sephora-search-scraper", {"keyword": cell["search_term"], "maxPages": 1, "pageSize": 10,
                     "sortBy": "BEST_SELLING", "minRating": 1, "minPrice": 0, "maxPrice": 10000}, "0.35")
    else:
        rows = apify(ctx, "parseforge~chewy-com-scraper", {"searchTerm": cell["search_term"], "maxItems": 15}, "0.15")
    if not rows:
        raise Fail("list_empty")
    if not all(isinstance(x, dict) and all(k in x for k in ROW_KEYS[r]) for x in rows) or \
            (r == "ulta" and not all(isinstance(x.get("action"), dict) and "url" in x["action"] for x in rows)):
        raise Fail("list_shape_changed")
    if r == "target":
        rows.sort(key=lambda x: x["position"])
        if any(x["storeId"] != "2581" for x in rows):
            raise Fail("store_mismatch")
    elif r == "sephora":
        rows.sort(key=lambda x: (x["page"], x["position"]))
    return rows


def set_state(p, state, error=None, meta=None):
    p["raw"]["reviews_state"], p["raw"]["reviews_error"], p["raw"]["reviews_meta"] = state, error, meta


def run_cell(ctx, cell):
    r = cell["retailer"]
    ctx["pending"] = []
    out = {"retailer": r, "status": "could_not_look", "reason": "", "selected": 0}
    with ExitStack() as stack:
        page = None
        try:
            if r == "ulta":
                try:
                    from playwright.sync_api import sync_playwright
                    pw = stack.enter_context(sync_playwright())
                    browser = pw.chromium.launch(headless=True, channel="chrome")
                    stack.callback(browser.close)
                    page = browser.new_context(locale="en-US").new_page()
                except Exception as e:
                    raise Fail(f"browser: {msg(e)}")
            rows = list_rows(ctx, cell, page)
            listed_at = now()
            picked = select(r, rows, cell)
            if not picked:
                raise Fail("brand_matched_none")
        except Fail as f:
            out["reason"] = f.reason
            return out
        products = []
        for rank, row in enumerate(picked, 1):
            key, url = product_key_url(r, row)
            p = {"key": key, "url": url, "row": row, "n": listed_count(r, row), "fetched_at": listed_at,
                 "raw": {"retailer": r, "rank": rank, "listing_item": row}}
            p["raw"]["product_page"] = None if r != "ulta" else \
                {"state": "not_attempted", "error": None, "sku": None, "price": None, "currency": None, "availability": None}
            set_state(p, "none" if not p["n"] else "not_attempted")
            products.append(p)
        ctx["pending"] = products
        if r == "ulta":
            pfails = 0
            for p in products:
                state, err, offer = ulta_product_page(ctx, page, p)
                p["raw"]["product_page"] = {"state": state, "error": err, "sku": None, "price": None, "currency": None, "availability": None, **(offer or {})}
                pfails = pfails + 1 if state == "failed" else 0
                if (err or "").startswith("blocked: ") or pfails >= MAX_FAILURES_IN_A_ROW:
                    break
        todo = [p for p in products if p["n"]]
        fetch = None
        if todo and r == "ulta":
            apikey, err = ulta_find_key(ctx, page, todo[0]["url"])
            if err:
                for p in todo:
                    set_state(p, "failed", err)
                todo = []
            fetch = lambda p: ulta_fetch(ctx, page, apikey, p)
        elif todo:
            fetch = lambda p: apify_reviews(ctx, r, p)
        fails, stop = 0, False
        for p in todo:
            if stop:
                continue
            err, reviews, meta = fetch(p)
            ts = now()
            if err:
                set_state(p, "failed", err)
                fails += 1
            else:
                set_state(p, "fetched", None, meta)
                fails = 0
                for rv in reviews:
                    url = p["url"] if r == "ulta" else rv["sourceUrl"] if r == "chewy" else rv["inputUrl"]
                    write(ctx, review_key(p["key"], r, rv), "review", url, {"retailer": r, "product_key": p["key"], "review": rv}, ts)
            stop = err == "blocked" or fails >= MAX_FAILURES_IN_A_ROW
    flush_pending(ctx)
    errs = [p["raw"]["reviews_error"] for p in products if p["raw"]["reviews_state"] == "failed"]
    other = [e for e in errs if e not in ("blocked", "review_key_not_found")]
    n_not = sum(p["raw"]["reviews_state"] == "not_attempted" for p in products)
    parts = (["review_key_not_found"] if "review_key_not_found" in errs else []) + (["reviews_blocked"] if "blocked" in errs else []) \
        + ([f"reviews_failed={len(other)}"] if other else []) + ([f"reviews_not_attempted={n_not}"] if n_not else [])
    pstates = [p["raw"]["product_page"]["state"] for p in products if p["raw"]["product_page"]]
    parts += ([f"product_pages_failed={pstates.count('failed')}"] if "failed" in pstates else []) \
        + ([f"product_pages_not_attempted={pstates.count('not_attempted')}"] if "not_attempted" in pstates else [])
    out.update(status="partial" if parts else "ok", reason="; ".join(parts), selected=len(products))
    return out


def flush_pending(ctx):
    for p in ctx["pending"]:
        write(ctx, p["key"], "product", p["url"], p["raw"], p["fetched_at"])
    ctx["pending"] = []


# ---------- brand ----------
def run_brand(slug, token):
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    d = HERE / "raw" / slug
    d.mkdir(parents=True, exist_ok=True)
    part = d / f"{run_id}.jsonl.part"
    ctx = {"fh": open(part, "w", encoding="utf-8"), "kinds": {}, "token": token, "requests": 0, "runs": {}, "pending": []}
    cells, failed = [], False
    try:
        for cell in json.load(open(HERE / "brand_inputs.json"))[slug]:
            cells.append(run_cell(ctx, cell))
        statuses = {c["status"] for c in cells}
        status = "ok" if statuses == {"ok"} else "could_not_look" if statuses == {"could_not_look"} else "partial"
        reason = " | ".join(f"{c['retailer']}: {c['reason']}" for c in cells if c["status"] != "ok")
    except Exception as e:
        failed = True
        flush_pending(ctx)
        status = "partial" if sum(ctx["kinds"].values()) else "could_not_look"
        reason = f"exception: {type(e).__name__}: {e}"
    cost = apify_cost(ctx) if ctx["runs"] else 0
    ctx["fh"].close()
    part.rename(d / f"{run_id}.jsonl")
    result = {"source": "retail_shelf", "brand": slug, "run_id": run_id, "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "finished_at": now(), "status": status, "reason": reason, "records": sum(ctx["kinds"].values()),
              "records_by_kind": ctx["kinds"], "expected_total": None, "requests": ctx["requests"], "cost_usd": cost,
              "extra": {"cells": cells}}
    (d / f"{run_id}.run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{slug}: {status} {reason}".strip(), flush=True)
    return failed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()  # invalid arguments exit 2
    slugs = [b["slug"] for b in json.load(open(HERE.parent / "brands.json"))]
    if args.brand and args.brand not in slugs:
        ap.error(f"unknown brand {args.brand}")
    token = load_token()
    failed = [run_brand(s, token) for s in (slugs if args.all else [args.brand])]
    sys.exit(1 if any(failed) else 0)


if __name__ == "__main__":
    main()
