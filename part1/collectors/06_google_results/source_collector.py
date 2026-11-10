"""Raw collector for source 6 (Google search results via Apify). See spec.md."""
import argparse, copy, json, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
API = "https://api.apify.com"
FINISHED = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
START = "/v2/acts/apify~google-search-scraper/runs?maxTotalChargeUsd=0.5&timeout=600&memory=1024"


def actor_input(keywords):
    off = {"enable": False}
    return {"queries": "\n".join(keywords), "maxPagesPerQuery": 1, "countryCode": "us", "languageCode": "en",
            "focusOnPaidAds": False, "mobileResults": False, "includeUnfilteredResults": False,
            "saveHtml": False, "saveHtmlToKeyValueStore": False, "includeIcons": False,
            "aiOverview": {"scrapeFullAiOverview": False}, "aiModeSearch": {"enableAiMode": False},
            "geminiSearch": {"enableGemini": False}, "chatGptSearch": {"enableChatGpt": False},
            "copilotSearch": {"enableCopilot": False},
            "perplexitySearch": {"enablePerplexity": False, "returnImages": False, "returnRelatedQuestions": False},
            "maximumLeadsEnrichmentRecords": 0, "verifyLeadsEnrichmentEmails": False,
            "websiteContentScraper": off}


def search_url(term):
    return "https://www.google.com/search?" + urllib.parse.urlencode({"q": term, "gl": "us", "hl": "en"})


def match(keywords, items):
    out = []
    for term in keywords:
        item = next((i for i in items if isinstance(i, dict) and isinstance(i.get("searchQuery"), dict)
                     and i["searchQuery"].get("term") == term), None)
        if item is None:
            out.append((None, "missing"))
        elif item.get("#error") is not False:
            out.append((item, "actor_error"))
        elif not isinstance(item.get("organicResults"), list) or not item["organicResults"]:
            out.append((item, "no_organic_results"))
        else:
            out.append((item, None))
    return out


def remove_names(item):
    item = copy.deepcopy(item)
    for r in item.get("organicResults") or []:
        if isinstance(r, dict) and isinstance(r.get("websiteTitle"), str) and "·" in r["websiteTitle"]:
            r["websiteTitle"] = None
    return item


def read_token():
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def call(st, method, path, timeout, expect, body=None):
    """One HTTP request. Returns parsed JSON; raises RuntimeError(description) on any failure."""
    st["requests"] += 1
    headers = {"Authorization": "Bearer " + st["token"]}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:
        raise RuntimeError(str(e))
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
    if status != expect:
        typ = parsed.get("error", {}).get("type") if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict) else None
        raise RuntimeError("http_%s%s" % (status, ": " + typ if typ else ""))
    return parsed


def read_run(st, run_id, wait=False):
    path = "/v2/actor-runs/%s%s" % (run_id, "?waitForFinish=60" if wait else "")
    data = call(st, "GET", path, 90 if wait else 30, 200)["data"]
    st["status"] = data["status"]
    st["cost"] = data.get("usageTotalUsd", st["cost"])
    return data


def collect(st, keywords, out):
    """Steps 1-7. Returns (status, reason); writes records to the open file `out`."""
    if not st["token"]:
        return "could_not_look", "missing_token"
    try:
        d = call(st, "POST", START, 30, 201, actor_input(keywords))["data"]
        run_id, dataset_id = d["id"], d["defaultDatasetId"]
        st["run_id"] = run_id
    except Exception as e:
        return "could_not_look", "apify_start: %s" % e
    try:
        run = read_run(st, run_id, wait=True)
        while run["status"] not in FINISHED:
            run = read_run(st, run_id, wait=True)
    except Exception as e:
        return "could_not_look", "apify_wait: %s" % e
    try:
        items = call(st, "GET", "/v2/datasets/%s/items?format=json" % dataset_id, 60, 200)
        if not isinstance(items, list):
            raise RuntimeError("not a JSON list")
    except Exception as e:
        return "could_not_look", "apify_dataset: %s" % e
    pages = sum(1 for i in items if isinstance(i, dict) and i.get("#error") is False)
    try:
        for n in range(12):
            if (run.get("chargedEventCounts") or {}).get("search-page-scraped", 0) >= pages:
                break
            if n:
                time.sleep(5)
            run = read_run(st, run_id)
    except Exception:
        pass
    matched = match(keywords, items)
    errors = [e for _, e in matched]
    if all(e is not None for e in errors):
        return "could_not_look", "no_results: apify_status=%s" % st["status"]
    finished = run.get("finishedAt")
    fetched_at = finished[:19] + "Z" if finished else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i, (term, (item, err)) in enumerate(zip(keywords, matched), 1):
        rec = {"key": term, "kind": "search_results_page", "url": search_url(term), "fetched_at": fetched_at,
               "raw": {"keyword_index": i, "serp": remove_names(item) if item else None, "error": err,
                       "ads": "could_not_look"}}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        st["records"] += 1
    parts = ["%s=%d" % (k, errors.count(k)) for k in ("missing", "actor_error", "no_organic_results") if errors.count(k)]
    if st["status"] != "SUCCEEDED":
        parts.append("apify_status=%s" % st["status"])
    return ("partial", "; ".join(parts)) if parts else ("ok", "")


def run_brand(slug, keywords, token):
    ts = lambda: datetime.now(timezone.utc)
    started = ts()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    d = HERE / "raw" / slug
    d.mkdir(parents=True, exist_ok=True)
    part = d / (run_id + ".jsonl.part")
    st = {"token": token, "requests": 0, "cost": 0, "records": 0, "status": None, "run_id": None}
    crashed = False
    with open(part, "w", encoding="utf-8") as out:
        try:
            status, reason = collect(st, keywords, out)
        except Exception as e:
            crashed = True
            reason = ("exception: %s: %s" % (type(e).__name__, e)).replace(token, "***") if token else \
                "exception: %s: %s" % (type(e).__name__, e)
            status = "partial" if st["records"] else "could_not_look"
    part.rename(d / (run_id + ".jsonl"))
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    result = {"source": "google_results", "brand": slug, "run_id": run_id, "started_at": started.strftime(fmt),
              "finished_at": ts().strftime(fmt), "status": status, "reason": reason, "records": st["records"],
              "records_by_kind": {"search_results_page": st["records"]} if st["records"] else {},
              "expected_total": None, "requests": st["requests"], "cost_usd": round(st["cost"], 6),
              "extra": {"apify_run_id": st["run_id"], "apify_status": st["status"], "ads": "could_not_look"}}
    (d / (run_id + ".run.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(slug, status, st["records"], result["cost_usd"], reason)
    return crashed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()
    slugs = [b["slug"] for b in json.loads((HERE.parent / "brands.json").read_text())]
    if args.brand and args.brand not in slugs:
        print("unknown brand: %s" % args.brand, file=sys.stderr)
        return 2
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    token = read_token()
    crashed = [run_brand(s, inputs[s]["keywords"], token) for s in (slugs if args.all else [args.brand])]
    return 1 if any(crashed) else 0


if __name__ == "__main__":
    sys.exit(main())
