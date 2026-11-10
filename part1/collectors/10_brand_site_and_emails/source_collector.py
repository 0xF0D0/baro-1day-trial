"""Raw collector for source 10: brand site and emails. See spec.md.

    python source_collector.py --brand living-proof
    python source_collector.py --all
"""
import argparse
import copy
import email.parser
import email.policy
import email.utils
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
BRANDS_JSON = ROOT / "part1/collectors/brands.json"
SIGNUPS_JSON = ROOT / "part1/data/email_signups.json"
EXPORT_DIR = HERE / "inbox_export"
RAW_DIR = HERE / "raw"

NAV_TIMEOUT_S = 45
HOME_SETTLE_S = 8
HTTP_TIMEOUT_S = 30
SPACING_S = 4
PRODUCTS_PAGE_SIZE = 250
MAX_PRODUCT_PAGES = 10
APIFY_MAX_PRODUCTS = 80
APIFY_MAX_CHARGE_USD = 1
APIFY_RUN_TIMEOUT_S = 3600
APIFY_POLL_WAIT_S = 60
APIFY_POLL_HTTP_TIMEOUT_S = 90
APIFY_POLL_ERRORS_MAX = 3
APIFY_POLL_ERROR_WAIT_S = 15
APIFY_MAX_TOTAL_WAIT_S = 4200
FIRST_DAY_S = 86400
SIGNUP_TOLERANCE_S = 300

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
APIFY_ACTOR = "apify~e-commerce-scraping-tool"
APIFY_BR_RE = re.compile(r"^https://www\.blackriflecoffee\.com/products/([^/?#]+)(?:\?variant=\d+)?$")
WTB_URL = ("https://wtb-api-hub.swaven.com/wtb/v2/api/search/availabilities/{ean}"
           "?wtbid={wtbid}&lang=en&country=US&nextEndpointV2=true&applyTiedHouseLaw=true")
TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class ShapeError(Exception):
    pass


# ---------------------------------------------------------------- pure parsers
def product_key(host, handle):
    return f"product/{host}/{handle}"


def market_ok(country, currency):
    return country == "US" and currency == "USD"


def parse_products_page(resp):
    if not isinstance(resp, dict) or not isinstance(resp.get("products"), list):
        raise ShapeError("products is not a list")
    for p in resp["products"]:
        if not isinstance(p, dict):
            raise ShapeError("product is not an object")
        if not isinstance(p.get("id"), int) or isinstance(p.get("id"), bool):
            raise ShapeError("product without integer id")
        if not isinstance(p.get("handle"), str) or not p["handle"]:
            raise ShapeError("product without handle")
        if not isinstance(p.get("variants"), list):
            raise ShapeError("product without variants")
        for v in p["variants"]:
            if not isinstance(v, dict) or "id" not in v or "price" not in v:
                raise ShapeError("variant without id or price")
    return resp["products"]


def _title(html):
    m = re.search(r"<title>\s*([^<]*?)\s*</title>", html, re.I)
    return m.group(1) if m else ""


def parse_batiste_listing(html):
    if _title(html).startswith("404 |"):
        raise ShapeError("listing_not_found")
    paths = list(dict.fromkeys(re.findall(r'href="(/products/[^"#?]+)"', html)))
    if not paths:
        raise ShapeError("listing_no_products")
    return paths


def classify_batiste_page(status, location, html, wtbid):
    if 300 <= status < 400:
        return "redirected", []
    if status != 200:
        return "failed", []
    if _title(html).startswith("404 |"):
        return "not_found_page", []
    tags = re.findall(r'<a\b[^>]*\bdata-mm-ids="[^"]*"[^>]*>', html)
    if len(tags) == 1:
        m = re.search(r'data-mm-wtbid="([^"]*)"', tags[0])
        if m and m.group(1) == wtbid:
            ids = re.search(r'data-mm-ids="([^"]*)"', tags[0]).group(1)
            return "widget", [e for e in ids.split(",") if e]
    return "widget_missing", []


def validate_wtb(resp, ean):
    if not (isinstance(resp, dict) and isinstance(resp.get("d"), list)
            and isinstance(resp.get("prd"), dict) and resp["prd"].get("ean") == ean
            and isinstance(resp.get("loc"), dict)):
        raise ShapeError("wtb shape changed")
    return resp["loc"].get("Country"), resp["loc"].get("ISOCurrencySymbol")


def parse_klaviyo(resp):
    forms = resp.get("full_forms") if isinstance(resp, dict) else None
    if not isinstance(forms, list) or not all(
            isinstance(f, dict) and isinstance(f.get("form_id"), str) for f in forms):
        raise ShapeError("full_forms shape changed")
    return forms


def apify_item_key(item):
    url = item.get("url") if isinstance(item, dict) else None
    m = APIFY_BR_RE.match(url) if isinstance(url, str) else None
    return product_key("www.blackriflecoffee.com", m.group(1)) if m else None


def apify_listed(log, listing_url):
    pairs = {}
    for n, url, page in re.findall(r"Found (\d+) products in the listing page: (\S+)\. Page: (\d+)", log):
        if url == listing_url:
            pairs[(url, page)] = int(n)
    return sum(pairs.values()) if pairs else None


def apify_prices_state(run_status, records, listed, max_hit, errors, log_read, counts):
    if run_status != "SUCCEEDED" and records == 0:
        return "could_not_look", f"apify_run_{run_status}"
    if (run_status == "SUCCEEDED" and not max_hit and log_read and listed == records
            and errors == 0 and not any(counts.values())):
        return "ok", ""
    r = []
    if run_status != "SUCCEEDED":
        r.append(f"apify_run_{run_status}")
    if max_hit:
        r.append("apify_max_results_reached")
    if log_read and listed is None:
        r.append("apify_listing_count_missing")
    if listed is not None and listed != records:
        r.append(f"apify_count_mismatch(got={records},listed={listed})")
    if errors:
        r.append(f"apify_errors={errors}")
    if errors is None:
        r.append("apify_errors_unread")
    if not log_read:
        r.append("apify_log_unread")
    for k in ("items_without_product_url", "duplicate_items", "items_without_price"):
        if counts[k]:
            r.append(f"{k}={counts[k]}")
    if counts["currency_not_reported"]:
        r.append(f"currency_not_reported(n={counts['currency_not_reported']})")
    return "partial", "; ".join(r)


def combine_parts(parts):
    if all(s == "ok" for s, _ in parts.values()):
        return "ok", ""
    if all(s == "could_not_look" for s, _ in parts.values()):
        return "could_not_look", "; ".join(f"{k}: {r}" for k, (_, r) in parts.items())
    return "partial", "; ".join(f"{k}: {r}" for k, (s, r) in parts.items() if s != "ok")


def redact_apify_run(run):
    run = copy.deepcopy(run)

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            return re.sub(r"signature=[^&\s\"']*", "signature=REDACTED", x)
        return x

    data = run.get("data")
    if isinstance(data, dict):
        if "userId" in data:
            data["userId"] = "REDACTED"
        if "output" in data:
            data["output"] = walk(data["output"])
    return run


def extract_slots(page, slots):
    out = []
    for name, sel in slots.items():
        els = page.query_selector_all(sel)
        out.append({"route": "home_dom", "slot": name, "selector": sel,
                    "state": "found" if els else "not_found",
                    "elements": [{"outer_html": e.evaluate("e => e.outerHTML"), "text": e.inner_text()}
                                 for e in els]})
    return out


def read_eml(path, manifest_gmail_id):
    try:
        data = Path(path).read_bytes()
        data.decode("ascii")
        msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(data)
        recv = str(msg["X-Trial-Received-At"])
        if (str(msg["X-Trial-Gmail-Id"]) != manifest_gmail_id or not TS_RE.match(recv)
                or str(msg["To"]) != "TRIAL_INBOX <trial_inbox@redacted.invalid>"
                or msg["X-Trial-Redaction"] is None):
            return None
        addr = email.utils.parseaddr(str(msg["From"]))[1]
        return {"file": Path(path).name, "gmail_id": manifest_gmail_id, "received_at": recv,
                "from_domain": addr.rsplit("@", 1)[-1].lower(),
                "sha256": hashlib.sha256(data).hexdigest(), "eml": data.decode("ascii")}
    except Exception:
        return None


def _ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _manifest_ok(m):
    try:
        _ts(m["exported_at"])
        return (isinstance(m["searched_domains"], list) and isinstance(m["spam_checked"], bool)
                and isinstance(m["messages"], list))
    except Exception:
        return False


def email_eval(signup, sender_domains, manifest, emls):
    """(state, reason, in-window messages, stats). stats values are None for unreached counters."""
    stats = dict(signup_at=None, first_day_ends_at=None, exported_at=None, first_day_complete=None,
                 spam_checked=None, in_window=None, before_signup=None, after_first_day=None, eml_invalid=None)

    def stop(reason):
        return "could_not_look", reason, [], stats

    if signup is None:
        return stop("no_signup_entry")
    if signup.get("signup_at") is None:
        return stop(f"not_signed_up(status={signup.get('status')})")
    sign = _ts(signup["signup_at"])
    end = sign + timedelta(seconds=FIRST_DAY_S)
    stats.update(signup_at=signup["signup_at"], first_day_ends_at=end.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if not sender_domains:
        return stop("sender_domains_unknown")
    if not isinstance(manifest, dict) or not _manifest_ok(manifest):
        return stop("no_inbox_export")
    for d in sender_domains:
        if d not in manifest["searched_domains"]:
            return stop(f"domain_not_searched({d})")
    exported = _ts(manifest["exported_at"])
    invalid = sum(1 for e in emls if e is None)
    start = sign - timedelta(seconds=SIGNUP_TOLERANCE_S)
    inwin, before, after = [], 0, 0
    for e in emls:
        if e is None or not any(e["from_domain"] == d or e["from_domain"].endswith("." + d)
                                for d in sender_domains):
            continue
        t = _ts(e["received_at"])
        if t < start:
            before += 1
        elif t >= end:
            after += 1
        else:
            inwin.append(e)
    complete = exported >= end
    stats.update(exported_at=manifest["exported_at"], first_day_complete=complete,
                 spam_checked=manifest["spam_checked"], in_window=len(inwin), before_signup=before,
                 after_first_day=after, eml_invalid=invalid)
    if complete and manifest["spam_checked"] and invalid == 0:
        return "ok", "", inwin, stats
    r = []
    if not complete:
        r.append(f"first_day_not_over(covered={(exported - sign).total_seconds() / 3600:.2f}h)")
    if not manifest["spam_checked"]:
        r.append("spam_not_checked")
    if invalid:
        r.append(f"eml_invalid={invalid}")
    return "partial", "; ".join(r), inwin, stats


def emails_part(signup, sender_domains, manifest, emls):
    return email_eval(signup, sender_domains, manifest, emls)[:3]


# ---------------------------------------------------------------- run plumbing
R = {}  # per-brand run state: fh, kinds, requests
_last = {}  # host -> monotonic time of the last request end


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def emit(kind, key, url, fetched_at, raw):
    R["fh"].write(json.dumps({"key": key, "kind": kind, "url": url, "fetched_at": fetched_at, "raw": raw},
                             ensure_ascii=False) + "\n")
    R["fh"].flush()
    R["kinds"][kind] += 1


def space(host):
    wait = _last.get(host, 0) + SPACING_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def http(url, method="GET", headers=None, data=None, timeout=HTTP_TIMEOUT_S, spaced=True):
    """-> (status, headers, body bytes). Raises on timeout / connection errors. Redirects are returned."""
    host = urlparse(url).hostname
    if spaced:
        space(host)
    R["requests"] += 1
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    try:
        try:
            with _opener.open(urllib.request.Request(url, data=data, headers=h, method=method), timeout=timeout) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
    finally:
        _last[host] = time.monotonic()


def err_reason(e):
    """timeout / request_error: <message> for a plain HTTP exception."""
    if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
        return "timeout"
    return f"request_error: {e}"


def read_token():
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                v = line[len("APIFY_TOKEN="):].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                return v or None
    except OSError:
        pass
    return None


# ---------------------------------------------------------------- Chrome steps
def navigate(page, url, host):
    """-> (response, reason). Counts one request."""
    from playwright.sync_api import TimeoutError as PWTimeout
    space(host)
    R["requests"] += 1
    try:
        resp = page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_S * 1000)
        if resp is None:
            return None, "navigation_error: no response"
        return resp, None
    except PWTimeout:
        return None, "timeout"
    except Exception as e:
        return None, f"navigation_error: {e}"
    finally:
        _last[host] = time.monotonic()


def blocked_reason(page, resp, host):
    h = urlparse(page.url).hostname
    if h != host:
        return f"blocked: host={h}"
    if resp.status in (403, 429):
        return f"blocked: http_{resp.status}"
    title = (page.title() or "").lower()
    for phrase in ("attention required", "just a moment"):
        if phrase in title:
            return f"blocked: title={phrase}"
    return None


def home_step(page, cfg):
    h = cfg["home"]
    part = {"state": "could_not_look", "reason": "", "market": None, "slots_not_found": None}
    resp, why = navigate(page, h["url"], h["host"])
    if not why:
        try:
            page.wait_for_timeout(HOME_SETTLE_S * 1000)
            why = blocked_reason(page, resp, h["host"])
        except Exception as e:
            why = f"navigation_error: {e}"
    if not why and resp.status >= 400:
        why = f"http_{resp.status}"
    if why:
        part["reason"] = why
        return part
    if h["shopify_market_check"]:
        c, cur = page.evaluate("() => [window.Shopify?.country ?? null, window.Shopify?.currency?.active ?? null]")
        part["market"] = {"country": c, "currency": cur}
    fetched_at = utc_now()
    missing = []
    for raw in extract_slots(page, h["slots"]):
        if raw["state"] == "not_found":
            missing.append(raw["slot"])
        emit("offer_slot", f"offer_slot/{h['host']}/{raw['slot']}", h["url"], fetched_at, raw)
    part.update(state="ok" if not missing else "partial",
                reason=f"slots_not_found({','.join(missing)})" if missing else "", slots_not_found=missing)
    return part


def fetch_products_page(page, host, n):
    """-> (products or None, reason or None)."""
    resp, why = navigate(page, f"https://{host}/products.json?limit={PRODUCTS_PAGE_SIZE}&page={n}", host)
    if why:
        return None, why
    try:
        why = blocked_reason(page, resp, host)
        if why:
            return None, why
        if resp.status != 200:
            return None, f"http_{resp.status}"
        body = resp.body()
    except Exception as e:
        return None, f"navigation_error: {e}"
    try:
        if not resp.headers.get("content-type", "").startswith("application/json"):
            return None, "not_json"
        data = json.loads(body)
    except ValueError:
        return None, "not_json"
    try:
        return parse_products_page(data), None
    except ShapeError:
        return None, "products_shape_changed"


def shopify_prices(page, cfg, home):
    host = cfg["prices"]["host"]
    part = {"state": "could_not_look", "reason": "", "route": "shopify_products_json", "records": None,
            "pages": None, "complete": None, "duplicate_products": None}
    if home["state"] == "could_not_look":
        part["reason"] = "market_unconfirmed"
        return part
    mk = home["market"]
    if not market_ok(mk["country"], mk["currency"]):
        part["reason"] = f"not_us(country={mk['country']},currency={mk['currency']})"
        return part
    seen, pages, dup, complete, reason = set(), 0, 0, False, ""
    for n in range(1, MAX_PRODUCT_PAGES + 1):
        products, why = fetch_products_page(page, host, n)
        fetched_at = utc_now()
        if why:
            reason = why if n == 1 else f"page_{n}: {why}"
            part["state"] = "could_not_look" if n == 1 else "partial"
            break
        pages += 1
        for p in products:
            key = product_key(host, p["handle"])
            if key in seen:
                dup += 1
                continue
            seen.add(key)
            emit("product", key, f"https://{host}/products/{p['handle']}", fetched_at,
                 {"route": "shopify_products_json", "page": n, "product": p})
        if len(products) < PRODUCTS_PAGE_SIZE:
            complete = True
            break
        if n == MAX_PRODUCT_PAGES:
            reason = "max_pages_reached"
    if complete:
        part["state"] = "ok"
    elif part["state"] != "could_not_look":
        part["state"] = "partial"
    part.update(reason=reason, records=len(seen), pages=pages, complete=complete, duplicate_products=dup)
    return part


# ---------------------------------------------------------------- Apify
def apify_prices(cfg, out_dir):
    """-> (part, cost_usd)."""
    listing_url = cfg["prices"]["listing_url"]
    part = {"state": "could_not_look", "reason": "", "route": "apify_ecommerce", "records": None,
            "run_id": None, "run_status": None, "listed": None, "items": None,
            "items_without_product_url": None, "duplicate_items": None, "items_without_price": None,
            "currency_not_reported": None, "errors": None}
    token = read_token()
    if not token:
        part["reason"] = "missing_token"
        return part, 0
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    api = "https://api.apify.com/v2"
    body = json.dumps({"listingUrls": [{"url": listing_url}], "maxProductResults": APIFY_MAX_PRODUCTS,
                       "additionalProperties": True, "deduplicateProducts": True}).encode()
    try:
        status, _, b = http(f"{api}/acts/{APIFY_ACTOR}/runs?maxTotalChargeUsd={APIFY_MAX_CHARGE_USD}"
                            f"&timeout={APIFY_RUN_TIMEOUT_S}", "POST", hdr, body, spaced=False)
    except Exception as e:
        part["reason"] = f"apify_start_failed: {type(e).__name__}"
        return part, 0
    run_id = None
    try:
        run_id = json.loads(b)["data"]["id"] if status == 201 else None
    except (ValueError, KeyError, TypeError):
        pass
    if not run_id:
        part["reason"] = f"apify_start_failed: http_{status}"
        return part, 0
    part["run_id"] = run_id
    started, fails, usage, run = time.monotonic(), 0, 0, None
    while True:
        try:
            status, _, b = http(f"{api}/actor-runs/{run_id}?waitForFinish={APIFY_POLL_WAIT_S}", headers=hdr,
                                timeout=APIFY_POLL_HTTP_TIMEOUT_S, spaced=False)
            cand = json.loads(b) if status == 200 else None
            ok = isinstance(cand, dict) and isinstance(cand.get("data"), dict)
        except Exception:
            ok = False
        if ok:
            fails, run = 0, cand
            usage = run["data"].get("usageTotalUsd") or usage
            if run["data"].get("status") in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break
        else:
            fails += 1
        if fails >= APIFY_POLL_ERRORS_MAX or time.monotonic() - started > APIFY_MAX_TOTAL_WAIT_S:
            part["reason"] = f"apify_wait_failed(run={run_id})"
            return part, usage
        if not ok:
            time.sleep(APIFY_POLL_ERROR_WAIT_S)
    data = run["data"]
    cost = data.get("usageTotalUsd") or 0
    part["run_status"] = data["status"]

    def get(url):
        """-> (text or None, failure reason or None)."""
        try:
            st, _, b = http(url, headers=hdr, spaced=False)
        except Exception as e:
            return None, type(e).__name__
        return (b.decode("utf-8", "replace"), None) if st == 200 else (None, f"http_{st}")

    items_text, items_why = get(f"{api}/datasets/{data.get('defaultDatasetId')}/items?clean=true&format=json")
    errors_id = (data.get("storageIds") or {}).get("datasets", {}).get("errors")
    errors_text, _ = get(f"{api}/datasets/{errors_id}/items?clean=true&format=json")
    log_text, _ = get(f"{api}/logs/{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(json.dumps(redact_apify_run(run), indent=2, ensure_ascii=False))
    if errors_text is not None:
        (out_dir / "errors.json").write_text(errors_text)
    if log_text is not None:
        (out_dir / "log.txt").write_text(log_text)
    items_arrived = utc_now()
    items = None
    if items_text is not None:
        try:
            items = json.loads(items_text)
        except ValueError:
            pass
        if not isinstance(items, list):
            items, items_why = None, "not_a_list"
    if items is None:
        part["reason"] = f"apify_items_failed: {items_why}"
        return part, cost
    errors = None
    if errors_text is not None:
        try:
            e = json.loads(errors_text)
            errors = len(e) if isinstance(e, list) else None
        except ValueError:
            pass
    counts = dict(items_without_product_url=0, duplicate_items=0, items_without_price=0, currency_not_reported=0)
    take, seen = [], set()
    for it in items:
        key = apify_item_key(it)
        if key is None:
            counts["items_without_product_url"] += 1
        elif key in seen:
            counts["duplicate_items"] += 1
        else:
            seen.add(key)
            take.append((key, it))
    currencies = []
    for _, it in take:
        offers = it.get("offers") if isinstance(it.get("offers"), dict) else {}
        if offers.get("price") is None:
            counts["items_without_price"] += 1
        cur = offers.get("priceCurrency")
        if cur is None:
            counts["currency_not_reported"] += 1
        else:
            currencies.append(cur)
    part.update(items=len(items), errors=errors, **counts)
    bad = sorted({str(c) for c in currencies if c != "USD"})
    if bad:
        part["reason"] = f"not_usd({','.join(bad)})"
        return part, cost
    for key, it in take:
        m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", it.get("scrapedAt") or "") if isinstance(it.get("scrapedAt"), str) else None
        emit("product", key, it["url"], m.group(1) + "Z" if m else items_arrived,
             {"route": "apify_ecommerce", "apify_run_id": run_id, "item": it})
    listed = apify_listed(log_text, listing_url) if log_text is not None else None
    max_hit = log_text is not None and "The maximum number of results per run has been reached" in log_text
    part["records"] = len(take)
    part["listed"] = listed
    part["state"], part["reason"] = apify_prices_state(data["status"], len(take), listed, max_hit, errors,
                                                       log_text is not None, counts)
    return part, cost


# ---------------------------------------------------------------- Batiste
def wtb_failure(status, body):
    """Error text for a non-200 where-to-buy response, and whether the loop must stop."""
    if status == 403:
        try:
            detail = json.loads(body).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str) and detail.startswith("Unauthorized ProductUIDs"):
            return "unauthorized_product", False
    if status in (403, 429):
        return f"blocked: http_{status}", True
    return f"http_{status}", True


def batiste_prices(cfg, out_dir):
    c = cfg["prices"]
    part = {"state": "could_not_look", "reason": "", "route": "batiste_wtb", "records": None,
            "product_pages": None, "eans": None, "fetched": None, "failed": None, "not_attempted": None}
    base = "https://www.batistehair.com"
    # 1. listing
    try:
        status, _, b = http(c["listing_url"])
    except Exception as e:
        part["reason"] = "listing_" + err_reason(e)
        return part
    html = b.decode("utf-8", "replace")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "listing.html").write_text(html)
    if status != 200:
        part["reason"] = f"listing_http_{status}"
        return part
    try:
        paths = parse_batiste_listing(html)
    except ShapeError as e:
        part["reason"] = str(e)
        return part
    # 2. product pages
    pages, ean_pages, failures = [], {}, 0
    for path in paths:
        p = {"path": path, "state": None, "eans": [], "location": None, "error": None}
        try:
            status, hd, b = http(base + path)
            p["state"], p["eans"] = classify_batiste_page(status, hd.get("Location"), b.decode("utf-8", "replace"), c["wtbid"])
            if p["state"] == "redirected":
                p["location"] = hd.get("Location")
            elif p["state"] == "failed":
                p["error"] = f"http_{status}"
        except Exception as e:
            p["state"], p["error"] = "failed", err_reason(e)
        failures += p["state"] in ("failed", "widget_missing")
        for ean in p["eans"]:
            ean_pages.setdefault(ean, []).append(path)
        pages.append(p)
    part["product_pages"] = pages
    if not ean_pages:
        part["reason"] = "no_eans"
        return part
    # 4. widget API
    res = {ean: {"state": "not_attempted", "error": None, "response": None, "at": None} for ean in ean_pages}
    stopped, not_us = False, None
    for ean in ean_pages:
        if stopped:
            break
        r = res[ean]
        keep_going = False
        try:
            status, _, b = http(WTB_URL.format(ean=ean, wtbid=c["wtbid"]), headers={"Accept": "application/json"})
            r["at"] = utc_now()
            if status != 200:
                r["error"], must_stop = wtb_failure(status, b)
                keep_going = not must_stop
            else:
                try:
                    resp = json.loads(b)
                    loc = validate_wtb(resp, ean)
                    if market_ok(*loc):
                        r["state"], r["response"] = "fetched", resp
                    else:
                        not_us = loc
                except (ValueError, ShapeError):
                    r["error"] = "shape_changed"
        except Exception as e:
            r["at"] = utc_now()
            r["error"] = err_reason(e)
        if not_us:
            break
        if r["error"]:
            r["state"] = "failed"
            stopped = not keep_going
    stop_at = utc_now()
    if not_us:
        for r in res.values():
            r.update(state="not_us", response=None, error=None)
    # 5. records
    for ean, paths_ in ean_pages.items():
        r = res[ean]
        emit("retailer_availability", f"wtb/{ean}", base + paths_[0], r["at"] or stop_at,
             {"route": "batiste_wtb", "ean": ean, "product_pages": paths_, "state": r["state"],
              "error": r["error"], "response": r["response"]})
    states = Counter(r["state"] for r in res.values())
    failed = [r for r in res.values() if r["state"] == "failed"]
    na = states["not_attempted"]
    part.update(records=len(res), eans=len(res), fetched=states["fetched"], failed=len(failed), not_attempted=na)
    if not_us:
        part["reason"] = f"not_us(country={not_us[0]},currency={not_us[1]})"
    elif states["fetched"] == 0 and failed:
        part["reason"] = failed[0]["error"] + (f"; eans_not_attempted={na}" if na else "")
    elif states["fetched"] == len(res) and failures == 0:
        part["state"] = "ok"
    else:
        part["state"] = "partial"
        r_ = []
        if failures:
            r_.append(f"product_pages_failed={failures}")
        other = [r for r in failed if r["error"] != "unauthorized_product"]
        if other:
            r_.append(other[0]["error"])
        if len(other) < len(failed):
            r_.append(f"eans_unauthorized={len(failed) - len(other)}")
        if na:
            r_.append(f"eans_not_attempted={na}")
        part["reason"] = "; ".join(r_)
    return part


# ---------------------------------------------------------------- Klaviyo, emails
def klaviyo_step(cfg, out_dir):
    cid = cfg["klaviyo_company_id"]
    url = f"https://static-forms.klaviyo.com/forms/api/v7/{cid}/full-forms"
    part = {"state": "could_not_look", "reason": "", "forms": None}
    try:
        status, _, b = http(url, headers={"Accept": "application/json"})
    except Exception as e:
        part["reason"] = f"klaviyo_{err_reason(e)}"
        return part
    fetched_at = utc_now()
    if status != 200:
        part["reason"] = f"klaviyo_http_{status}"
        return part
    try:
        forms = parse_klaviyo(json.loads(b))
    except (ValueError, ShapeError):
        part["reason"] = "klaviyo_shape_changed"
        return part
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "full-forms.json").write_bytes(b)
    for f in forms:
        emit("klaviyo_form", f"klaviyo_form/{cid}/{f['form_id']}", url, fetched_at,
             {"route": "klaviyo_full_forms", "company_id": cid, "form": f})
    part.update(state="ok", forms=len(forms))
    return part


def emails_step(cfg, name):
    signup = None
    try:
        for s in json.loads(SIGNUPS_JSON.read_text())["signups"]:
            if s.get("brand") == name:
                signup = s
    except (OSError, ValueError, KeyError, TypeError):
        pass
    manifest = None
    try:
        manifest = json.loads((EXPORT_DIR / "export.json").read_text())
    except (OSError, ValueError):
        pass
    emls = []
    if isinstance(manifest, dict) and isinstance(manifest.get("messages"), list):
        for m in manifest["messages"]:
            ok = isinstance(m, dict) and isinstance(m.get("file"), str) and isinstance(m.get("gmail_id"), str)
            emls.append(read_eml(EXPORT_DIR / m["file"], m["gmail_id"]) if ok else None)
    state, reason, msgs, stats = email_eval(signup, cfg["email_sender_domains"], manifest, emls)
    for e in msgs:
        emit("email", f"email/{e['gmail_id']}", signup["signup_url"], manifest["exported_at"],
             {"route": "inbox_export", "file": e["file"], "sha256": e["sha256"], "eml": e["eml"],
              "signup_at": stats["signup_at"], "first_day_ends_at": stats["first_day_ends_at"],
              "exported_at": stats["exported_at"], "spam_checked": stats["spam_checked"]})
    return {"state": state, "reason": reason, **stats}


# ---------------------------------------------------------------- brand run
def offers_part(home, klaviyo):
    subs = {"home": home, **({"klaviyo": klaviyo} if klaviyo else {})}
    state, reason = combine_parts({k: (v["state"], v["reason"]) for k, v in subs.items()})
    return {"state": state, "reason": reason, "home": home, "klaviyo": klaviyo}


def run_brand(slug, inputs, names):
    from playwright.sync_api import sync_playwright
    cfg = inputs[slug]
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out = RAW_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    part_path = out / f"{run_id}.jsonl.part"
    R.clear()
    R.update(fh=open(part_path, "w", encoding="utf-8"), kinds=Counter(), requests=0)
    parts, cost, status, reason, crashed = {}, 0, None, "", False
    try:
        log(f"[{slug}] start {run_id}")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, channel="chrome", args=["--lang=en-US"])
            try:
                ctx = browser.new_context(locale="en-US", timezone_id="America/New_York",
                                          viewport={"width": 1400, "height": 950})
                page = ctx.new_page()
                home = home_step(page, cfg)
                route = cfg["prices"]["route"]
                if route == "shopify_products_json":
                    parts["prices"] = shopify_prices(page, cfg, home)
                elif route == "apify_ecommerce":
                    parts["prices"], cost = apify_prices(cfg, out / f"{run_id}.apify")
                else:
                    parts["prices"] = batiste_prices(cfg, out / f"{run_id}.batiste")
            finally:
                browser.close()
        klaviyo = klaviyo_step(cfg, out / f"{run_id}.klaviyo") if cfg["klaviyo_company_id"] else None
        parts["offers"] = offers_part(home, klaviyo)
        parts["emails"] = emails_step(cfg, names[slug])
        status, reason = combine_parts({k: (parts[k]["state"], parts[k]["reason"]) for k in ("prices", "offers", "emails")})
    except Exception as e:
        crashed = True
        status = "partial" if sum(R["kinds"].values()) else "could_not_look"
        reason = f"exception: {type(e).__name__}: {e}"
    finally:
        R["fh"].close()
        part_path.rename(out / f"{run_id}.jsonl")
    result = {"source": "brand_site_and_emails", "brand": slug, "run_id": run_id,
              "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "finished_at": utc_now(),
              "status": status, "reason": reason, "records": sum(R["kinds"].values()),
              "records_by_kind": dict(R["kinds"]), "expected_total": None, "requests": R["requests"],
              "cost_usd": cost, "extra": {"parts": parts}}
    (out / f"{run_id}.run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    log(f"[{slug}] {status} | {reason} | {result['records_by_kind']} | cost_usd={cost}")
    return crashed


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--brand")
    g.add_argument("--all", action="store_true")
    a = ap.parse_args()
    brands = json.loads(BRANDS_JSON.read_text())
    names = {b["slug"]: b["name"] for b in brands}
    if a.brand and a.brand not in names:
        ap.error(f"unknown brand {a.brand}")
    inputs = json.loads((HERE / "brand_inputs.json").read_text())
    crashed = [run_brand(s, inputs, names) for s in ([a.brand] if a.brand else list(names))]
    sys.exit(1 if any(crashed) else 0)


if __name__ == "__main__":
    main()
