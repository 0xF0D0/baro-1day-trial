from dataclasses import dataclass

COMMON_COLUMNS = ("source", "brand", "kind", "key", "scope", "url", "fetched_at",
                  "first_seen_at", "last_seen_at", "ended_at", "last_run_id", "raw")
TABLE_COLUMNS = {
    "ads": ("channel", "advertiser_id", "advertiser_name", "format", "headline", "body", "cta",
            "landing_url", "landing_domain", "started_at", "last_shown_at", "variation_count",
            "placements", "offer_code"),
    "products": ("retailer", "product_id", "title", "price", "price_max", "list_price", "currency",
                 "rating", "review_count", "rank", "sponsored", "availability", "seller_name", "sold_count"),
    "reviews": ("product_key", "rating", "title", "body", "review_date", "verified", "helpful_votes"),
    "search_rankings": ("keyword", "keyword_rank", "position", "result_url", "domain", "title",
                        "description", "result_type"),
    "search_interest": ("keyword", "series", "week_start", "value", "has_data", "is_partial", "geo"),
    "posts": ("post_id", "posted_at", "creator_handle", "creator_is_brand", "creator_followers",
              "views", "likes", "comments", "shares", "saves", "caption", "hashtags", "surfaced_by"),
}


@dataclass(frozen=True)
class Row:
    table: str                  # a key of TABLE_COLUMNS
    kind: str
    key: str
    scope: str
    url: str | None
    fetched_at: str             # ISO 8601 UTC, the record's fetched_at
    raw: dict
    columns: dict[str, object]  # own columns; a name left out keeps the stored value


@dataclass(frozen=True)
class Scope:
    name: str
    status: str                 # ok | partial | could_not_look
    reason: str


@dataclass(frozen=True)
class MappedRun:
    rows: list[Row]
    scopes: list[Scope]
    not_fetched: int = 0        # records that said their item was not fetched


class MapError(Exception):      # message starts with the record key
    pass
