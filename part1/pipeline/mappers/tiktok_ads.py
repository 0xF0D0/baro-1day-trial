from model import MapError, MappedRun, Row, Scope

SOURCE = "tiktok_ads"
ENDING = {("ads", "ad"): "absent"}


def _text(value):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"expected text, got {type(value).__name__}")
    return value


def _map_record(rec: dict) -> Row:
    if rec["kind"] != "ad":
        raise ValueError(f"unknown record kind {rec['kind']!r}")
    raw = rec["raw"]
    item = raw["item"]
    columns = {"channel": "tiktok", "advertiser_id": None, "advertiser_name": _text(item["brandName"]),
               "format": "video", "headline": None, "body": _text(item["adText"]), "cta": None,
               "landing_url": None, "landing_domain": None, "started_at": None, "last_shown_at": None,
               "variation_count": None, "placements": None, "offer_code": None}
    return Row("ads", "ad", rec["key"], "all", rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows = []
    for rec in records:
        try:
            rows.append(_map_record(rec))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, [Scope("all", run["status"], run["reason"])])
