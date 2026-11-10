"""Raw collector for the Google Ads Transparency Center. See spec.md."""
import argparse
import copy
import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SOURCE = "google_ads_transparency"
HOST = "adstransparency.google.com"
LIST_TIMEOUT_S = 30
PAGE_TIMEOUT_S = 10
SCROLL_EVERY_S = 2.5
MAX_LIST_RESPONSES = 50
DETAIL_WINDOW_DAYS = 7
DETAIL_TIMEOUT_S = 20
DETAIL_SPACING_S = 10
DETAIL_REFRESH_HOURS = 24
MAX_FAILURES_IN_A_ROW = 5
SCRIPT_TIMEOUT_S = 20


def parse_list(resp):
    if not isinstance(resp, dict):
        raise ValueError("response is not an object")
    items = resp.get("1", [])
    if not isinstance(items, list):
        raise ValueError("'1' is not a list")
    for it in items:
        if not isinstance(it, dict) or not all(k in it for k in ("1", "2", "4")) or "1" not in (it.get("7") or {}):
            raise ValueError("list item lacks 1, 2, 4 or 7.1")
    lo = int(resp["4"]) if "4" in resp else None
    hi = int(resp["5"]) if "5" in resp else None
    return items, resp.get("2"), lo, hi


def in_scope(item, run_start_epoch):
    return int(item["7"]["1"]) >= run_start_epoch - DETAIL_WINDOW_DAYS * 86400


def recent_details(brand_dir, start_epoch):
    """Keys whose detail was fetched within DETAIL_REFRESH_HOURS before start_epoch, per earlier record files."""
    keys = set()
    low = start_epoch - DETAIL_REFRESH_HOURS * 3600
    try:
        files = sorted(Path(brand_dir).glob("*.jsonl"))
    except OSError:
        return keys
    for f in files:
        try:
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                        if r["raw"]["detail_state"] != "fetched":
                            continue
                        t = datetime.strptime(r["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
                        if low <= t < start_epoch:
                            keys.add(r["key"])
                    except Exception:
                        continue
        except Exception:
            continue
    return keys


def script_urls(detail):
    out = {}
    for i, v in enumerate(detail["5"]):
        url = (v.get("1") or {}).get("4")
        if url:
            out[i] = url
    return out


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now():
    return datetime.now(timezone.utc)


class Browsing:
    """One page plus the captured responses and the request counter of one brand."""

    def __init__(self, ctx, st, nav):
        self.ctx, self.st, self.nav = ctx, st, nav  # nav: process-wide {"started": bool}
        self.page = ctx.new_page()
        self.lists, self.details = [], []
        self.page.on("response", self.on_response)

    def on_response(self, r):
        if "/SearchService/SearchCreatives" in r.url:
            target = self.lists
        elif "/LookupService/GetCreativeById" in r.url:
            target = self.details
        else:
            return
        try:
            body = json.loads(r.text())
        except Exception:
            body = None
        target.append((r.status, body, now()))

    def go(self, url, timeout_s):
        if self.nav["started"]:
            time.sleep(DETAIL_SPACING_S)
        self.nav["started"] = True
        self.st["requests"] += 1
        return self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)

    def blocked(self, resp):
        """None when not blocked, else a dict naming the first matching signal."""
        u = urlparse(self.page.url)
        sig = {"host": u.hostname, "path": u.path, "status": resp.status if resp is not None else None}
        if u.hostname != HOST:
            return {"check": "host", **sig}
        if resp is not None and resp.status >= 400:
            return {"check": "status", **sig}
        try:
            if "unusual traffic" in self.page.inner_text("body"):
                return {"check": "text", **sig}
        except Exception:
            pass
        return None

    def signal(self, sig, **extra):
        if self.st["block_signal"] is None:
            self.st["block_signal"] = {**sig, **extra}

    def poll(self, cond, timeout_s):
        end = time.monotonic() + timeout_s
        while not cond():
            if time.monotonic() >= end:
                return False
            self.page.wait_for_timeout(250)
        return True


def collect_list(b, st, cfg):
    """Returns (ads, complete, first_totals); ads is a list of (item, arrival). Raises Stop(status, reason)."""
    lists, ads = b.lists, {}
    done = 0

    def absorb():
        nonlocal done
        tok = None
        for status, body, t in lists[done:]:
            if status != 200:
                b.signal({"check": "rpc_status", "rpc": "SearchCreatives", "status": status, "after_list_responses": done})
                raise ValueError("list status %s" % status)
            items, tok, _, _ = parse_list(body)
            for it in items:
                ads.setdefault(it["2"], (it, t))
        done = len(lists)
        return tok

    url = "https://%s/?region=US&domain=%s&hl=en" % (HOST, cfg["domain"])
    try:
        resp = b.go(url, 45)
    except Exception as e:
        raise Stop("could_not_look", "browser: %s" % e)
    sig = b.blocked(resp)
    if sig:
        b.signal(sig)
        raise Stop("could_not_look", "blocked")
    if not b.poll(lambda: lists, LIST_TIMEOUT_S):
        raise Stop("could_not_look", "list_timeout")
    if lists[0][0] != 200:
        b.signal({"check": "rpc_status", "rpc": "SearchCreatives", "status": lists[0][0]})
        raise Stop("could_not_look", "blocked")
    try:
        _, _, lo, hi = parse_list(lists[0][1])
    except ValueError:
        raise Stop("could_not_look", "list_shape_changed")
    st["totals"] = (lo, hi)
    b.page.wait_for_timeout(2000)
    complete = True
    try:
        tok = absorb()
        if tok:
            try:
                b.page.locator("text=See all ads").first.click(timeout=10000)
            except Exception:
                return list(ads.values()), False
            b.page.wait_for_timeout(3000)
            while tok:
                if len(lists) >= MAX_LIST_RESPONSES:
                    complete = False
                    break
                n = len(lists)

                def fresh():
                    return any(isinstance(body, dict) and any(
                        isinstance(i, dict) and i.get("2") not in ads for i in (body.get("1") or []))
                        for _, body, _ in lists[n:])
                deadline = time.monotonic() + PAGE_TIMEOUT_S
                while True:
                    st["requests"] += 1
                    b.page.mouse.wheel(0, 6000)
                    b.page.keyboard.press("End")
                    if b.poll(fresh, min(SCROLL_EVERY_S, max(0, deadline - time.monotonic()))):
                        break
                    if time.monotonic() >= deadline:
                        break
                if not fresh():
                    for s, _, _ in lists[n:]:
                        if s != 200:
                            b.signal({"check": "rpc_status", "rpc": "SearchCreatives", "status": s, "after_list_responses": n})
                    complete = False
                    break
                tok = absorb()
    except ValueError:
        complete = False
    return list(ads.values()), complete


class Stop(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


def fetch_detail(b, item, n_fetched):
    """Returns (state, error, detail, arrival)."""
    url = "https://%s/advertiser/%s/creative/%s?region=US&hl=en" % (HOST, item["1"], item["2"])
    b.details.clear()
    try:
        resp = b.go(url, DETAIL_TIMEOUT_S)
    except Exception:
        return "failed", "timeout", None, None
    sig = b.blocked(resp)
    if sig:
        b.signal(sig, after_details_fetched=n_fetched)
        return "failed", "blocked", None, None
    if not b.poll(lambda: b.details, DETAIL_TIMEOUT_S):
        return "failed", "timeout", None, None
    status, body, t = b.details[0]
    if status != 200:
        b.signal({"check": "rpc_status", "rpc": "GetCreativeById", "status": status}, after_details_fetched=n_fetched)
        return "failed", "blocked", None, None
    try:
        d = body["1"]
        if d["1"] != item["1"] or d["2"] != item["2"] or not isinstance(d["5"], list):
            raise ValueError
    except Exception:
        return "failed", "invalid", None, None
    return "fetched", None, d, t


def fetch_scripts(b, st, detail, cid, brand_dir, run_id):
    files = {}
    for idx, url in script_urls(detail).items():
        st["requests"] += 1
        try:
            r = b.ctx.request.get(url, timeout=SCRIPT_TIMEOUT_S * 1000)
            if r.status != 200:
                raise ValueError
            rel = "%s.scripts/%s_%d.js.gz" % (run_id, cid, idx)
            (brand_dir / rel).parent.mkdir(exist_ok=True)
            (brand_dir / rel).write_bytes(gzip.compress(r.body()))
            files[str(idx)] = rel
        except Exception:
            files[str(idx)] = None
    return files


def collect(browser, slug, cfg, run_id, start_epoch, brand_dir, out, st, nav):
    if isinstance(browser, str):
        return "could_not_look", "browser: " + browser
    ctx = browser.new_context(locale="en-US", viewport={"width": 1400, "height": 950})
    try:
        b = Browsing(ctx, st, nav)
        try:
            ads, complete = collect_list(b, st, cfg)
        except Stop as s:
            return s.status, s.reason
        lo, hi = st["totals"]
        st["expected_total"] = lo if lo == hi else None
        named = set(cfg["named_advertiser_ids"])
        counts = {"in_scope": 0, "fetched": 0, "failed": 0, "not_attempted": 0, "scripts_failed": 0,
                  "skipped_recent": 0}
        recent = recent_details(brand_dir, start_epoch)
        stopped, fails = False, 0
        for item, arrival in ads:
            item = copy.deepcopy(item)
            detail, files, err, fetched_at = None, {}, None, arrival
            if not in_scope(item, start_epoch):
                state = "skipped_old"
            else:
                counts["in_scope"] += 1
                if "%s/%s" % (item["1"], item["2"]) in recent:
                    state = "skipped_recent"
                elif stopped:
                    state = "not_attempted"
                else:
                    state, err, detail, t = fetch_detail(b, item, counts["fetched"])
                    if state == "fetched":
                        fails, fetched_at = 0, t
                    else:
                        fails += 1
                        stopped = err == "blocked" or fails >= MAX_FAILURES_IN_A_ROW
                counts[state] = counts.get(state, 0) + 1
            if state == "fetched" and item["1"] in named:
                files = fetch_scripts(b, st, detail, item["2"], brand_dir, run_id)
                counts["scripts_failed"] += sum(v is None for v in files.values())
            if item["1"] not in named:
                item["12"] = None
                if detail is not None:
                    detail["22"] = None
            rec = {"key": "%s/%s" % (item["1"], item["2"]), "kind": "ad",
                   "url": "https://%s/advertiser/%s/creative/%s?region=US" % (HOST, item["1"], item["2"]),
                   "fetched_at": iso(fetched_at),
                   "raw": {"list_item": item, "detail": detail, "detail_state": state,
                           "detail_error": err, "script_files": files}}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            st["records"] += 1
        st["extra"] = {"list_complete": complete, "total_min": lo, "total_max": hi,
                       "in_scope": counts["in_scope"], "details_fetched": counts["fetched"],
                       "details_skipped_recent": counts["skipped_recent"]}
        if not ads:
            return "ok", ""
        parts = []
        if not complete:
            parts.append("list_incomplete")
        elif st["expected_total"] is not None and st["expected_total"] != len(ads):
            parts.append("count_mismatch(expected=%d, got=%d)" % (st["expected_total"], len(ads)))
        for key, label in (("failed", "details_failed"), ("not_attempted", "details_not_attempted"),
                           ("scripts_failed", "scripts_failed")):
            if counts[key]:
                parts.append("%s=%d" % (label, counts[key]))
        return ("partial", "; ".join(parts)) if parts else ("ok", "")
    finally:
        ctx.close()


def run_brand(browser, slug, cfg, nav):
    start = now()
    run_id = start.strftime("%Y%m%dT%H%M%SZ")
    brand_dir = HERE / "raw" / slug
    brand_dir.mkdir(parents=True, exist_ok=True)
    part = brand_dir / (run_id + ".jsonl.part")
    st = {"records": 0, "requests": 0, "expected_total": None, "extra": {}, "block_signal": None}
    failed = False
    with part.open("w", encoding="utf-8") as out:
        try:
            status, reason = collect(browser, slug, cfg, run_id, int(start.timestamp()), brand_dir, out, st, nav)
        except Exception as e:
            failed = True
            status = "partial" if st["records"] else "could_not_look"
            reason = "exception: %s: %s" % (type(e).__name__, e)
    part.rename(brand_dir / (run_id + ".jsonl"))
    result = {"source": SOURCE, "brand": slug, "run_id": run_id, "started_at": iso(start),
              "finished_at": iso(now()), "status": status, "reason": reason, "records": st["records"],
              "records_by_kind": {"ad": st["records"]}, "expected_total": st["expected_total"],
              "requests": st["requests"], "cost_usd": 0,
              "extra": {**st["extra"], "block_signal": st["block_signal"]}}
    (brand_dir / (run_id + ".run.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("%s: %s, %d records%s" % (slug, status, st["records"], (", " + reason) if reason else ""))
    return failed


def main():
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.brand and args.brand not in inputs:
        ap.error("unknown brand: %s" % args.brand)
    slugs = list(inputs) if args.all else [args.brand]
    from playwright.sync_api import sync_playwright
    nav, failed = {"started": False}, False
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception as e:
            browser = str(e)
        for slug in slugs:
            failed |= run_brand(browser, slug, inputs[slug], nav)
        if not isinstance(browser, str):
            browser.close()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
