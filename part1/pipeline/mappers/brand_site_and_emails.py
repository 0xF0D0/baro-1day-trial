import email
import email.policy
import email.utils
import json
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from model import MapError, MappedRun, Row, Scope

SOURCE = "brand_site_and_emails"
ENDING = {("products", "product"): "absent", ("products", "retailer_availability"): "absent",
          ("ads", "offer_slot"): "absent", ("ads", "klaviyo_form"): "absent", ("ads", "email"): "never"}

_BRANDS = json.loads((Path(__file__).resolve().parents[2] / "collectors" / "10_brand_site_and_emails" / "brand_inputs.json").read_text())
_CENT = Decimal("0.01")
_ADS = ("channel", "advertiser_id", "advertiser_name", "format", "headline", "body", "cta", "landing_url",
        "landing_domain", "started_at", "last_shown_at", "variation_count", "placements", "offer_code")
_PRODUCTS = ("retailer", "product_id", "title", "price", "price_max", "list_price", "currency", "rating",
             "review_count", "rank", "sponsored", "availability", "seller_name", "sold_count")


def _page_key(url: str, base: str) -> str:
    """A URL resolved against base, without query, fragment or trailing slash, for comparing two pages."""
    parts = urlsplit(urljoin(base, url))
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}".lower()


def _unread_pages(pages: list, listing_url) -> int:
    """Product pages not read cleanly: failed, widget missing, or redirected anywhere but the brand's listing page."""
    n = 0
    for p in pages:
        if not isinstance(p, dict):
            continue
        state = p.get("state")
        if state in ("failed", "widget_missing"):
            n += 1
        elif state == "redirected":
            loc = p.get("location")
            if not (listing_url and isinstance(loc, str) and _page_key(loc, listing_url) == _page_key(listing_url, listing_url)):
                n += 1
    return n


def _dec(value) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(_CENT)


def _stock(available) -> str | None:
    return None if available is None else ("IN_STOCK" if available else "OUT_OF_STOCK")


def _list_price(variant: dict) -> Decimal | None:
    """The compare-at price, only when it is above the price ("0.00" and null mean none)."""
    price, compare = _dec(variant.get("price")), _dec(variant.get("compare_at_price"))
    return compare if price is not None and compare is not None and compare > price else None


def _product_columns(**values) -> dict:
    return {name: values.get(name) for name in _PRODUCTS}


def _ad_columns(**values) -> dict:
    return {name: values.get(name) for name in _ADS}


def _product_rows(rec: dict) -> list[Row]:
    raw = rec["raw"]
    if raw["route"] == "shopify_products_json":
        p = raw["product"]
        variants = p["variants"]
        v = variants[0] if variants else {}
        cols = _product_columns(retailer="own_site", product_id=str(p["id"]), title=p["title"], price=_dec(v.get("price")),
                                list_price=_list_price(v), currency="USD",
                                availability=_stock(any(x.get("available") for x in variants)) if variants else None)
    elif raw["route"] == "apify_ecommerce":
        item = raw["item"]
        offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        cols = _product_columns(retailer="own_site", title=item.get("name"), price=_dec(offers.get("price")),
                                currency=offers.get("priceCurrency") or "USD")
    else:
        raise ValueError(f"unknown product route {raw['route']!r}")
    return [Row("products", "product", rec["key"], "prices", rec["url"], rec["fetched_at"], raw, cols)]


def _availability_rows(rec: dict) -> list[Row]:
    raw = rec["raw"]
    response = raw["response"]
    title = response["prd"]["pname"]
    first = {}
    for entry in response["d"]:     # the online entry of a retailer (sid ends with _WEB), else its first entry
        if entry["rid"] not in first or (entry["sid"].endswith("_WEB") and not first[entry["rid"]]["sid"].endswith("_WEB")):
            first[entry["rid"]] = entry
    return [Row("products", "retailer_availability", f"{rec['key']}/{rid}", rec["key"], rec["url"], rec["fetched_at"],
                raw, _product_columns(retailer=e["rname"].strip().lower(), product_id=raw["ean"], title=title, price=_dec(e["pr"]),
                                      currency=e["currency"], availability=_stock(e["av"])))
            for rid, e in first.items()]


def _ads_row(rec: dict, scope: str, **values) -> Row:
    return Row("ads", rec["kind"], rec["key"], scope, rec["url"], rec["fetched_at"], rec["raw"], _ad_columns(**values))


def _email_row(rec: dict) -> Row:
    msg = email.message_from_string(rec["raw"]["eml"], policy=email.policy.default)
    sent = email.utils.parsedate_to_datetime(str(msg["Date"]))
    if sent.tzinfo is None:
        raise ValueError(f"Date without a time zone: {msg['Date']!r}")
    name = email.utils.parseaddr(str(msg["From"]))[0]
    return _ads_row(rec, "emails", channel="email", headline=str(msg["Subject"]), advertiser_name=name or None,
                    started_at=sent.astimezone(timezone.utc),
                    body=plain.get_content() if (plain := msg.get_body(preferencelist=("plain",))) else None)


def _map_record(rec: dict, offer_scopes: tuple[str, str]) -> tuple[list[Row], bool]:
    """Return the rows and whether the record said its item was not fetched."""
    kind, raw = rec["kind"], rec["raw"]
    if kind == "product":
        return _product_rows(rec), False
    if kind == "retailer_availability":
        return (_availability_rows(rec), False) if raw["state"] == "fetched" else ([], True)
    if kind == "offer_slot":
        if raw["state"] != "found":
            return [], True
        return [_ads_row(rec, offer_scopes[0], channel="site", body="\n".join(e["text"] for e in raw["elements"]))], False
    if kind == "klaviyo_form":
        return [_ads_row(rec, offer_scopes[1], channel="signup_form", headline=raw["form"]["name"])], False
    if kind == "email":
        return [_email_row(rec)], False
    raise ValueError(f"unknown record kind {kind!r}")


def map_run(run: dict, records: list[dict]) -> MappedRun:
    parts = (run.get("extra") or {}).get("parts")   # a run that stopped on an exception may hold few or none
    if not isinstance(parts, dict):
        parts = {}
    offers = parts.get("offers") or {}
    split = isinstance(offers.get("home"), dict) or "offers" not in parts
    offer_scopes = ("offers_home", "offers_klaviyo") if split else ("offers", "offers")
    rows, barcodes, not_fetched = [], [], 0
    for rec in records:
        try:
            got, missing = _map_record(rec, offer_scopes)
            if rec["kind"] == "retailer_availability":
                raw = rec["raw"]
                barcodes.append(Scope(rec["key"], "ok", "") if raw["state"] == "fetched"
                                else Scope(rec["key"], "could_not_look", raw["error"] or raw["state"]))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError, OverflowError) as e:
            raise MapError(f"{rec.get('key')}: {type(e).__name__}: {e}") from e
        rows.extend(got)
        not_fetched += missing
    scopes = []
    for name, part in parts.items():
        if name == "prices" and barcodes and part.get("route") == "batiste_wtb":
            scopes.extend(barcodes)
        elif name == "offers" and split:
            scopes.append(Scope("offers_home", offers["home"]["state"], offers["home"]["reason"]))
            if isinstance(offers.get("klaviyo"), dict):
                scopes.append(Scope("offers_klaviyo", offers["klaviyo"]["state"], offers["klaviyo"]["reason"]))
        else:
            scopes.append(Scope(name, part["state"], part["reason"]))
        if name == "prices" and part.get("route") == "batiste_wtb":   # the product-page list the barcodes come from
            pages = part.get("product_pages")
            found = isinstance(pages, list) and any(isinstance(p, dict) and p.get("eans") for p in pages)
            if not found:     # no list, or not one barcode in it: the rows of the brand cannot be judged
                scopes.append(Scope("wtb_listing", "could_not_look", part["reason"], covers="wtb/"))
            else:
                listing = ((_BRANDS.get(run.get("brand")) or {}).get("prices") or {}).get("listing_url")
                bad = _unread_pages(pages, listing)
                scopes.append(Scope("wtb_listing", "partial" if bad else "ok",
                                    f"product_pages_failed={bad}" if bad else "", covers="wtb/"))
    names = {s.name for s in scopes}
    needed = {"product": lambda r: "prices", "retailer_availability": lambda r: r["key"],
              "offer_slot": lambda r: offer_scopes[0], "klaviyo_form": lambda r: offer_scopes[1], "email": lambda r: "emails"}
    for rec in records:     # a scope the run never reported is a gap of this run, not a reason to reject it
        name = needed[rec["kind"]](rec)
        if name not in names:
            scopes.append(Scope(name, "partial", run["reason"]))
            names.add(name)
    if not scopes:
        scopes.append(Scope("all", run["status"], run["reason"]))
    for row in rows:
        if row.scope not in names:
            raise MapError(f"{row.key}: scope {row.scope!r} is not in the scopes of the run")
    return MappedRun(rows, scopes, not_fetched)
