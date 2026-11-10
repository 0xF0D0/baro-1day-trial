from datetime import datetime, timezone

from model import MapError, MappedRun, Row, Scope

SOURCE = "google_ads_transparency"
ENDING = {("ads", "ad"): "source_date"}

FORMATS = {1: "text", 2: "image", 3: "video"}


def _utc(seconds) -> datetime:
    return datetime.fromtimestamp(int(seconds), timezone.utc)


def _map_record(rec: dict) -> Row:
    if rec["kind"] != "ad":
        raise ValueError(f"unknown record kind {rec['kind']!r}")
    raw = rec["raw"]
    item = raw["list_item"]
    columns = {
        "channel": "google", "advertiser_id": item["1"], "advertiser_name": item["12"],
        "format": FORMATS[item["4"]], "headline": None, "body": None, "cta": None, "landing_url": None,
        "landing_domain": item["14"], "started_at": _utc(item["6"]["1"]),
        "last_shown_at": _utc(item["7"]["1"]), "placements": None, "offer_code": None,
    }
    if raw["detail_state"] == "fetched":
        columns["variation_count"] = len(raw["detail"]["5"])
    return Row("ads", "ad", rec["key"], "all", rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows = []
    for rec in records:
        try:
            rows.append(_map_record(rec))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, OSError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, [Scope("all", run["status"], run["reason"])])
