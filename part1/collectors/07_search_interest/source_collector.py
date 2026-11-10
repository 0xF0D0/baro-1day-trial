"""Raw collector for source 7: Google Trends weekly interest (see spec.md)."""
import argparse
import json
import sys
import time
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
NAV_TIMEOUT_S = 45
TIMESERIES_TIMEOUT_S = 20
NAV_SPACING_S = 28
HOME_URL = "https://trends.google.com/trends/"
MULTILINE_PATH = "/trends/api/widgetdata/multiline"

# Process state. stopped: None, "blocked" or "home: <message>".
# compared: None until step 2 runs, then the fetch_series result.
state = {"window": None, "last_nav_start": None, "stopped": None, "compared": None}
hits = []  # (response, received_at) for multiline responses


def make_window(today: date) -> str:
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:  # Feb 29
        start = today.replace(year=today.year - 1, day=28)
    return f"{start.isoformat()} {today.isoformat()}"


def explore_url(terms, window):
    q = ",".join(urllib.parse.quote(t, safe="") for t in terms)
    return ("https://trends.google.com/trends/explore?date="
            + urllib.parse.quote(window, safe="") + "&geo=US&q=" + q)


def parse_multiline(url, body, terms, window):
    if not body.startswith(")]}'") or "\n" not in body:
        raise ValueError("no_prefix")
    try:
        data = json.loads(body.split("\n", 1)[1])
    except json.JSONDecodeError:
        raise ValueError("bad_json")
    req = json.loads(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["req"][0])
    if req.get("time") != window:
        raise ValueError("time")
    if req.get("resolution") != "WEEK":
        raise ValueError("resolution")
    items = req.get("comparisonItem", [])
    kws = [c["complexKeywordsRestriction"]["keyword"] for c in items]
    if any(len(k) != 1 for k in kws) or [k[0]["value"] for k in kws] != list(terms):
        raise ValueError("terms")
    points = data.get("default", {}).get("timelineData") if isinstance(data, dict) else None
    if not isinstance(points, list) or not points:
        raise ValueError("timelineData")
    for i, p in enumerate(points):
        for key in ("time", "value", "hasData"):
            if key not in p:
                raise ValueError(f"point_{i}_missing_{key}")
        for key in ("value", "hasData"):
            if not isinstance(p[key], list) or len(p[key]) != len(terms):
                raise ValueError(f"point_{i}_length")
    for i in range(len(points) - 1):
        if int(points[i + 1]["time"]) - int(points[i]["time"]) != 604800:
            raise ValueError(f"gap_after_point_{i}")
    return req, points


def utc_now(fmt="%Y-%m-%dT%H:%M:%SZ"):
    return datetime.now(timezone.utc).strftime(fmt)


def short(e):
    return str(e).split("\n")[0]


def is_blocked(page, response):
    if urllib.parse.urlparse(page.url).hostname != "trends.google.com":
        return True
    if response is not None and response.status >= 400:
        return True
    try:
        text = page.inner_text("body").lower()
    except Exception:
        text = ""
    return "unusual traffic" in text


def navigate(page, url, run, label):
    """Returns None on success, else the error string. Respects the stop state and spacing."""
    if state["stopped"]:
        return state["stopped"]
    if state["last_nav_start"] is not None:
        wait = NAV_SPACING_S - (time.monotonic() - state["last_nav_start"])
        if wait > 0:
            time.sleep(wait)
    state["last_nav_start"] = time.monotonic()
    run["requests"] += 1
    hits.clear()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_S * 1000)
    except Exception as e:
        return f"{label}: {short(e)}"
    if is_blocked(page, response):
        state["stopped"] = "blocked"
        return "blocked"
    return None


def fetch_series(page, terms, run):
    err = navigate(page, explore_url(terms, state["window"]), run, "navigation")
    if err:
        return {"ok": False, "error": err}
    deadline = time.monotonic() + TIMESERIES_TIMEOUT_S
    while not hits and time.monotonic() < deadline:
        page.wait_for_timeout(250)
    if not hits:
        return {"ok": False, "error": "timeout"}
    response, fetched_at = hits[0]
    try:
        if response.status != 200:
            return {"ok": False, "error": f"http_{response.status}"}
        req, points = parse_multiline(response.url, response.text(), terms, state["window"])
    except ValueError as e:
        return {"ok": False, "error": f"shape_changed: {e}"}
    return {"ok": True, "req": req, "points": points, "url": explore_url(terms, state["window"]),
            "fetched_at": fetched_at}


def run_brand(page, browser_error, slug, term, comparison_set):
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out_dir = HERE / "raw" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    part = out_dir / f"{run_id}.jsonl.part"
    run = {"requests": 0}
    by_kind = {}
    solo = compared = None
    exc = None
    with part.open("w", encoding="utf-8") as f:
        def write(kind, key, series, point, index):
            rec = {"key": key, "kind": kind, "url": series["url"], "fetched_at": series["fetched_at"],
                   "raw": {"point": point, "series_index": index, "request": series["req"]}}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            by_kind[kind] = by_kind.get(kind, 0) + 1
        try:
            if not browser_error:
                if state["compared"] is None:
                    err = navigate(page, HOME_URL, run, "home")
                    if err and err.startswith("home:"):
                        state["stopped"] = err
                    state["compared"] = fetch_series(page, comparison_set, run)
                solo = fetch_series(page, [term], run)
                compared = state["compared"]
                if solo["ok"]:
                    for p in solo["points"]:
                        write("interest_point", f"{term}|US|{p['time']}", solo, p, 0)
                if compared["ok"]:
                    suffix = "|vs:" + ",".join(comparison_set)
                    for p in compared["points"]:
                        write("interest_point_compared", f"{term}|US|{p['time']}{suffix}", compared, p,
                              comparison_set.index(term))
        except Exception as e:
            exc = f"exception: {type(e).__name__}: {e}"
    part.rename(part.with_suffix(""))  # .jsonl.part -> .jsonl
    total = sum(by_kind.values())
    if browser_error:
        status, reason = "could_not_look", f"browser: {browser_error}"
    elif exc:
        status, reason = ("partial" if total else "could_not_look"), exc
    elif not solo["ok"] and not compared["ok"]:
        status, reason = "could_not_look", f"solo: {solo['error']}; compared: {compared['error']}"
    elif not solo["ok"]:
        status, reason = "partial", f"solo: {solo['error']}"
    elif not compared["ok"]:
        status, reason = "partial", f"compared: {compared['error']}"
    else:
        status, reason = "ok", ""
    result = {"source": "search_interest", "brand": slug, "run_id": run_id,
              "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "finished_at": utc_now(),
              "status": status, "reason": reason, "records": total, "records_by_kind": by_kind,
              "expected_total": None, "requests": run["requests"], "cost_usd": 0,
              "extra": {"window": state["window"]}}
    (out_dir / f"{run_id}.run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(f"{slug} {status} {total} {reason}")
    return exc is None


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()  # bad arguments exit 2
    slugs = [b["slug"] for b in json.loads((HERE.parent / "brands.json").read_text(encoding="utf-8"))]
    inputs = json.loads((HERE / "brand_inputs.json").read_text(encoding="utf-8"))
    if args.brand and args.brand not in slugs:
        print(f"unknown brand: {args.brand}", file=sys.stderr)
        return 2
    comparison_set = [inputs[s]["term"] for s in slugs]
    state["window"] = make_window(datetime.now(ZoneInfo("America/New_York")).date())
    wanted = slugs if args.all else [args.brand]

    from playwright.sync_api import sync_playwright
    all_ok = True
    with sync_playwright() as p:
        page = browser_error = None
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
            context = browser.new_context(locale="en-US", timezone_id="America/New_York",
                                          viewport={"width": 1400, "height": 950})
            page = context.new_page()
            page.on("response", lambda r: hits.append((r, utc_now()))
                    if urllib.parse.urlparse(r.url).path == MULTILINE_PATH else None)
        except Exception as e:
            browser_error = short(e)
        for slug in wanted:
            all_ok &= run_brand(page, browser_error, slug, inputs[slug]["term"], comparison_set)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
