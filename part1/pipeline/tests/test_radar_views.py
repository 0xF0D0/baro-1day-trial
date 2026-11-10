import unittest
from datetime import timezone
from decimal import Decimal

from support import DbTestCase

COMMON = {"kind": "x", "scope": "all", "fetched_at": "2026-11-10T00:00:00Z", "first_seen_at": "2026-11-01T00:00:00Z",
          "last_seen_at": "2026-11-10T00:00:00Z", "last_run_id": "r", "raw": "{}"}
TABLE_DEFAULTS = {"ads": {"source": "fake", "brand": "b", "kind": "ad", "channel": "meta"},
                  "products": {"source": "amazon", "brand": "b", "kind": "product", "retailer": "amazon"},
                  "posts": {"source": "tiktok_posts", "brand": "b", "kind": "post"},
                  "search_rankings": {"source": "google_results", "brand": "b", "kind": "organic", "keyword": "k"}}


class RadarViewsBase(DbTestCase):
    def insert(self, table, key, **columns):
        values = {**COMMON, **TABLE_DEFAULTS[table], "key": key, **columns}
        names = ", ".join(values)
        marks = ", ".join(["%s"] * len(values))
        self.conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(values.values()))
        self.conn.commit()

    def ad(self, key, **columns):
        self.insert("ads", key, **columns)

    def post(self, key, **columns):
        self.insert("posts", key, **columns)

    def product(self, key, **columns):
        self.insert("products", key, **columns)

    def ranking(self, key, **columns):
        self.insert("search_rankings", key, **columns)

    def change(self, key, field, old, new, changed_at, table="products", change="changed", source="amazon",
               kind="product", run_id="r", brand="b"):
        self.conn.execute(
            "INSERT INTO changes (changed_at, run_id, source, brand, table_name, kind, key, change, field, old_value, new_value) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (changed_at, run_id, source, brand, table, kind, key, change, field, old, new))
        self.conn.commit()

    def running(self, *names):
        rows = self._query(f"SELECT key, {', '.join(names)} FROM radar_running")
        return {r["key"]: tuple(r[n] for n in names) for r in rows}


class RadarViewsTest(RadarViewsBase):
    def test_destination_and_subject(self):
        cases = [  # landing_domain, landing_url, destination, subject_type, subject
            ("livingproof.com", "https://www.livingproof.com/products/sheer-clean-mist?x=1#top", "brand_site", "product", "sheer-clean-mist"),
            ("livingproof.com", "https://www.livingproof.com/collections/holiday-kits/products/the-set/", "brand_site", "product", "the-set"),
            ("livingproof.com", "https://www.livingproof.com/collections/holiday-kits", "brand_site", "collection", "collections/holiday-kits"),
            ("livingproof.com", "https://www.livingproof.com/pages/dry-shampoo", "brand_site", "page", "pages/dry-shampoo"),
            ("livingproof.com", "https://www.livingproof.com/", "brand_site", "home", "home"),
            ("buy.batistehair.com", "https://buy.batistehair.com/social/abc", "brand_site", "page", "social/abc"),
            ("ulta.com", "https://www.ulta.com/p/berry-disco-pimprod1", "retailer", "retailer_product", "ulta.com/p/berry-disco-pimprod1"),
            ("example.org", "https://example.org/x", "other", "other", "example.org/x"),
            ("thinkjinx.com", None, "brand_site", None, None),
            (None, None, None, None, None)]
        for i, (domain, url, *_) in enumerate(cases):
            self.ad(f"a{i}", landing_domain=domain, landing_url=url)
        got = self.running("destination", "subject_type", "subject")
        for i, (_, _, *expected) in enumerate(cases):
            self.assertEqual(got[f"a{i}"], tuple(expected), f"case {i}")

    def test_domain_match_is_equal_or_subdomain(self):
        self.ad("x1", landing_domain="notulta.com", landing_url="https://notulta.com/a")
        self.ad("x2", landing_domain="m.target.com", landing_url="https://m.target.com/p/a")
        self.ad("x3", landing_domain="fakebatistehair.com", landing_url="https://fakebatistehair.com/a")
        got = self.running("destination")
        self.assertEqual(got["x1"], ("other",))
        self.assertEqual(got["x2"], ("retailer",))
        self.assertEqual(got["x3"], ("other",))

    def test_days_live_and_verdict(self):
        cases = [  # started_at, first_seen_at, last_seen_at, ended_at, appeared row?, start_basis, days_live, status, verdict
            ("2026-10-01", "2026-11-01", "2026-11-10", None,         False, "source",     40,  "live",  "working"),
            ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-04", False, "source",     3,   "ended", "not_working"),
            ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-08", False, "source",     7,   "ended", "not_working"),
            ("2026-11-01", "2026-11-01", "2026-11-10", "2026-11-09", False, "source",     8,   "ended", "undecided"),
            ("2026-04-01", "2026-11-01", "2026-11-10", "2026-10-18", False, "source",     200, "ended", "working"),
            ("2026-10-11", "2026-11-01", "2026-11-10", None,         False, "source",     30,  "live",  "working"),
            ("2026-11-01", "2026-11-01", "2026-11-10", None,         False, "source",     9,   "live",  "undecided"),
            (None,         "2026-11-01", "2026-11-10", "2026-11-04", False, "first_seen", 3,   "ended", "undecided"),
            (None,         "2026-11-01", "2026-11-10", "2026-11-04", True,  "first_seen", 3,   "ended", "not_working"),
            (None,         "2026-10-01", "2026-11-10", None,         False, "first_seen", 40,  "live",  "working")]

        def at(day):
            return None if day is None else f"{day}T00:00:00Z"
        for i, (started, first, last, ended, appeared, *_) in enumerate(cases):
            self.ad(f"a{i}", started_at=at(started), first_seen_at=at(first), last_seen_at=at(last), ended_at=at(ended))
            if appeared:
                self.change(f"a{i}", None, None, None, "2026-11-01T00:00:00Z", table="ads", change="appeared",
                            source="fake", kind="ad")
        got = self.running("start_basis", "days_live", "status", "verdict")
        for i, (*_, basis, days, status, verdict) in enumerate(cases):
            self.assertEqual(got[f"a{i}"], (basis, days, status, verdict), f"case {i}")

    def test_started_is_source_date_else_first_seen(self):
        self.ad("s", started_at="2026-10-01T00:00:00Z", first_seen_at="2026-11-01T00:00:00Z")
        self.ad("f", first_seen_at="2026-11-01T00:00:00Z")
        rows = self.running("started")
        self.assertEqual(rows["s"][0].astimezone(timezone.utc).isoformat(), "2026-10-01T00:00:00+00:00")
        self.assertEqual(rows["f"][0].astimezone(timezone.utc).isoformat(), "2026-11-01T00:00:00+00:00")

    def test_angle_columns(self):
        self.ad("lab", headline="Save 20%")
        self.ad("raw", headline="Hello")
        self.ad("empty", headline="  ", body=None)
        self.ad("blank", headline=None, body="\n\t ")
        self.conn.execute(
            "INSERT INTO ad_angles (source, brand, kind, key, angle_offer, angle_message, angle_voice, text_sha256, "
            "list_version, labeled_by, labeled_at) VALUES ('fake', 'b', 'ad', 'lab', 'discount', 'convenience', 'brand', "
            "'h', 1, 't', now())")
        self.conn.commit()
        got = self.running("angle_offer", "angle_message", "angle_voice", "angle_state")
        self.assertEqual(got["lab"], ("discount", "convenience", "brand", "labeled"))
        self.assertEqual(got["raw"], (None, None, None, "not_labeled"))
        self.assertEqual(got["empty"], (None, None, None, "no_text"))
        self.assertEqual(got["blank"], (None, None, None, "no_text"))

    def test_running_has_one_row_per_ad_and_the_spec_columns(self):
        self.ad("one")
        self.ad("two")
        self.conn.execute(
            "INSERT INTO ad_angles (source, brand, kind, key, angle_offer, angle_message, angle_voice, text_sha256, "
            "list_version, labeled_by, labeled_at) VALUES ('fake', 'b', 'ad', 'one', 'none', 'none', 'brand', 'h', 1, 't', now())")
        self.conn.commit()
        self.assertEqual(len(self.running("status")), 2)
        self.assertEqual(self._query("SELECT count(*) AS n FROM radar_running")[0]["n"], 2)
        self.assertEqual(self.columns("radar_running"), [
            "source", "brand", "channel", "kind", "key", "url", "fetched_at", "format", "headline", "body", "cta",
            "landing_url", "landing_domain", "offer_code", "variation_count", "destination", "subject_type", "subject",
            "started", "start_basis", "ended_at", "status", "days_live", "verdict",
            "angle_offer", "angle_message", "angle_voice", "angle_state"])

    def response(self, key=None):
        sql = "SELECT * FROM radar_response" + (" WHERE key = %s" if key else "") + " ORDER BY key, metric"
        return {(r["key"], r["metric"]): r for r in self._query(sql, (key,) if key else ())}

    def test_response_rows(self):
        self.post("p1", views=100, likes=5, comments=0, shares=None, saves=2, creator_followers=50,
                  creator_is_brand=False, caption="hi")
        self.post("p2", views=10, creator_followers=50)
        self.post("p3", views=10, creator_followers=0)
        self.post("p4", views=10, creator_followers=None)
        self.product("pr1", rank=2, rating=Decimal("4.5"), review_count=10, sold_count=None, title="Shampoo")
        self.product("pr2", source="tiktok_shop", kind="search_result", rank=1, retailer="tiktok_shop")
        self.product("pr3", source="brand_site_and_emails", rank=1, rating=4, retailer="brand")
        self.product("pr4", source="tiktok_shop", rank=1, retailer="tiktok_shop")
        self.ranking("sr1", keyword="k w", domain="d.com", position=3)
        rows = self.response()

        self.assertEqual(sorted(m for (k, m) in rows if k == "p1"), ["comments", "likes", "saves", "views"])
        for metric in ("views", "likes", "comments", "saves"):
            r = rows[("p1", metric)]
            self.assertEqual((r["nature"], r["place"], r["by_brand"], r["better"], r["label"]),
                             ("post", "tiktok", False, "higher", "hi"))
        views = rows[("p1", "views")]
        self.assertEqual((views["baseline"], views["baseline_value"], views["ratio"], views["verdict"]),
                         ("followers", 50, 2, "working"))
        self.assertEqual(views["value"], 100)
        for metric in ("likes", "comments", "saves"):
            r = rows[("p1", metric)]
            self.assertEqual((r["baseline"], r["baseline_value"], r["ratio"], r["verdict"]), (None, None, None, None))

        low = rows[("p2", "views")]
        self.assertEqual(low["ratio"], Decimal("0.2"))
        self.assertEqual((low["baseline"], low["baseline_value"], low["verdict"]), ("followers", 50, None))
        for key in ("p3", "p4"):
            r = rows[(key, "views")]
            self.assertEqual((r["baseline"], r["baseline_value"], r["ratio"], r["verdict"]), (None, None, None, None))

        self.assertEqual(sorted(m for (k, m) in rows if k == "pr1"), ["rank", "rating", "review_count"])
        for metric, better in (("rank", "lower"), ("rating", "higher"), ("review_count", "higher")):
            r = rows[("pr1", metric)]
            self.assertEqual((r["nature"], r["place"], r["label"], r["by_brand"], r["better"]),
                             ("product", "amazon", "Shampoo", None, better))
            self.assertEqual((r["baseline"], r["ratio"], r["verdict"]), (None, None, None))
        self.assertEqual(rows[("pr1", "rating")]["value"], Decimal("4.5"))
        self.assertEqual([k for (k, m) in rows if k == "pr2"], [])
        self.assertEqual([k for (k, m) in rows if k == "pr3"], [])
        self.assertEqual(sorted(m for (k, m) in rows if k == "pr4"), ["rank"])

        r = rows[("sr1", "position")]
        self.assertEqual((r["nature"], r["place"], r["label"], r["metric"], r["value"], r["better"], r["by_brand"]),
                         ("search_result", "google", "k w -> d.com", "position", 3, "lower", None))
        self.assertEqual(sorted(k for (k, m) in rows), sorted(
            ["p1"] * 4 + ["p2", "p3", "p4"] + ["pr1"] * 3 + ["pr4", "sr1"]))
        self.assertEqual(self.columns("radar_response"), [
            "source", "brand", "key", "url", "fetched_at", "first_seen_at", "last_seen_at", "ended_at", "nature", "place",
            "label", "by_brand", "metric", "value", "better", "baseline", "baseline_value", "ratio",
            "previous_value", "moved", "moved_at", "verdict"])

    def test_response_last_move(self):
        self.product("pr1", rank=2, rating=Decimal("4.5"), title="Shampoo")
        self.change("pr1", "rank", "5", "4", "2026-11-02T00:00:00Z")
        self.change("pr1", "rank", "4", "2", "2026-11-03T00:00:00Z")
        self.change("pr1", "price", "9", "8", "2026-11-04T00:00:00Z")
        self.change("pr1", "rank", "2", None, "2026-11-05T00:00:00Z", change="ended")
        rows = self.response("pr1")
        rank = rows[("pr1", "rank")]
        self.assertEqual((rank["previous_value"], rank["moved"]), (4, -2))
        self.assertEqual(rank["moved_at"].astimezone(timezone.utc).isoformat(), "2026-11-03T00:00:00+00:00")
        rating = rows[("pr1", "rating")]
        self.assertEqual((rating["previous_value"], rating["moved"], rating["moved_at"]), (None, None, None))

    def test_response_last_move_ties_take_the_greatest_id(self):
        self.product("pr1", rank=2)
        self.change("pr1", "rank", "9", "7", "2026-11-03T00:00:00Z")
        self.change("pr1", "rank", "4", "2", "2026-11-03T00:00:00Z")
        self.assertEqual(self.response("pr1")[("pr1", "rank")]["previous_value"], 4)

    def test_ended_item_keeps_its_rows(self):
        self.product("pr1", rank=2, ended_at="2026-11-09T00:00:00Z")
        r = self.response("pr1")[("pr1", "rank")]
        self.assertEqual(r["ended_at"].astimezone(timezone.utc).isoformat(), "2026-11-09T00:00:00+00:00")

    def test_views_survive_ensure_schema_again(self):
        import db
        self.ad("a")
        db.ensure_schema(self.conn)
        self.assertEqual(len(self.running("status")), 1)
        self.assertEqual(self._query("SELECT count(*) AS n FROM radar_angles")[0]["n"], 0)
        self.assertEqual(self._query("SELECT count(*) AS n FROM radar_response")[0]["n"], 0)


class RadarAnglesTest(RadarViewsBase):
    URL = "https://www.livingproof.com/products/mist"

    def label(self, key, offer, message, voice, brand="b"):
        self.conn.execute(
            "INSERT INTO ad_angles (source, brand, kind, key, angle_offer, angle_message, angle_voice, text_sha256, "
            "list_version, labeled_by, labeled_at) VALUES ('fake', %s, 'ad', %s, %s, %s, %s, 'h', 1, 't', now())",
            (brand, key, offer, message, voice))
        self.conn.commit()

    def angles(self, where):
        return {(r["angle_kind"], r["angle"]): r for r in self._query(f"SELECT * FROM radar_angles WHERE {where}")}

    def numbers(self, r):
        return (r["ads"], r["live"], r["started_last_7d"], r["oldest_days_live"], r["working"], r["not_working"])

    def test_groups_and_counts(self):
        # the latest look is 2026-11-10 (greatest last_seen_at over all ads)
        self.ad("1", headline="one", landing_url=self.URL, landing_domain="livingproof.com", started_at="2026-11-08T00:00:00Z")
        self.ad("2", headline="two", landing_url=self.URL, landing_domain="livingproof.com", started_at="2026-10-01T00:00:00Z")
        self.ad("3", headline="three", landing_url=self.URL, landing_domain="livingproof.com",
                started_at="2026-10-21T00:00:00Z", ended_at="2026-10-24T00:00:00Z")
        self.ad("4", headline="four", landing_url=self.URL, landing_domain="livingproof.com", started_at="2026-10-31T00:00:00Z")
        self.ad("5", headline="not labeled", landing_url=self.URL, landing_domain="livingproof.com", started_at="2026-11-09T00:00:00Z")
        self.ad("6", headline="other brand", brand="c", landing_url=self.URL, landing_domain="livingproof.com",
                started_at="2026-11-09T00:00:00Z")
        self.label("1", "discount", "benefit", "brand")
        self.label("2", "none", "benefit", "creator")
        self.label("3", "none", "ingredient", "brand")
        self.label("4", "discount", "none", "brand")
        self.label("6", "discount", "benefit", "brand", brand="c")
        rows = self.angles("brand = 'b' AND subject = 'mist'")
        self.assertEqual(sorted(rows), [("message", "benefit"), ("message", "ingredient"), ("offer", "discount"),
                                        ("voice", "brand"), ("voice", "creator")])
        self.assertEqual(self.numbers(rows[("message", "benefit")]), (2, 2, 1, 40, 1, 0))
        self.assertEqual(self.numbers(rows[("voice", "brand")]), (3, 2, 1, 10, 0, 1))
        self.assertEqual(self.numbers(rows[("message", "ingredient")]), (1, 0, 0, 3, 0, 1))
        self.assertEqual(self.numbers(rows[("voice", "creator")]), (1, 1, 0, 40, 1, 0))
        self.assertEqual(rows[("offer", "discount")]["ads"], 2)
        self.assertEqual({(r["subject_type"], r["subject"]) for r in rows.values()}, {("product", "mist")})
        other = self.angles("brand = 'c'")
        self.assertEqual(sorted(other), [("message", "benefit"), ("offer", "discount"), ("voice", "brand")])
        self.assertEqual(other[("offer", "discount")]["ads"], 1)

    def test_ads_without_a_subject_group_under_null(self):
        self.ad("1", headline="one")
        self.ad("2", headline="two")
        self.label("1", "none", "convenience", "brand")
        self.label("2", "none", "convenience", "creator")
        rows = self._query("SELECT * FROM radar_angles WHERE brand = 'b' AND angle_kind = 'message'")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["subject_type"], r["subject"], r["angle"], r["ads"]), (None, None, "convenience", 2))

    def test_columns(self):
        self.assertEqual(self.columns("radar_angles"), [
            "brand", "subject_type", "subject", "angle_kind", "angle", "ads", "live", "started_last_7d",
            "oldest_days_live", "working", "not_working"])


if __name__ == "__main__":
    unittest.main()
