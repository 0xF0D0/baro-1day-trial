import json
import re
from datetime import datetime, timezone
from pathlib import Path

from model import MapError, MappedRun, Row, Scope

SOURCE = "tiktok_posts"
ENDING = {("posts", "post"): "never"}

PATHS = ("profile_popular", "hashtag")
_STATUS = {"complete": "ok", "incomplete": "partial", "failed": "could_not_look"}
_BRANDS = json.loads((Path(__file__).resolve().parents[2] / "collectors" / "08_tiktok_posts" / "brand_inputs.json").read_text())


def _count(value) -> int | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"not a count: {value!r}")
    return value


def _hashtags(item: dict) -> list[str]:
    names = [h["name"] for h in item.get("hashtags") or []] + re.findall(r"#(\w+)", item["text"])
    seen, out = set(), []
    for name in names:
        name = name.lower()
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _columns(item: dict, profile: str, paths: list[str]) -> dict:
    author = item["authorMeta"]
    return {"post_id": item["id"],
            "posted_at": datetime.fromtimestamp(item["createTime"], timezone.utc),
            "creator_handle": author["name"], "creator_is_brand": author["name"] == profile,
            "creator_followers": _count(author.get("fans")),
            "views": _count(item.get("playCount")), "likes": _count(item.get("diggCount")),
            "comments": _count(item.get("commentCount")), "shares": _count(item.get("shareCount")),
            "saves": _count(item.get("collectCount")),
            "caption": item["text"], "hashtags": _hashtags(item), "surfaced_by": paths}


def map_run(run: dict, records: list[dict]) -> MappedRun:
    parts = {p: v for p, v in (run.get("extra") or {}).items() if p in PATHS and isinstance(v, dict)}
    scopes = []
    for p, v in parts.items():
        if v.get("state") not in _STATUS:
            raise MapError(f"{p}: unknown state {v.get('state')!r}")
        scopes.append(Scope(p, _STATUS[v["state"]], v.get("error") or ""))
    for rec in records:
        path = (rec.get("raw") or {}).get("path")
        if path in PATHS and all(s.name != path for s in scopes):
            scopes.append(Scope(path, "partial", run["reason"]))
    if not scopes:
        scopes = [Scope("all", run["status"], run["reason"])]
    found: dict[str, dict[str, dict]] = {}
    for rec in records:
        try:
            path = rec["raw"]["path"]
            if rec["kind"] != "post":
                raise ValueError(f"unknown record kind {rec['kind']!r}")
            if path not in PATHS:
                raise ValueError(f"unknown path {path!r}")
            post_id = rec["key"].split("/", 1)[1]
            if rec["key"] != f"{path}/{rec['raw']['item']['id']}":
                raise ValueError("key does not match path and item id")
            found.setdefault(post_id, {})[path] = rec
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    rows = []
    for post_id, by_path in found.items():
        paths = [p for p in PATHS if p in by_path]
        rec = by_path[paths[0]]
        try:
            if run["brand"] not in _BRANDS:
                raise ValueError(f"unknown brand {run['brand']!r}")
            columns = _columns(rec["raw"]["item"], _BRANDS[run["brand"]]["profile"], paths)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError, OSError) as e:
            key = rec["key"] if run["brand"] in _BRANDS else run["brand"]
            raise MapError(f"{key}: {type(e).__name__}: {e}") from e
        rows.append(Row("posts", "post", post_id, paths[0], rec["url"], rec["fetched_at"], rec["raw"], columns))
    return MappedRun(rows, scopes)
