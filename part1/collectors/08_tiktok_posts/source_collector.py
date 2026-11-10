"""Source 8: TikTok posts via the Apify Actor clockworks/tiktok-scraper. Raw collector; see spec.md."""
import argparse, copy, json, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
START_URL = "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/runs?timeout=300&maxTotalChargeUsd=0.5&waitForFinish=60"
RUN_URL = "https://api.apify.com/v2/actor-runs/{}?waitForFinish=60"
ITEMS_URL = "https://api.apify.com/v2/datasets/{}/items?format=json"
MAX_WAIT_S, HTTP_TIMEOUT_S = 420, 90
FINISHED = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
PATHS = ("profile_popular", "hashtag")
OFF = {"shouldDownloadVideos": False, "shouldDownloadCovers": False, "shouldDownloadSlideshowImages": False,
       "shouldDownloadAvatars": False, "shouldDownloadMusicCovers": False,
       "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES", "commentsPerPost": 0, "scrapeRelatedVideos": False,
       "scrapeAdditionalAuthorMeta": False, "proxyCountryCode": "None"}


def now_z(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_input(path, query):
    if path == "profile_popular":
        return {"profiles": [query], "profileScrapeSections": ["videos"], "profileSorting": "popular",
                "excludePinnedPosts": False, "resultsPerPage": 10, "maxFollowersPerProfile": 0,
                "maxFollowingPerProfile": 0, **OFF}
    return {"hashtags": [query], "resultsPerPage": 30, **OFF}


def remove_personal(item):
    item = copy.deepcopy(item)
    for parent, keys in (("authorMeta", ("nickName", "signature", "bioLink", "avatar", "originalAvatarUrl", "profileUrl")),
                         ("musicMeta", ("musicAuthor", "coverMediumUrl", "originalCoverMediumUrl"))):
        if isinstance(item.get(parent), dict):
            for k in keys:
                if k in item[parent]: item[parent][k] = None
    for k in ("mentions", "locationMeta"):
        if k in item: item[k] = None
    if isinstance(item.get("detailedMentions"), list):
        for m in item["detailedMentions"]:
            if isinstance(m, dict):
                for k in ("nickName", "profileUrl"):
                    if k in m: m[k] = None
    return item


def path_records(dataset, path, query):
    if not isinstance(dataset, list): raise ValueError("dataset is not a list")
    out, bad, seen = [], 0, set()
    for pos, item in enumerate(dataset, 1):
        if not (isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].isdigit()
                and item["id"].isascii() and isinstance(item.get("webVideoUrl"), str)):
            bad += 1
            continue
        if item["id"] in seen: continue
        seen.add(item["id"])
        out.append({"path": path, "query": query, "position": pos, "item": remove_personal(item)})
    return out, bad


def decide_status(paths):
    if all(p["state"] == "failed" for p in paths.values()):
        return "could_not_look", "; ".join(f"{n}: {p['error']}" for n, p in paths.items())
    if all(p["state"] == "complete" for p in paths.values()): return "ok", ""
    return "partial", "; ".join(f"{n}: {p['error']}" for n, p in paths.items() if p["state"] != "complete")


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
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method),
                                    timeout=HTTP_TIMEOUT_S) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def fetch_path(state, token, path, query, out):
    """Returns the path summary; writes records to `out`."""
    info = {"query": query, "state": "failed", "error": None, "apify_run_id": None, "records": 0, "bad_items": 0, "cost_usd": 0}
    want = run_input(path, query)["resultsPerPage"]
    t0 = time.monotonic()
    try:
        status, body = call(state, token, "POST", START_URL, run_input(path, query))
    except Exception:
        info["error"] = "start_error"; return info
    if status != 201 or not isinstance(body, dict): info["error"] = f"start_http_{status}"; return info
    data = body["data"]
    info["apify_run_id"] = data.get("id")
    while data.get("status") not in FINISHED:
        if time.monotonic() - t0 > MAX_WAIT_S: info["error"] = "wait_exceeded"; break
        try:
            status, body = call(state, token, "GET", RUN_URL.format(data["id"]))
            if status != 200: raise RuntimeError(status)
            data = body["data"]
        except Exception:
            info["error"] = "poll_error"; break
    info["cost_usd"] = round(data.get("usageTotalUsd") or 0, 6)
    if info["error"]: return info
    if data["status"] != "SUCCEEDED": info["error"] = f"run_{data['status']}"; return info
    try:
        status, items = call(state, token, "GET", ITEMS_URL.format(data["defaultDatasetId"]))
        if status != 200 or not isinstance(items, list): raise ValueError(status)
    except Exception:
        info["error"] = "dataset_error"; return info
    fetched_at = now_z()
    raws, info["bad_items"] = path_records(items, path, query)
    for raw in raws:
        out.write(json.dumps({"key": f"{path}/{raw['item']['id']}", "kind": "post", "url": raw["item"]["webVideoUrl"],
                              "fetched_at": fetched_at, "raw": raw}, ensure_ascii=False) + "\n")
        out.flush(); info["records"] += 1; state["records"] += 1
    problems = []
    if info["records"] == 0: info["error"] = "no_items"
    else:
        if info["records"] < want: problems.append(f"short({info['records']}/{want})")
        if info["bad_items"]: problems.append(f"bad_items={info['bad_items']}")
        info["error"] = ", ".join(problems) or None
        info["state"] = "incomplete" if problems else "complete"
    return info


def run_brand(slug):
    started = datetime.now(timezone.utc)
    run_id, started_at = started.strftime("%Y%m%dT%H%M%SZ"), started.strftime("%Y-%m-%dT%H:%M:%SZ")
    out_dir = HERE / "raw" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    part, final = out_dir / f"{run_id}.jsonl.part", out_dir / f"{run_id}.jsonl"
    state, extra, failed = {"requests": 0, "records": 0}, {}, False
    status, reason, token = None, "", read_token()
    queries = json.loads((HERE / "brand_inputs.json").read_text())[slug]
    out = part.open("w", encoding="utf-8")
    try:
        if not token:
            status, reason = "could_not_look", "missing_token"
        else:
            for path, key in zip(PATHS, ("profile", "hashtag")):
                extra[path] = fetch_path(state, token, path, queries[key], out)
            status, reason = decide_status(extra)
    except Exception as e:
        failed = True
        status = "partial" if state["records"] else "could_not_look"
        reason = f"exception: {type(e).__name__}: {e}"
    finally:
        out.close()
    n = state["records"]
    part.rename(final)
    result = {"source": "tiktok_posts", "brand": slug, "run_id": run_id, "started_at": started_at, "finished_at": now_z(),
              "status": status, "reason": reason, "records": n, "records_by_kind": {"post": n}, "expected_total": None,
              "requests": state["requests"], "cost_usd": round(sum(p["cost_usd"] for p in extra.values()), 6),
              "extra": extra}
    (out_dir / f"{run_id}.run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"{slug}: {status} {reason} records={n} cost_usd={result['cost_usd']}")
    return not failed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand"); g.add_argument("--all", action="store_true")
    args = ap.parse_args()  # argparse exits with 2 on invalid arguments
    slugs = list(json.loads((HERE / "brand_inputs.json").read_text()))
    if args.brand and args.brand not in slugs:
        print(f"unknown brand: {args.brand}", file=sys.stderr); return 2
    ok = [run_brand(s) for s in (slugs if args.all else [args.brand])]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
