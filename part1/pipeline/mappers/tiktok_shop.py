"""Maps TikTok Shop runs to product rows.

Ending rule as implemented: a tracked product the source answers as `unavailable` gives no row and leaves
the tracked scope complete (`ok`), so its stored row is ended. A tracked product the actor returned no row
for (`missing`) or failed on makes the tracked scope `partial`, so nothing is ended.
"""
from decimal import Decimal

from model import MapError, MappedRun, Row, Scope

SOURCE = "tiktok_shop"
ENDING = {("products", "product"): "absent", ("products", "search_result"): "absent"}

PART_OF_KIND = {"product": "tracked", "search_result": "search"}
SEARCH_LIMIT = 20
_CENT = Decimal("0.01")


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_CENT)


def _problems(p: dict, part: str) -> list[str]:
    """The collector spec's part problems, in its order."""
    if p.get("error"):
        return [p["error"]]
    out = []
    if p.get("apify_status") and p["apify_status"] != "SUCCEEDED":
        out.append(f"apify_run_{p['apify_status']}: {p.get('apify_status_message') or ''}")
    for k in ("failed", "missing", "unavailable", "unexpected_rows", "duplicate_rows", "message_rows"):
        if p.get(k) and (k != "unavailable" or part == "search") and (k != "missing" or part == "tracked") \
                and (k != "unexpected_rows" or part == "tracked"):
            out.append(f"{k}={p[k]}")
    if part == "search":
        if p["fetched"] != SEARCH_LIMIT:
            out.append(f"fetched={p['fetched']}/{SEARCH_LIMIT}")
        elif not p["ranks_complete"]:
            out.append("ranks_incomplete")
    return out


def _scope(name: str, p: dict) -> Scope:
    problems = _problems(p, name)
    if p.get("error"):
        return Scope(name, "could_not_look", p["error"])
    return Scope(name, "partial", ", ".join(problems)) if problems else Scope(name, "ok", "")


def _int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)) or value != int(value):
        raise ValueError(f"not an integer: {value!r}")
    return int(value)


def _map_record(rec: dict) -> Row | None:
    kind, raw = rec["kind"], rec["raw"]
    if kind not in PART_OF_KIND:
        raise ValueError(f"unknown record kind {kind!r}")
    if raw["item_state"] != "fetched":
        if raw["item_state"] not in ("unavailable", "failed", "missing"):
            raise ValueError(f"unknown item_state {raw['item_state']!r}")
        return None
    item = raw["item"]
    columns = {"retailer": "tiktok_shop", "product_id": item["productId"], "title": item["title"],
               "price": _dec(item["currentPrice"]), "price_max": None, "list_price": _dec(item.get("originalPrice")),
               "currency": item["currency"], "rating": _dec(item.get("rating")), "review_count": _int(item.get("reviewCount")),
               "rank": _int(item["rank"]) if kind == "search_result" else None, "sponsored": None,
               "availability": None, "seller_name": item.get("sellerName"), "sold_count": _int(item.get("soldCount"))}
    return Row("products", kind, rec["key"], PART_OF_KIND[kind], rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    extra = run.get("extra") or {}
    scopes = [_scope(n, extra[n]) for n in ("tracked", "search") if isinstance(extra.get(n), dict)]
    if not scopes:
        scopes = [Scope("all", run["status"], run["reason"])]
    else:
        scopes += [Scope(n, "could_not_look", run["reason"])
                   for n in ("tracked", "search") if all(s.name != n for s in scopes)]
    rows, not_fetched = [], 0
    for rec in records:
        try:
            row = _map_record(rec)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
        if row is None:
            not_fetched += 1
        else:
            rows.append(row)
    return MappedRun(rows, scopes, not_fetched)
