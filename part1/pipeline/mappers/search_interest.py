from datetime import datetime, timezone

from model import MapError, MappedRun, Row, Scope

SOURCE = "search_interest"
ENDING = {("search_interest", "interest_point"): "never", ("search_interest", "interest_point_compared"): "never"}
_SERIES = {"interest_point": "solo", "interest_point_compared": "compared"}


def _map_record(rec: dict) -> Row:
    kind, raw = rec["kind"], rec["raw"]
    if kind not in _SERIES:
        raise ValueError(f"unknown record kind {kind!r}")
    i, point = raw["series_index"], raw["point"]
    if not isinstance(i, int) or i < 0:
        raise ValueError(f"bad series_index {i!r}")
    item = raw["request"]["comparisonItem"][i]
    value = point["value"][i]
    has_data = point["hasData"][i]
    if isinstance(value, bool) or not isinstance(value, int) or not isinstance(has_data, bool):
        raise ValueError("value must be an integer and hasData a boolean")
    columns = {"keyword": item["complexKeywordsRestriction"]["keyword"][0]["value"], "series": _SERIES[kind],
               "week_start": datetime.fromtimestamp(int(point["time"]), timezone.utc).date(),
               "value": value, "has_data": has_data, "is_partial": bool(point.get("isPartial", False)),
               "geo": item["geo"]["country"]}
    return Row("search_interest", kind, rec["key"], "all", rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows = []
    for rec in records:
        try:
            rows.append(_map_record(rec))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, OSError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, [Scope("all", run["status"], run["reason"])])
