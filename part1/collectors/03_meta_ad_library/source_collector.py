"""Raw collector for the Meta Ad Library. See spec.md."""
import argparse, json, re, sys, time
import urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

COUNT_TIMEOUT_S, SITE_SPACING_S, RESULTS_MARGIN, RESULTS_MAX = 30, 15, 50, 1000
PRICE_USD, RUN_TIMEOUT_S, WAIT_LIMIT_S = 0.0058, 1800, 2100
HTTP_TIMEOUT_S, MEDIA_TIMEOUT_S, MEDIA_SPACING_S = 90, 60, 1
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
ACTOR, SOURCE = "apify~facebook-ads-scraper", "meta_ad_library"
TERMINAL = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parents[2] / ".env"
LIST_URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US"
            "&view_all_page_id={}&search_type=page&media_type=all")
_last_site_nav = None
_last_media = None


def parse_site_count(html: str) -> int:
    for m in re.finditer(r'<script type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>', html, re.S):
        text = m.group(1)
        if "search_results_connection" not in text:
            continue
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ValueError(f"bad json: {e}")
        found = _find_key(data)
        if found is None:
            raise ValueError("search_results_connection not found")
        count = found.get("count") if isinstance(found, dict) else None
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"bad count: {count!r}")
        return count
    raise ValueError("no data block with search_results_connection")


def _find_key(node):
    if isinstance(node, dict):
        if "search_results_connection" in node:
            return node["search_results_connection"]
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for c in children:
        r = _find_key(c)
        if r is not None:
            return r
    return None


def media_targets(item):
    snap = item.get("snapshot") or {}
    out = []

    def add(path, obj, key):
        url = obj.get(key)
        if url:
            out.append((f"{path}.{key}", url))

    for i, im in enumerate(snap.get("images") or []):
        add(f"snapshot.images[{i}]", im, "originalImageUrl")
    for i, v in enumerate(snap.get("videos") or []):
        add(f"snapshot.videos[{i}]", v, "videoSdUrl")
        add(f"snapshot.videos[{i}]", v, "videoPreviewImageUrl")
    for i, c in enumerate(snap.get("cards") or []):
        for k in ("originalImageUrl", "videoSdUrl", "videoPreviewImageUrl"):
            add(f"snapshot.cards[{i}]", c, k)
    return out


def remove_partner_fields(item):
    snap = item["snapshot"]
    bc = snap.get("brandedContent")
    page_differs = str(snap.get("pageId")) != str(item.get("pageId"))
    bc_differs = isinstance(bc, dict) and str(bc.get("pageId")) != str(item.get("pageId"))
    if page_differs:
        for k in ("pageName", "pageProfileUri", "pageProfilePictureUrl", "pageId"):
            snap[k] = None
    if bc_differs:
        for k in ("pageName", "pageProfileUri", "pageId"):
            bc[k] = None


def read_token():
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("APIFY_TOKEN="):
                v = line.split("=", 1)[1].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1]
                return v.strip()
    except OSError:
        pass
    return ""


def now_z():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def api(S, url, token, body=None):
    S["requests"] += 1
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
        return json.loads(r.read())


def err(e):
    return f"http_{e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__


def fetch_media(S, brand, url):
    """Returns relative path or None."""
    global _last_media
    name = urlparse(url).path.rsplit("/", 1)[-1]
    dest = HERE / "media" / brand / name
    rel = f"media/{brand}/{name}"
    if dest.exists():
        return rel
    if _last_media is not None:
        time.sleep(max(0, MEDIA_SPACING_S - (time.time() - _last_media)))
    S["requests"] += 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=MEDIA_TIMEOUT_S) as r:
            ok, body = r.status == 200, r.read()
    except Exception:
        _last_media = time.time()
        return None
    _last_media = time.time()
    if not ok:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return rel


def get_counts(S, page_ids):
    """Fills S['counts']; adds page reasons to S['reasons'] and S['bad']."""
    global _last_site_nav
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception as e:
            S["browser_err"] = str(e)
            return
        try:
            page = browser.new_context(locale="en-US").new_page()
            bodies = []

            def on_response(r):
                if r.request.resource_type == "document":
                    try:
                        bodies.append(r.text())
                    except Exception:
                        pass
            page.on("response", on_response)
            blocked = False
            for pid in page_ids:
                if blocked:
                    S["bad"].add(pid); S["reasons"].append(f"not_attempted({pid})")
                    continue
                bodies.clear()
                if _last_site_nav is not None:
                    time.sleep(max(0, SITE_SPACING_S - (time.time() - _last_site_nav)))
                t0 = time.time()
                S["requests"] += 1
                try:
                    page.goto(LIST_URL.format(pid), wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass
                _last_site_nav = time.time()
                while not any("search_results_connection" in b for b in bodies) and time.time() - t0 < COUNT_TIMEOUT_S:
                    page.wait_for_timeout(500)
                body = next((b for b in bodies if "search_results_connection" in b), None)
                if body is None:
                    u = urlparse(page.url)
                    S["bad"].add(pid)
                    if u.hostname != "www.facebook.com" or u.path.startswith(("/checkpoint", "/login")):
                        blocked = True
                        S["reasons"].append(f"blocked({pid})")
                    else:
                        S["reasons"].append(f"count_timeout({pid})")
                    continue
                try:
                    S["counts"][pid] = parse_site_count(body)
                except ValueError:
                    S["bad"].add(pid); S["reasons"].append(f"count_shape_changed({pid})")
        finally:
            browser.close()


def fetch_items(S, pid, count, token):
    """Runs the Actor for one page. Returns (run, items) or None after adding a reason."""
    def fail(name, detail=""):
        S["bad"].add(pid); S["reasons"].append(f"{name}({pid})" + (f": {detail}" if detail else ""))
    limit = min(count + RESULTS_MARGIN, RESULTS_MAX)
    cap = -(-limit * 58 // 100) / 100
    url = (f"https://api.apify.com/v2/acts/{ACTOR}/runs?timeout={RUN_TIMEOUT_S}&maxItems={limit}"
           f"&maxTotalChargeUsd={cap}&waitForFinish=60")
    body = {"startUrls": [{"url": LIST_URL.format(pid)}], "resultsLimit": limit, "activeStatus": "active",
            "onlyTotal": False, "includeAboutPage": False, "isDetailsPerAd": False,
            "enrichWithEcommerceData": False}
    t0 = time.time()
    try:
        run = api(S, url, token, body)["data"]
    except Exception as e:
        fail("apify_start_failed", err(e)); return None
    S["runs"][pid] = run.get("id")
    while run.get("status") not in TERMINAL:
        if time.time() - t0 > WAIT_LIMIT_S:
            fail("apify_wait_exceeded"); return None
        try:
            run = api(S, f"https://api.apify.com/v2/actor-runs/{run['id']}?waitForFinish=60", token)["data"]
        except Exception as e:
            fail("apify_poll_failed", err(e)); return None
    try:
        items = api(S, f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?format=json&clean=1", token)
    except Exception as e:
        fail("apify_dataset_failed", err(e)); return None
    S["cost"] += len(items) * PRICE_USD
    if run["status"] != "SUCCEEDED":
        fail("apify_run_" + run["status"].lower().replace("-", "_"))
    return run, items


def good_shape(it):
    if not isinstance(it, dict):
        return False
    a, s = it.get("adArchiveID"), it.get("snapshot")
    return (isinstance(a, str) and a.isdigit() and isinstance(s, dict)
            and all(isinstance(s.get(k), list) for k in ("images", "videos", "cards")))


def write_page(S, slug, pid, count, run, items):
    if not all(good_shape(it) for it in items):
        S["bad"].add(pid); S["reasons"].append(f"apify_shape_changed({pid})")
        return
    n = len({it["adArchiveID"] for it in items})
    if n < count:
        S["bad"].add(pid); S["reasons"].append(f"incomplete({pid}): got={n} count={count}")
    for it in items:
        ad = it["adArchiveID"]
        if ad in S["seen"]:
            continue
        S["seen"].add(ad)
        remove_partner_fields(it)
        media = {field: fetch_media(S, slug, url) for field, url in media_targets(it)}
        S["media_files"] += len(media)
        S["media_failed"] += sum(v is None for v in media.values())
        rec = {"key": ad, "kind": "ad", "url": f"https://www.facebook.com/ads/library/?id={ad}",
               "fetched_at": run["finishedAt"][:19] + "Z", "raw": {"page_id": pid, "item": it, "media": media}}
        S["fh"].write(json.dumps(rec, ensure_ascii=False) + "\n")
        S["fh"].flush()
        S["records"] += 1


def collect(slug, S, token):
    page_ids = json.loads((HERE / "brand_inputs.json").read_text())[slug]["page_ids"]
    S["page_ids"] = page_ids
    if not token:
        S["missing"] = True
        return
    get_counts(S, page_ids)
    if S["browser_err"]:
        return
    for pid in page_ids:
        count = S["counts"].get(pid)
        if pid in S["bad"] or not count:
            continue
        got = fetch_items(S, pid, count, token)
        if got:
            write_page(S, slug, pid, count, *got)


def decide(S):
    if S["missing"]:
        return "could_not_look", "missing_token"
    if S["browser_err"]:
        return "could_not_look", f"browser: {S['browser_err']}"
    if not S["reasons"] and S["media_failed"] == 0:
        return "ok", ""
    if S["records"] == 0:
        return "could_not_look", "; ".join(S["reasons"])
    extra = [f"media_failed={S['media_failed']}"] if S["media_failed"] else []
    return "partial", "; ".join(S["reasons"] + extra)


def run_brand(slug) -> int:
    started = now_z()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = HERE / "raw" / slug
    out.mkdir(parents=True, exist_ok=True)
    part = out / f"{run_id}.jsonl.part"
    S = {"requests": 0, "cost": 0.0, "records": 0, "counts": {}, "runs": {}, "media_files": 0, "media_failed": 0,
         "reasons": [], "bad": set(), "seen": set(), "browser_err": None, "missing": False, "page_ids": [],
         "fh": part.open("w", encoding="utf-8")}
    code = 0
    try:
        collect(slug, S, read_token())
        status, reason = decide(S)
    except Exception as e:
        code = 1
        status = "partial" if S["records"] else "could_not_look"
        reason = f"exception: {type(e).__name__}: {e}"
    S["fh"].close()
    part.rename(out / f"{run_id}.jsonl")
    complete = bool(S["page_ids"]) and all(p in S["counts"] for p in S["page_ids"])
    result = {"source": SOURCE, "brand": slug, "run_id": run_id, "started_at": started, "finished_at": now_z(),
              "status": status, "reason": reason, "records": S["records"], "records_by_kind": {"ad": S["records"]},
              "expected_total": sum(S["counts"].values()) if complete else None,
              "requests": S["requests"], "cost_usd": round(S["cost"], 4),
              "extra": {"counts": S["counts"], "runs": S["runs"], "media_files": S["media_files"],
                        "media_failed": S["media_failed"]}}
    (out / f"{run_id}.run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return code


def main():
    slugs = [b["slug"] for b in json.loads((HERE.parent / "brands.json").read_text())]
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand", choices=slugs)
    g.add_argument("--all", action="store_true")
    a = ap.parse_args()
    codes = [run_brand(s) for s in (slugs if a.all else [a.brand])]
    return 1 if 1 in codes else 0


if __name__ == "__main__":
    sys.exit(main())
