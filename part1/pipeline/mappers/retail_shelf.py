import re
from datetime import date, datetime, timezone
from decimal import Decimal

from model import MapError, MappedRun, Row, Scope

SOURCE = "retail_shelf"
ENDING = {("products", "product"): "absent", ("reviews", "review"): "never"}

RETAILERS = ("ulta", "target", "sephora", "chewy")
_CENT = Decimal("0.01")


_AMOUNT = r"\$(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"


def _money(text: str) -> Decimal:
    return Decimal(text.replace("$", "").replace(",", ""))


def parse_price(text: str) -> tuple[Decimal, Decimal | None]:
    if re.fullmatch(_AMOUNT, text):
        return _money(text), None
    if re.fullmatch(_AMOUNT + " - " + _AMOUNT, text):
        low, high = text.split(" - ")
        return _money(low), _money(high)
    raise ValueError(f"unrecognised price: {text!r}")


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_CENT)


def _parsed(text) -> tuple[Decimal | None, Decimal | None]:
    return (None, None) if text is None else parse_price(text)


def _low(text) -> Decimal | None:
    return None if text is None else parse_price(text)[0]


def _product_values(retailer: str, li: dict) -> dict:
    """Return title, price, price_max, list_price, rating, review_count, sponsored, availability."""
    if retailer == "ulta":
        price, price_max = _parsed(li.get("salePrice") or li.get("listPrice"))
        return dict(title=li.get("productName"), price=price, price_max=price_max,
                    list_price=_low(li.get("listPrice")) if li.get("salePrice") is not None else None,
                    rating=li.get("rating"), review_count=li.get("reviewCount"),
                    sponsored=li.get("sponsored"), availability=None)
    if retailer == "target":
        price, regular = _dec(li.get("price")), _dec(li.get("regularPrice"))
        return dict(title=li.get("title"), price=price, price_max=None,
                    list_price=regular if regular != price else None,
                    rating=li.get("rating"), review_count=li.get("reviewCount"),
                    sponsored=li.get("isSponsored"), availability=li.get("availability"))
    if retailer == "sephora":
        price, price_max = _parsed(li.get("listPrice"))
        return dict(title=li.get("displayName"), price=price, price_max=price_max, list_price=None,
                    rating=li.get("rating"), review_count=li.get("reviews"),
                    sponsored=li.get("sponsored"), availability=None)
    price, price_max = _parsed(li.get("displayPrice"))
    in_stock = li.get("inStock")
    return dict(title=li.get("name"), price=price, price_max=price_max, list_price=_low(li.get("strikePrice")),
                rating=li.get("rating"), review_count=li.get("ratingCount"), sponsored=None,
                availability=None if in_stock is None else ("IN_STOCK" if in_stock else "OUT_OF_STOCK"))


def _date_part(text) -> date | None:
    return None if text is None else date.fromisoformat(text[:10])


def _review_values(retailer: str, r: dict) -> dict:
    """Return rating, title, body, review_date, verified, helpful_votes."""
    if retailer == "ulta":
        d, ms = r.get("details") or {}, (r.get("details") or {}).get("created_date")
        return dict(rating=(r.get("metrics") or {}).get("rating"), title=d.get("headline"), body=d.get("comments"),
                    review_date=None if ms is None else datetime.fromtimestamp(ms / 1000, timezone.utc).date(),
                    verified=(r.get("badges") or {}).get("is_verified_buyer"),
                    helpful_votes=(r.get("metrics") or {}).get("helpful_votes"))
    if retailer in ("target", "sephora"):
        return dict(rating=(r.get("reviewRating") or {}).get("ratingValue"), title=r.get("name"),
                    body=r.get("reviewBody"), review_date=_date_part(r.get("datePublished")),
                    verified=None, helpful_votes=None)
    return dict(rating=r.get("rating"), title=r.get("title"), body=r.get("reviewText"),
                review_date=_date_part(r.get("reviewDate")), verified=None, helpful_votes=r.get("helpfulVotes"))


def _map_record(rec: dict) -> Row:
    raw, kind = rec["raw"], rec["kind"]
    retailer = raw["retailer"]
    if retailer not in RETAILERS:
        raise ValueError(f"unknown retailer {retailer!r}")
    if kind == "product":
        v = _product_values(retailer, raw["listing_item"])
        columns = {"retailer": retailer, "product_id": rec["key"].split(":", 1)[1], "title": v["title"],
                   "price": v["price"], "price_max": v["price_max"], "list_price": v["list_price"],
                   "currency": "USD", "rating": _dec(v["rating"]), "review_count": v["review_count"],
                   "rank": raw["rank"], "sponsored": v["sponsored"], "availability": v["availability"],
                   "seller_name": None, "sold_count": None}
        table = "products"
    elif kind == "review":
        columns = {"product_key": raw["product_key"], **_review_values(retailer, raw["review"])}
        table = "reviews"
    else:
        raise ValueError(f"unknown record kind {kind!r}")
    return Row(table, kind, rec["key"], retailer, rec["url"], rec["fetched_at"], raw, columns)


def map_run(run: dict, records: list[dict]) -> MappedRun:
    cells = (run.get("extra") or {}).get("cells")
    if not isinstance(cells, list):
        raise MapError("run.extra has no cells list")
    scopes = [Scope(c["retailer"], c["status"], c["reason"]) for c in cells]
    rows = []
    for rec in records:
        try:
            rows.append(_map_record(rec))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
    return MappedRun(rows, scopes)
