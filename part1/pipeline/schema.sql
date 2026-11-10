CREATE TABLE IF NOT EXISTS ads (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  channel text NOT NULL,
  advertiser_id text,
  advertiser_name text,
  format text,
  headline text,
  body text,
  cta text,
  landing_url text,
  landing_domain text,
  started_at timestamptz,
  last_shown_at timestamptz,
  variation_count integer,
  placements text[],
  offer_code text,
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS products (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  retailer text NOT NULL,
  product_id text,
  title text,
  price numeric(12,2),
  price_max numeric(12,2),
  list_price numeric(12,2),
  currency text,
  rating numeric(3,2),
  review_count integer,
  rank integer,
  sponsored boolean,
  availability text,
  seller_name text,
  sold_count bigint,
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS reviews (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  product_key text NOT NULL,
  rating numeric(3,2),
  title text,
  body text,
  review_date date,
  verified boolean,
  helpful_votes integer,
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS search_rankings (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  keyword text NOT NULL,
  keyword_rank integer,
  position integer,
  result_url text,
  domain text,
  title text,
  description text,
  result_type text,
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS search_interest (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  keyword text NOT NULL,
  series text NOT NULL,
  week_start date NOT NULL,
  value integer,
  has_data boolean,
  is_partial boolean,
  geo text,
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS posts (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  scope text NOT NULL,
  url text,
  fetched_at timestamptz NOT NULL,
  first_seen_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL,
  ended_at timestamptz,
  last_run_id text NOT NULL,
  raw jsonb NOT NULL,
  post_id text,
  posted_at timestamptz,
  creator_handle text,
  creator_is_brand boolean,
  creator_followers bigint,
  views bigint,
  likes bigint,
  comments bigint,
  shares bigint,
  saves bigint,
  caption text,
  hashtags text[],
  surfaced_by text[],
  PRIMARY KEY (source, brand, kind, key)
);

CREATE TABLE IF NOT EXISTS runs (
  source text,
  brand text,
  run_id text,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  status text NOT NULL,
  reason text NOT NULL,
  records integer,
  expected_total integer,
  requests integer,
  cost_usd numeric(10,4),
  extra jsonb,
  result text NOT NULL,
  loaded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, brand, run_id)
);

CREATE TABLE IF NOT EXISTS run_scopes (
  source text,
  brand text,
  run_id text,
  scope text,
  status text NOT NULL,
  reason text NOT NULL,
  PRIMARY KEY (source, brand, run_id, scope)
);

CREATE TABLE IF NOT EXISTS changes (
  id bigserial PRIMARY KEY,
  changed_at timestamptz NOT NULL,
  run_id text NOT NULL,
  source text NOT NULL,
  brand text NOT NULL,
  table_name text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  change text NOT NULL CHECK (change IN ('appeared', 'ended', 'reappeared', 'changed')),
  field text,
  old_value text,
  new_value text
);
CREATE INDEX IF NOT EXISTS changes_item ON changes (source, brand, table_name, kind, key, field, changed_at);
CREATE INDEX IF NOT EXISTS changes_changed_at ON changes (changed_at);

CREATE TABLE IF NOT EXISTS ad_angles (
  source text NOT NULL,
  brand text NOT NULL,
  kind text NOT NULL,
  key text NOT NULL,
  angle_offer text NOT NULL,
  offer_evidence text,
  angle_message text NOT NULL,
  message_evidence text,
  angle_voice text NOT NULL,
  voice_evidence text,
  text_sha256 text NOT NULL,
  list_version integer NOT NULL,
  labeled_by text NOT NULL,
  labeled_at timestamptz NOT NULL,
  PRIMARY KEY (source, brand, kind, key)
);

-- Agent views. Dropped and created again on every ensure_schema, so the definitions in this file always win.
DROP VIEW IF EXISTS radar_angles;
DROP VIEW IF EXISTS radar_response;
DROP VIEW IF EXISTS radar_running;

-- One row per ad: how long it ran, a verdict, what it sells, where it sends people, its angles.
CREATE VIEW radar_running AS
WITH brand_domains(domain) AS (
  VALUES ('batistehair.com'), ('livingproof.com'), ('deathwishcoffee.com'), ('blackriflecoffee.com'), ('thinkjinx.com')
), retailer_domains(domain) AS (
  VALUES ('amazon.com'), ('ulta.com'), ('target.com'), ('sephora.com'), ('walmart.com'), ('chewy.com'),
         ('cvs.com'), ('walgreens.com'), ('kroger.com'), ('petco.com'), ('petsmart.com')
), destination AS (
  SELECT a.*,
         CASE
           WHEN a.landing_domain IS NULL THEN NULL
           WHEN EXISTS (SELECT 1 FROM brand_domains d
                        WHERE a.landing_domain = d.domain OR a.landing_domain LIKE '%.' || d.domain) THEN 'brand_site'
           WHEN EXISTS (SELECT 1 FROM retailer_domains d
                        WHERE a.landing_domain = d.domain OR a.landing_domain LIKE '%.' || d.domain) THEN 'retailer'
           ELSE 'other'
         END AS destination,
         -- landing_url without scheme, host, query, fragment and trailing slashes
         regexp_replace(regexp_replace(regexp_replace(a.landing_url, '^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*', ''),
                                       '[?#].*$', ''), '/+$', '') AS path
  FROM ads a
), subject AS (
  SELECT d.*,
         CASE
           WHEN d.landing_url IS NULL OR d.destination IS NULL THEN NULL
           WHEN d.destination = 'retailer' THEN 'retailer_product'
           WHEN d.destination = 'other' THEN 'other'
           WHEN d.path ~ '/products/[^/]+' THEN 'product'
           WHEN d.path ~ '^/collections/[^/]+' THEN 'collection'
           WHEN d.path = '' THEN 'home'
           ELSE 'page'
         END AS subject_type,
         CASE
           WHEN d.landing_url IS NULL OR d.destination IS NULL THEN NULL
           WHEN d.destination IN ('retailer', 'other') THEN d.landing_domain || d.path
           WHEN d.path ~ '/products/[^/]+' THEN substring(d.path from '/products/([^/]+)')
           WHEN d.path ~ '^/collections/[^/]+' THEN 'collections/' || substring(d.path from '^/collections/([^/]+)')
           WHEN d.path = '' THEN 'home'
           ELSE ltrim(d.path, '/')
         END AS subject
  FROM destination d
), lifetime AS (
  SELECT s.*,
         COALESCE(s.started_at, s.first_seen_at) AS started,
         CASE WHEN s.started_at IS NOT NULL THEN 'source' ELSE 'first_seen' END AS start_basis,
         CASE WHEN s.ended_at IS NULL THEN 'live' ELSE 'ended' END AS status,
         floor(extract(epoch FROM COALESCE(s.ended_at, s.last_seen_at) - COALESCE(s.started_at, s.first_seen_at)) / 86400)::integer
           AS days_live,
         EXISTS (SELECT 1 FROM changes c
                 WHERE c.table_name = 'ads' AND c.change = 'appeared'
                   AND c.source = s.source AND c.brand = s.brand AND c.kind = s.kind AND c.key = s.key) AS has_appeared
  FROM subject s
), verdict AS (
  SELECT l.*,
         CASE
           WHEN l.ended_at IS NOT NULL AND l.days_live <= 7 AND (l.start_basis = 'source' OR l.has_appeared) THEN 'not_working'
           WHEN l.days_live >= 30 THEN 'working'
           ELSE 'undecided'
         END AS verdict,
         CASE
           WHEN COALESCE(l.headline, '') ~ '^\s*$' AND COALESCE(l.body, '') ~ '^\s*$' THEN 'no_text'
           WHEN g.key IS NOT NULL THEN 'labeled'
           ELSE 'not_labeled'
         END AS angle_state,
         g.angle_offer, g.angle_message, g.angle_voice
  FROM lifetime l
  LEFT JOIN ad_angles g ON g.source = l.source AND g.brand = l.brand AND g.kind = l.kind AND g.key = l.key
)
SELECT source, brand, channel, kind, key, url, fetched_at,
       format, headline, body, cta, landing_url, landing_domain, offer_code, variation_count,
       destination, subject_type, subject,
       started, start_basis, ended_at, status, days_live, verdict,
       CASE WHEN angle_state = 'labeled' THEN angle_offer END AS angle_offer,
       CASE WHEN angle_state = 'labeled' THEN angle_message END AS angle_message,
       CASE WHEN angle_state = 'labeled' THEN angle_voice END AS angle_voice,
       angle_state
FROM verdict;

-- One row per published number of a post, product or search result, with its last move.
CREATE VIEW radar_response AS
WITH numbers AS (
  SELECT p.source, p.brand, p.kind, p.key, p.url, p.fetched_at, p.first_seen_at, p.last_seen_at, p.ended_at,
         'posts' AS table_name, 'post' AS nature, 'tiktok' AS place, p.caption AS label, p.creator_is_brand AS by_brand,
         m.metric, m.value, 'higher' AS better, p.creator_followers
  FROM posts p
  CROSS JOIN LATERAL (VALUES ('views', p.views::numeric), ('likes', p.likes::numeric), ('comments', p.comments::numeric),
                             ('shares', p.shares::numeric), ('saves', p.saves::numeric)) AS m(metric, value)
  UNION ALL
  SELECT p.source, p.brand, p.kind, p.key, p.url, p.fetched_at, p.first_seen_at, p.last_seen_at, p.ended_at,
         'products', 'product', p.retailer, p.title, NULL::boolean,
         m.metric, m.value, m.better, NULL::bigint
  FROM products p
  CROSS JOIN LATERAL (VALUES ('rank', p.rank::numeric, 'lower'), ('rating', p.rating::numeric, 'higher'),
                             ('review_count', p.review_count::numeric, 'higher'),
                             ('sold_count', p.sold_count::numeric, 'higher')) AS m(metric, value, better)
  WHERE p.kind = 'product' AND p.source IN ('amazon', 'retail_shelf', 'tiktok_shop')
  UNION ALL
  SELECT r.source, r.brand, r.kind, r.key, r.url, r.fetched_at, r.first_seen_at, r.last_seen_at, r.ended_at,
         'search_rankings', 'search_result', 'google', r.keyword || ' -> ' || r.domain, NULL::boolean,
         'position', r.position::numeric, 'lower', NULL::bigint
  FROM search_rankings r
), published AS (
  SELECT * FROM numbers WHERE value IS NOT NULL
), baseline AS (
  SELECT n.*,
         CASE WHEN n.nature = 'post' AND n.metric = 'views' AND n.creator_followers > 0 THEN 'followers' END AS baseline,
         CASE WHEN n.nature = 'post' AND n.metric = 'views' AND n.creator_followers > 0 THEN n.creator_followers END AS baseline_value,
         CASE WHEN n.nature = 'post' AND n.metric = 'views' AND n.creator_followers > 0
              THEN n.value / n.creator_followers END AS ratio
  FROM published n
)
SELECT b.source, b.brand, b.key, b.url, b.fetched_at, b.first_seen_at, b.last_seen_at, b.ended_at,
       b.nature, b.place, b.label, b.by_brand, b.metric, b.value, b.better,
       b.baseline, b.baseline_value, b.ratio,
       c.old_value::numeric AS previous_value,
       b.value - c.old_value::numeric AS moved,
       c.changed_at AS moved_at,
       CASE WHEN b.ratio >= 1 THEN 'working' END AS verdict
FROM baseline b
LEFT JOIN LATERAL (
  SELECT x.old_value, x.changed_at
  FROM changes x
  WHERE x.table_name = b.table_name AND x.change = 'changed' AND x.field = b.metric
    AND x.source = b.source AND x.brand = b.brand AND x.kind = b.kind AND x.key = b.key
  ORDER BY x.changed_at DESC, x.id DESC
  LIMIT 1
) c ON true;

-- Angles of labeled ads, one row per kind and value (the value none is left out), grouped by brand and what is sold.
CREATE VIEW radar_angles AS
WITH latest AS (
  SELECT max(last_seen_at) AS at FROM ads
), angles AS (
  SELECT r.brand, r.subject_type, r.subject, r.started, r.status, r.days_live, r.verdict, a.angle_kind, a.angle
  FROM radar_running r
  CROSS JOIN LATERAL (VALUES ('offer', r.angle_offer), ('message', r.angle_message), ('voice', r.angle_voice))
              AS a(angle_kind, angle)
  WHERE r.angle_state = 'labeled' AND a.angle IS NOT NULL AND a.angle <> 'none'
)
SELECT g.brand, g.subject_type, g.subject, g.angle_kind, g.angle,
       count(*)::int AS ads,
       (count(*) FILTER (WHERE g.status = 'live'))::int AS live,
       (count(*) FILTER (WHERE g.started >= l.at - interval '7 days'))::int AS started_last_7d,
       max(g.days_live)::int AS oldest_days_live,
       (count(*) FILTER (WHERE g.verdict = 'working'))::int AS working,
       (count(*) FILTER (WHERE g.verdict = 'not_working'))::int AS not_working
FROM angles g
CROSS JOIN latest l
GROUP BY g.brand, g.subject_type, g.subject, g.angle_kind, g.angle;
