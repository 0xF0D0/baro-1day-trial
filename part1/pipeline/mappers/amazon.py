from datetime import date
from decimal import Decimal

from model import MapError, MappedRun, Row, Scope

SOURCE = "amazon"
ENDING = {("products", "product"): "absent", ("reviews", "review"): "never"}

_CENT = Decimal("0.01")


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_CENT)


def _amount(value) -> Decimal | None:
    """A detail price: None, {"value": number, ...} or a plain number."""
    if value is None:
        return None
    if isinstance(value, dict):
        return _dec(value["value"])
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _dec(value)
    raise ValueError(f"unrecognised price: {value!r}")


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in ("True", "False"):
        return value == "True"
    raise ValueError(f"unrecognised boolean: {value!r}")


def _product(rec: dict) -> Row:
    raw = rec["raw"]
    columns = {"retailer": "amazon", "product_id": rec["key"], "price_max": None, "currency": "USD",
               "rank": raw["rank"], "sponsored": None, "sold_count": None}
    d = raw["detail"]
    if d is not None:  # these columns come only from the detail item
        columns.update(title=d.get("title"), price=_amount(d.get("price")), list_price=_amount(d.get("listPrice")),
                       rating=_dec(d.get("stars")), review_count=d.get("reviewsCount"),
                       availability=d.get("inStockText"), seller_name=(d.get("seller") or {}).get("name"))
    return Row("products", "product", rec["key"], "all", rec["url"], rec["fetched_at"], raw, columns)


def _review(rec: dict) -> Row:
    raw = rec["raw"]
    r = raw["item"]
    columns = {"product_key": raw["product_asin"], "rating": _dec(r["ReviewScore"]), "title": r["ReviewTitle"],
               "body": r["ReviewContent"], "review_date": date.fromisoformat(r["ReviewDate"]),
               "verified": _bool(r["Verified"]), "helpful_votes": r["HelpfulVotes"]}
    return Row("reviews", "review", rec["key"], "all", rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    rows = []
    for rec in records:
        try:
            if rec["kind"] == "product":
                rows.append(_product(rec))
            elif rec["kind"] == "review":
                rows.append(_review(rec))
            else:
                raise ValueError(f"unknown record kind {rec['kind']!r}")
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, [Scope("all", run["status"], run["reason"])])
