from datetime import datetime, timezone
from urllib.parse import urlsplit

from model import MapError, MappedRun, Row, Scope

SOURCE = "meta_ad_library"
ENDING = {("ads", "ad"): "absent"}


def _text(value):
    return value["text"] if isinstance(value, dict) else value


def _pick(snap, field, card_field):
    """The snapshot's own value; when null or empty, the first card (in order) with a non-empty value."""
    cards = snap.get("cards")
    nodes = [(snap, field)] + [(c, card_field) for c in cards] if isinstance(cards, list) else [(snap, field)]
    for node, name in nodes:
        value = _text(node.get(name))
        if value not in (None, ""):
            return value
    return None


def _host(url):
    host = None if url is None else urlsplit(url).hostname
    return host.removeprefix("www.") if host else None


def _map_record(rec: dict) -> Row:
    if rec["kind"] != "ad":
        raise ValueError(f"unknown record kind {rec['kind']!r}")
    item = rec["raw"]["item"]
    snap = item["snapshot"]
    if not isinstance(snap, dict):
        raise TypeError("snapshot is not an object")
    platforms = item["publisherPlatform"]
    if not isinstance(platforms, list):
        raise TypeError("publisherPlatform is not a list")
    start = item["startDate"]
    if isinstance(start, bool) or not isinstance(start, int):
        raise TypeError(f"startDate is not UTC seconds: {start!r}")
    count = item.get("collationCount")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
        raise TypeError(f"collationCount is not an integer: {count!r}")
    link = _pick(snap, "linkUrl", "linkUrl")
    columns = {
        "channel": "meta", "advertiser_id": item["pageId"], "advertiser_name": item["pageName"],
        "format": snap["displayFormat"].lower(), "headline": _pick(snap, "title", "title"),
        "body": _pick(snap, "body", "body"), "cta": _pick(snap, "ctaText", "ctaText"), "landing_url": link,
        "landing_domain": _host(link), "started_at": datetime.fromtimestamp(start, timezone.utc),
        "last_shown_at": None, "variation_count": count,
        "placements": list(platforms), "offer_code": None,
    }
    return Row("ads", "ad", rec["key"], "all", rec["url"], rec["fetched_at"], rec["raw"], columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows = []
    for rec in records:
        try:
            rows.append(_map_record(rec))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, OSError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, [Scope("all", run["status"], run["reason"])])
