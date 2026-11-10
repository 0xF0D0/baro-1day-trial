"""Round trip of every real mapper through the loader and Postgres.

For each source: load a realistic complete run, load the same content again, then load a run in which one
item is gone. The checks compare what the mapper returns with what the database stores, and check the
loader's ending rules with the real mappers' scopes and ending policies.
"""
import copy
import json
import unittest
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import support
from support import DbTestCase, ts
import mappers
from load import load_all
from model import TABLE_COLUMNS

import test_amazon as t_amazon
import test_brand_site_and_emails as t_brand
import test_google_ads_transparency as t_gat
import test_google_results as t_gres
import test_meta_ad_library as t_meta
import test_retail_shelf as t_retail
import test_search_interest as t_interest
import test_tiktok_ads as t_tads
import test_tiktok_posts as t_posts
import test_tiktok_shop as t_shop

RUN1, RUN2, RUN3 = "20261110T100000Z", "20261110T110000Z", "20261110T120000Z"


@dataclass
class Gone:
    """The third run: the records that remain, the run extra, and how many rows the absence must end."""
    records: list
    extra: dict
    ends: int


@dataclass
class Case:
    source: str
    brand: str
    status: str
    reason: str
    extra: dict
    records: list
    gone: Gone | None = None


# ---------------------------------------------------------------- comparison

def _instant(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def same_value(expected, stored) -> bool:
    """Whether a stored value equals the mapper's value after the natural type conversion."""
    if expected is None or stored is None:
        return expected is None and stored is None
    if isinstance(expected, bool) or isinstance(stored, bool):
        return isinstance(expected, bool) and isinstance(stored, bool) and expected == stored
    if isinstance(stored, Decimal):
        return isinstance(expected, (int, float, Decimal)) and Decimal(str(expected)) == stored
    if isinstance(stored, datetime):
        return isinstance(expected, (str, datetime)) and _instant(expected) == stored
    if isinstance(stored, date):
        return isinstance(expected, date) and not isinstance(expected, datetime) and expected == stored
    if isinstance(stored, list):
        return isinstance(expected, (list, tuple)) and list(expected) == stored
    return type(expected) is type(stored) and expected == stored


class RoundTripCase(DbTestCase):
    # ------------------------------------------------------------ helpers

    def read_back(self, path):
        """The run result and the records exactly as the loader reads them from the files."""
        run = json.loads(path.read_text())
        lines = path.with_name(run["run_id"] + ".jsonl").read_text().splitlines()
        return run, [json.loads(line) for line in lines if line.strip()]

    def expected(self, path):
        """The rows map_run returns for a written run, de-duplicated by key as the loader does."""
        run, records = self.read_back(path)
        mapped = mappers.MAPPERS[run["source"]].map_run(run, records)
        latest = {}
        for row in mapped.rows:
            latest[(row.table, row.kind, row.key)] = row
        return latest

    def stored(self, source, brand):
        out = {}
        for table in TABLE_COLUMNS:
            for r in self._query(f"SELECT * FROM {table} WHERE source = %s AND brand = %s", (source, brand)):
                out[(table, r["kind"], r["key"])] = r
        return out

    def load(self):
        return {(o.source, o.brand, o.run_id): o for o in load_all(self.conn, self.dir, mappers.MAPPERS)}

    def write(self, case, run_id, records, extra):
        return self.write_run(case.source, case.brand, run_id, case.status, records, case.reason, extra)

    def diffs(self, expected, stored):
        problems = []
        for (table, kind, key), row in expected.items():
            where = f"{row.table}/{row.kind}/{row.key}"
            r = stored.get((table, kind, key))
            if r is None:
                problems.append(f"{where}: no stored row")
                continue
            for name in row.columns:
                if not same_value(row.columns[name], r[name]):
                    problems.append(f"{where}: column {name}: mapper {row.columns[name]!r} stored {r[name]!r}")
            for name, want, got in (("scope", row.scope, r["scope"]), ("url", row.url, r["url"]),
                                    ("raw", row.raw, r["raw"])):
                if want != got:
                    problems.append(f"{where}: {name}: mapper {want!r} stored {got!r}")
            if _instant(row.fetched_at) != r["fetched_at"]:
                problems.append(f"{where}: fetched_at: mapper {row.fetched_at!r} stored {r['fetched_at']!r}")
        return problems

    def counts(self, rows):
        out = {}
        for table, _, _ in rows:
            out[table] = out.get(table, 0) + 1
        return out

    # ------------------------------------------------------------ steps

    def step1(self, cases):
        paths = [self.write(c, RUN1, c.records, c.extra) for c in cases]
        outcomes = self.load()
        for case, path in zip(cases, paths):
            label = f"{case.source}/{case.brand}"
            out = outcomes[(case.source, case.brand, RUN1)]
            self.assertEqual((out.result, out.error), ("applied", ""), label)
            expected = self.expected(path)
            self.assertTrue(expected, f"{label}: the mapper returned no rows")
            stored = self.stored(case.source, case.brand)
            self.assertEqual(self.diffs(expected, stored), [], label)
            self.assertEqual(self.counts(stored), self.counts(expected), label)
            self.assertEqual(set(stored), set(expected), label)
        mapper = mappers.MAPPERS[cases[0].source]
        seen = {(t, k) for case, path in zip(cases, paths) for (t, k, _) in self.expected(path)}
        self.assertEqual(seen, set(mapper.ENDING), "record kinds covered")

    def step2(self, cases):
        paths = [self.write(c, RUN2, c.records, c.extra) for c in cases]
        outcomes = self.load()
        for case, path in zip(cases, paths):
            label = f"{case.source}/{case.brand}"
            before = self.stored(case.source, case.brand)
            out = outcomes[(case.source, case.brand, RUN2)]
            self.assertEqual((out.result, out.error, out.inserted, out.ended), ("applied", "", 0, 0), label)
            stored = self.stored(case.source, case.brand)
            self.assertEqual(self.counts(stored), self.counts(before), label)
            self.assertEqual(set(stored), set(before), label)
            ending = mappers.MAPPERS[case.source].ENDING
            for (table, kind, key), r in stored.items():
                if ending[(table, kind)] in ("absent", "never"):
                    self.assertEqual(r["last_seen_at"], ts(RUN2), f"{label}: {table}/{kind}/{key} last_seen_at")
                    self.assertEqual(r["last_run_id"], RUN2, f"{label}: {table}/{kind}/{key} last_run_id")

    def step3(self, cases):
        cases = [c for c in cases if c.gone is not None]
        snapshots, wanted = {}, {}
        for case in cases:
            snapshots[case.source, case.brand] = self.stored(case.source, case.brand)
            gone_path = self.write(case, RUN3, case.gone.records, case.gone.extra)
            before = {k for k in self.expected(self.dir / case.source / "raw" / case.brand / f"{RUN2}.run.json")}
            after = set(self.expected(gone_path))
            ending = mappers.MAPPERS[case.source].ENDING
            wanted[case.source, case.brand] = {k for k in before - after if ending[(k[0], k[1])] == "absent"}
        outcomes = self.load()
        for case in cases:
            label = f"{case.source}/{case.brand}"
            before = snapshots[case.source, case.brand]
            ends = wanted[case.source, case.brand]
            self.assertEqual(len(ends), case.gone.ends, f"{label}: rows the absence should end")
            out = outcomes[(case.source, case.brand, RUN3)]
            self.assertEqual((out.result, out.error, out.ended), ("applied", "", case.gone.ends), label)
            stored = self.stored(case.source, case.brand)
            self.assertTrue(set(before) <= set(stored), f"{label}: a row was deleted")
            for key, r in stored.items():
                if key in before:
                    want = ts(RUN3) if key in ends else before[key]["ended_at"]
                    self.assertEqual(r["ended_at"], want, f"{label}: {key} ended_at")
                else:
                    self.assertIsNone(r["ended_at"], f"{label}: new row {key} ended_at")

    def round_trip(self, cases):
        self.step1(cases)
        self.step2(cases)
        self.step3(cases)


# ---------------------------------------------------------------- fixtures

def google_ads_transparency():
    items = t_gat.DEATH_ITEMS
    old = next(i for i in items if i["2"] == "CR15044796763124793345")
    records = [t_gat.record(items[0], t_gat.VIDEO_DETAIL, "fetched"),
               t_gat.record(items[1], t_gat.TEXT_DETAIL, "fetched")]
    records += [t_gat.record(i) for i in items[2:6]] + [t_gat.record(old)]
    run = t_gat.RUN_OK
    gone = Gone(records[:3] + records[4:], run["extra"], 0)
    return [Case("google_ads_transparency", "death-wish-coffee", run["status"], run["reason"], run["extra"],
                 records, gone)]


def tiktok_ads():
    ids = list(t_tads.ROWS)
    terms = {t_tads.LP: ["living proof", "livingproof"], t_tads.JINX: ["@jinx", "#jinxpartner"]}
    records = [t_tads.ad(i, terms.get(i, ["living proof"])) for i in ids]
    run = t_tads.RUN_OK
    return [Case("tiktok_ads", "living-proof", run["status"], run["reason"], {"rows": len(records)}, records,
                 Gone(records[1:], {"rows": len(records) - 1}, 1))]


def meta_extra(pages, counts):
    return {"pages": pages, "counts": counts, "runs": {}, "media_files": 0, "media_failed": 0}


def meta_ad_library():
    page = "40730897173"
    pages = {page: {"ads_complete": True, "reasons": []}}
    records = [t_meta.record(i) for i in list(t_meta.ITEMS)[:10]]
    run = t_meta.RUN
    return [Case("meta_ad_library", "living-proof", run["status"], run["reason"],
                 meta_extra(pages, {page: len(records)}), records,
                 Gone(records[:4] + records[5:], meta_extra(pages, {page: len(records) - 1}), 1))]


def amazon():
    detail = {i["asin"]: i for i in t_amazon.sample("dataset_junglee_3asins.json")}
    search = {i["asin"]: i for i in t_amazon.sample("dataset_apt_marble_dw60.json")}
    reviews = t_amazon.sample("dataset_2asins_5each.json")
    asins = list(detail)
    products = [t_amazon.product(detail[a], rank=n + 1, key=a, search=search.get(a)) for n, a in enumerate(asins)]
    revs = [t_amazon.review(r, asin=r["ASIN"]) for r in reviews]
    extra = {"search_rows": 60, "candidates": 27, "selected": len(products)}
    gone_asin = "B006CQ1ZHI"
    keep = [p for p in products if p["key"] != gone_asin] + [r for r in revs if r["raw"]["product_asin"] != gone_asin]
    ok = t_amazon.OK
    return [Case("amazon", "death-wish-coffee", ok["status"], ok["reason"], extra, products + revs,
                 Gone(keep, {**extra, "selected": len(products) - 1}, 1))]


def retail_shelf():
    ulta_items = [
        (t_retail.ULTA_LI, 1),
        ({**t_retail.ULTA_LI, "productId": "pimprod2045776", "productName": "Dry Shampoo - Rose",
          "listPrice": "$12.99 - $20.99", "rating": 4.2, "reviewCount": 1203}, 2),
        ({**t_retail.ULTA_LI, "productId": "pimprod2045777", "productName": "Dry Shampoo - Travel Size",
          "listPrice": "$12.99", "salePrice": "$9.74", "rating": 3.75, "reviewCount": 88, "sponsored": True}, 3)]
    products, reviews = [], []
    for li, rank in ulta_items:
        products.append(t_retail.product("ulta", li, rank=rank, key="ulta:" + li["productId"]))
    first = "ulta:" + ulta_items[0][0]["productId"]
    for n in range(3):
        r = {**t_retail.ULTA_R, "ugc_id": t_retail.ULTA_R["ugc_id"] + n,
             "details": {**t_retail.ULTA_R["details"], "created_date": t_retail.ULTA_R["details"]["created_date"] - n * 86400000},
             "badges": {"is_verified_buyer": bool(n % 2)}, "metrics": {"rating": 5 - n, "helpful_votes": n}}
        reviews.append(t_retail.review("ulta", first, r, key=f"{first}:{r['ugc_id']}"))
    second = "ulta:" + ulta_items[1][0]["productId"]
    reviews.append(t_retail.review("ulta", second, t_retail.ULTA_R, key=f"{second}:589138362"))
    for n, li in enumerate(t_retail.items("apify/target_al_store2581_4brands.json")[:3]):
        products.append(t_retail.product("target", li, rank=n + 1, key="target:" + li["tcin"]))
    for n, r in enumerate(t_retail.items("apify/target_reviews_A-88498115.json")[:3]):
        reviews.append(t_retail.review("target", "target:88498115", r, key=f"target:88498115:h{n}"))
    for n, li in enumerate(t_retail.items("apify/sephora_search_igview_bestselling_3.json")):
        products.append(t_retail.product("sephora", li, rank=n + 1, key="sephora:" + li["productId"]))
    for n, li in enumerate(t_retail.items("apify/chewy_search_jinx_parseforge.json")[:3]):
        products.append(t_retail.product("chewy", li, rank=n + 1, key="chewy:" + li["partNumber"]))
    for n, r in enumerate(t_retail.items("apify/chewy_reviews_alc_845310.json")[:3]):
        reviews.append(t_retail.review("chewy", "chewy:845310", r, key=f"chewy:845310:r{n}"))

    def cells(ulta_selected):
        return {"cells": [{"retailer": "ulta", "status": "ok", "reason": "", "selected": ulta_selected},
                          {"retailer": "target", "status": "ok", "reason": "", "selected": 3},
                          {"retailer": "sephora", "status": "ok", "reason": "", "selected": 3},
                          {"retailer": "chewy", "status": "ok", "reason": "", "selected": 3}]}

    gone = Gone([p for p in products if p["key"] != first]
                + [r for r in reviews if r["raw"]["product_key"] != first], cells(2), 1)
    return [Case("retail_shelf", "batiste", "ok", "", cells(3), products + reviews, gone)]


def google_results():
    terms = list(t_gres.ITEMS)
    records = [t_gres.record(t, n + 1) for n, t in enumerate(terms)]
    term = "batiste dry shampoo"
    serp = copy.deepcopy(t_gres.ITEMS[term])
    serp["organicResults"].pop(2)
    kept = [t_gres.record(term, 2, serp=serp) if r["key"] == term else r for r in records]
    run = t_gres.RUN_OK
    return [Case("google_results", "death-wish-coffee", run["status"], run["reason"], {}, records,
                 Gone(kept, {}, 1))]


def search_interest():
    files = {"Batiste dry shampoo": "multiline_batiste_dry_shampoo_fixed.txt",
             "Living Proof shampoo": "multiline_living_proof_shampoo_fixed.txt",
             "Death Wish Coffee": "multiline_death_wish_coffee_fixed.txt",
             "Black Rifle Coffee": "multiline_black_rifle_coffee_fixed.txt",
             "Jinx dog food": "multiline_jinx_dog_food_fixed.txt"}
    records = []
    for term, name in files.items():
        records += [t_interest.solo_record(term, name, i) for i in (0, 1, -1)]
    for term in files:
        records += [t_interest.compared_record(term, i) for i in (0, 1, -1)]
    run = t_interest.OK
    return [Case("search_interest", "batiste", run["status"], run["reason"], run["extra"], records,
                 Gone(records[:4] + records[5:], run["extra"], 0))]


def tiktok_posts():
    records = [t_posts.post("profile_popular", n + 1, item) for n, item in enumerate(t_posts.PROFILE)]
    records += [t_posts.post("hashtag", n + 1, item) for n, item in enumerate(t_posts.HASHTAG)]
    run = t_posts.RUN
    return [Case("tiktok_posts", run["brand"], run["status"], run["reason"], run["extra"], records,
                 Gone(records[1:], run["extra"], 0))]


def tiktok_shop():
    tracked = [t_shop.envelope(i) for i in t_shop.sample("product_ids_2.items.json")]
    items = t_shop.sample("search_death_wish_coffee_20.items.json")
    search = [t_shop.envelope(i, part="search") for i in items]
    # The search part stays complete (20 results): the removed result is replaced by another product.
    other = {**items[4], "productId": "1799999999999999999", "rank": items[3]["rank"]}
    changed = search[:3] + [t_shop.envelope(other, part="search")] + search[4:]
    run = t_shop.OK_RUN
    return [Case("tiktok_shop", "death-wish-coffee", run["status"], run["reason"], run["extra"],
                 tracked + search, Gone(tracked + changed, run["extra"], 1))]


BRAND_HOST = "www.deathwishcoffee.com"


def brand_site_and_emails():
    products = []
    for p in t_brand.load("products_deathwish_trimmed.json")["products"]:
        raw = {"route": "shopify_products_json", "page": 1, "product": p}
        products.append(t_brand.record(f"product/{BRAND_HOST}/{p['handle']}", "product", raw,
                                       f"https://{BRAND_HOST}/products/{p['handle']}"))
    slots = [t_brand.slot("announcement_bar", "found", ["FREE SHIPPING ON ORDERS OVER $50"]),
             t_brand.slot("banner_heading", "found", ["HOLIDAY ROASTS", "SHOP NOW"]),
             t_brand.slot("footer_newsletter", "found", ["Sign up and get 10% off"]),
             t_brand.slot("cart_note", "not_found", [])]
    forms = [t_brand.record(f"klaviyo_form/H99sYH/{f['form_id']}", "klaviyo_form",
                            {"route": "klaviyo_full_forms", "company_id": "H99sYH", "form": f})
             for f in t_brand.load("klaviyo_forms_livingproof.json")["full_forms"][:3]]
    emails = []
    for path in sorted((t_brand.SAMPLES / "eml").glob("*.eml")):
        emails.append(t_brand.record("email/" + path.stem.rsplit("_", 1)[1], "email",
                                     {"route": "inbox_export", "file": path.name,
                                      "eml": path.read_bytes().decode("ascii"), "exported_at": "2026-11-10T07:26:17Z"}))
    ok = {"state": "ok", "reason": ""}
    parts = {"prices": {**ok, "route": "shopify_products_json"},
             "offers": {**ok, "home": ok, "klaviyo": ok}, "emails": ok}
    extra = {"parts": parts}
    main = Case("brand_site_and_emails", "death-wish-coffee", "ok", "", extra, products + slots + forms + emails,
                Gone(products[1:] + slots + forms + emails, extra, 1))

    response = t_brand.load("batiste", "wtb_availabilities_5010724526705_full.json")
    pages = [{"path": "/products/bare", "state": "widget", "eans": ["5010724526705"]}]
    batiste_parts = {"prices": {**ok, "route": "batiste_wtb", "product_pages": pages},
                     "offers": {**ok, "home": ok}}
    batiste = Case("brand_site_and_emails", "batiste", "ok", "", {"parts": batiste_parts},
                   [t_brand.availability("5010724526705", response=response),
                    t_brand.slot("community_signup", "found", ["Join the community"])])

    items = t_brand.load("apify", "blackrifle_run2_items.json")[:5]
    apify = [t_brand.record("product/www.blackriflecoffee.com/" + i["url"].rsplit("/", 1)[1], "product",
                            {"route": "apify_ecommerce", "apify_run_id": "r1", "item": i}, i["url"]) for i in items]
    black = Case("brand_site_and_emails", "black-rifle-coffee", "ok", "",
                 {"parts": {"prices": {**ok, "route": "apify_ecommerce"}}}, apify)
    return [main, batiste, black]


class RoundTripTest(RoundTripCase):
    def test_google_ads_transparency(self):
        self.round_trip(google_ads_transparency())

    def test_tiktok_ads(self):
        self.round_trip(tiktok_ads())

    def test_meta_ad_library(self):
        self.round_trip(meta_ad_library())

    def test_amazon(self):
        self.round_trip(amazon())

    def test_retail_shelf(self):
        self.round_trip(retail_shelf())

    def test_google_results(self):
        self.round_trip(google_results())

    def test_search_interest(self):
        self.round_trip(search_interest())

    def test_tiktok_posts(self):
        self.round_trip(tiktok_posts())

    def test_tiktok_shop(self):
        self.round_trip(tiktok_shop())

    def test_brand_site_and_emails(self):
        self.round_trip(brand_site_and_emails())

    def test_meta_two_pages(self):
        source, brand, a, b = "meta_ad_library", "living-proof", "40730897173", "999"
        ids = list(t_meta.ITEMS)
        recs_a = [t_meta.record(i) for i in ids[:4]]
        recs_b = [t_meta.record(i) for i in ids[4:7]]
        for r in recs_b:
            r["raw"]["page_id"] = b
        complete = {"ads_complete": True, "reasons": []}
        first = meta_extra({a: complete, b: complete}, {a: 4, b: 3})
        self.write_run(source, brand, RUN1, "ok", recs_a + recs_b, "", first)
        out = self.load()[(source, brand, RUN1)]
        self.assertEqual((out.result, out.error), ("applied", ""))
        self.assertEqual(len(self.stored(source, brand)), 7)

        self.write_run(source, brand, RUN2, "partial", recs_a[:3], "blocked(999)", meta_extra(
            {a: complete, b: {"ads_complete": False, "reasons": ["blocked(999)"]}}, {a: 3}))
        out = self.load()[(source, brand, RUN2)]
        self.assertEqual((out.result, out.error, out.inserted, out.ended), ("applied", "", 0, 1))
        ended = {k[2]: r["ended_at"] for k, r in self.stored(source, brand).items()}
        self.assertEqual(ended[recs_a[3]["key"]], ts(RUN2))
        for r in recs_a[:3] + recs_b:
            self.assertIsNone(ended[r["key"]], r["key"])
        self.assertEqual(len(ended), 7)


if __name__ == "__main__":
    unittest.main()
