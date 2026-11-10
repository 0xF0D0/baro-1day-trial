"""Raw collector: TikTok Creative Center Top Ads (US) via Apify. See spec.md."""
import argparse
import copy
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
API = "https://api.apify.com/v2"
START_URL = (API + "/acts/fetch_cat~tiktok-ads-library-scraper/runs"
             "?build=0.1.30&timeout=300&memory=512&maxTotalChargeUsd=0.25&waitForFinish=60")
TERMINAL = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
ITEM_LIMIT = 1000
RUN_WAIT_S = 360
API_TIMEOUT_S = 90
VIDEO_TIMEOUT_S, COVER_TIMEOUT_S = 60, 30
MEDIA_SPACING_S = 2
REQUIRED = ["adId", "detailUrl", "adText", "brandName", "advertiserName", "keyword", "videoUrl", "coverImageUrl"]


class ApiError(Exception):
    pass


def check_rows(rows):
    if not isinstance(rows, list):
        raise ValueError("dataset is not a list")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {i} is not an object")
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            raise ValueError(f"row {i} lacks {', '.join(missing)}")


def find_match_terms(row, match_terms):
    text = (row.get("adText") or "").lower()
    brand = (row.get("brandName") or "").lower()
    return [t for t in match_terms if t in text or t in brand]


def remove_personal_data(row, match_terms, kept_mentions):
    out = copy.deepcopy(row)
    for key in ("brandName", "advertiserName"):
        value = out.get(key)
        if value is not None and not any(t in value.lower() for t in match_terms):
            out[key] = None
    if out.get("adText"):
        out["adText"] = re.sub(
            r"@[^\s#@]+",
            lambda m: m.group(0) if m.group(0)[1:].lower() in kept_mentions else "@<removed>",
            out["adText"])
    return out


def cost_usd(run, rows):
    if not run:
        return 0
    events = (run.get("pricingInfo") or {}).get("pricingPerEvent", {}).get("actorChargeEvents")
    if not events:
        return run.get("usageTotalUsd") or 0
    return round(events["apify-actor-start"]["eventPriceUsd"]
                 + rows * events["apify-default-dataset-item"]["eventPriceUsd"], 8)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_token():
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\" ")
    except OSError:
        pass
    return ""


def fetch(st, url, token, body=None, timeout=API_TIMEOUT_S):
    """One request, sent once. Returns (status, body bytes, content type). Raises ApiError."""
    headers = {"Authorization": "Bearer " + token} if token else {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    st["requests"] += 1
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise ApiError(f"http_{e.code}")
    except Exception as e:
        raise ApiError(f"request_error: {e}")


def api_json(st, url, token, body=None, expect=(200,)):
    status, data, _ = fetch(st, url, token, body)
    if status not in expect:
        raise ApiError(f"http_{status}")
    try:
        return json.loads(data)
    except ValueError as e:
        raise ApiError(f"request_error: not JSON ({e})")


def get_media(st, url, timeout, want_type, path):
    """Download one file with no added headers. Returns the record entry."""
    if st["media_gets"]:
        time.sleep(MEDIA_SPACING_S)
    st["media_gets"] += 1
    st["requests"] += 1
    fail = {"file": None, "bytes": None, "sha256": None}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if r.status != 200:
                return {**fail, "error": f"http_{r.status}"}
            if ctype != want_type:
                return {**fail, "error": f"content_type: {ctype}"}
            body = r.read()
    except urllib.error.HTTPError as e:
        return {**fail, "error": f"http_{e.code}"}
    except Exception as e:
        return {**fail, "error": f"request_error: {e}"}
    full = HERE / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(body)
    return {"file": path, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "error": None}


def collect(st, slug, cfg, token, run_id, out):
    """Returns (status, reason). Fills st; writes records to out."""
    if not token:
        return "could_not_look", "missing_token"
    t0 = time.monotonic()
    body = {"keywords": cfg["keywords"], "regions": ["US"], "period": "180", "sortBy": "for_you", "maxItems": ITEM_LIMIT}
    try:
        st["run"] = api_json(st, START_URL, token, body, expect=(201,))["data"]
    except ApiError as e:
        return "could_not_look", f"apify_start: {e}"
    try:
        while st["run"].get("status") not in TERMINAL and time.monotonic() - t0 < RUN_WAIT_S:
            st["run"] = api_json(st, f"{API}/actor-runs/{st['run']['id']}?waitForFinish=60", token)["data"]
    except ApiError as e:
        return "could_not_look", f"apify_wait: {e}"
    run = st["run"]
    if run.get("status") not in TERMINAL:
        return "could_not_look", "apify_wait_timeout"
    try:
        rows = api_json(st, f"{API}/datasets/{run['defaultDatasetId']}/items?format=json&clean=false", token)
    except ApiError as e:
        return "could_not_look", f"apify_dataset: {e}"
    fetched_at = now()
    st["rows"] = len(rows) if isinstance(rows, list) else 0
    try:
        check_rows(rows)
    except ValueError as e:
        return "could_not_look", f"item_shape_changed: {e}"
    try:
        summary = api_json(st, f"{API}/key-value-stores/{run['defaultKeyValueStoreId']}/records/RUN_SUMMARY", token)
    except ApiError:
        summary = None
    st["summary"] = summary

    media_failed = 0
    for row in rows:
        terms = find_match_terms(row, cfg["match_terms"])
        if not terms:
            st["unmatched"].append(row["adId"])
            continue
        item = remove_personal_data(row, cfg["match_terms"], cfg["kept_mentions"])
        base = f"media/{slug}/{run_id}/{row['adId']}"
        video = get_media(st, row["videoUrl"], VIDEO_TIMEOUT_S, "video/mp4", base + ".mp4")
        cover = get_media(st, row["coverImageUrl"], COVER_TIMEOUT_S, "image/jpeg", base + ".jpg")
        media_failed += (video["error"] is not None) + (cover["error"] is not None)
        record = {"key": row["adId"], "kind": "ad", "url": row["detailUrl"], "fetched_at": fetched_at,
                  "raw": {"item": item, "matched_terms": terms, "video": video, "cover": cover}}
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        st["records"] += 1

    problems = []
    if run["status"] != "SUCCEEDED":
        problems.append(f"apify_run_{run['status']}")
    if summary is None:
        problems.append("run_summary_missing")
    elif (summary.get("status") != "SUCCEEDED" or summary.get("failed") != 0 or summary.get("errors")
          or summary.get("warnings") or summary.get("saved") != st["rows"]):
        problems.append("actor_summary_not_clean")
    if st["rows"] == ITEM_LIMIT:
        problems.append("item_limit_reached")
    if media_failed:
        problems.append(f"media_failed={media_failed}")
    if not problems:
        return "ok", ""
    return ("partial" if st["rows"] else "could_not_look"), "; ".join(problems)


def run_brand(slug, cfg):
    """Runs one brand. Returns True when it ended without an unexpected exception."""
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    raw_dir = HERE / "raw" / slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    part = raw_dir / f"{run_id}.jsonl.part"
    st = {"requests": 0, "media_gets": 0, "records": 0, "rows": 0, "run": None, "summary": None, "unmatched": []}
    ok = True
    with open(part, "w", encoding="utf-8") as out:
        try:
            status, reason = collect(st, slug, cfg, read_token(), run_id, out)
        except Exception as e:
            ok = False
            status = "partial" if st["records"] else "could_not_look"
            reason = f"exception: {type(e).__name__}: {e}"
    part.rename(raw_dir / f"{run_id}.jsonl")
    result = {
        "source": "tiktok_ads", "brand": slug, "run_id": run_id,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "finished_at": now(),
        "status": status, "reason": reason, "records": st["records"],
        "records_by_kind": {"ad": st["records"]}, "expected_total": None,
        "requests": st["requests"], "cost_usd": cost_usd(st["run"], st["rows"]),
        "extra": {"apify_run_id": (st["run"] or {}).get("id"), "rows": st["rows"],
                  "unmatched_ad_ids": st["unmatched"], "run_summary": st["summary"]},
    }
    (raw_dir / f"{run_id}.run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"{slug}: {status} {reason} records={st['records']}")
    return ok


def main():
    slugs = [b["slug"] for b in json.loads((HERE.parent / "brands.json").read_text())]
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brand", choices=slugs)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    all_ok = True
    for slug in (slugs if args.all else [args.brand]):
        all_ok &= run_brand(slug, inputs[slug])
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
