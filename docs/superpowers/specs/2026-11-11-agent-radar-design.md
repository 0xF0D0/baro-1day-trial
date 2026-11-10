# Market Radar: what the agents read

Date: 2026-11-11. Builds on `2026-11-10-market-radar-tables-design.md` (the "tables design"), which stays in force.

## 1. Intent

The radar exists to tell a brand which angles and strategies work for its competitors right now, and which do not.
It is fed constantly, and it is one of the inputs that agents read (with people reviewing).

The tables design gave us six tables that hold what each source shows, with `first_seen_at`, `last_seen_at` and
`ended_at` per row. That answers "what are competitors doing". It does not yet answer "is it working", "what changed",
or "which angle".

None of the sources publishes results, so "working" has to be read from two kinds of evidence:

| Evidence | Measured by | Applies to |
|---|---|---|
| The competitor keeps doing it | how long it stays up | ads, home-page offers, signup forms, emails: things a competitor pays for or gives space to |
| The public responded | published numbers and how they move | posts (views), products (rank, reviews, units sold), search results (position) |

Both need time, so the first thing added is a record of what changed and when.

## 2. What gets built

Four things on top of the six tables. The six tables, the mappers and the collectors do not change.

| Name | Kind | One row is |
|---|---|---|
| `changes` | table, written by the loader, append-only | one change to one item, seen at one run |
| `angles` | table, filled from a labels file | one angle of one ad |
| `radar_running` | view over `ads` (+ `changes`, `angles`) | one ad or owned-channel message, with how long it has run and a verdict |
| `radar_response` | view over `posts`, `products`, `search_rankings` (+ `changes`) | one published number of one item, with its last move |

"Competitors" are all five brands. There is no table that says who competes with whom.

## 3. `changes`

### 3.1 Table

| Column | Type | Meaning |
|---|---|---|
| `id` | bigserial, primary key | |
| `changed_at` | timestamptz, not null | the `started_at` of the run that showed the change |
| `run_id` | text, not null | that run |
| `source`, `brand`, `table_name`, `kind`, `key` | text, not null | the item; `table_name` is one of the six tables |
| `change` | text, not null | `appeared`, `ended`, `reappeared` or `changed` |
| `field` | text | the column that changed; only for `changed` |
| `old_value`, `new_value` | text | only for `changed`; either may be NULL when the value was or became NULL |

Indexes: `(source, brand, table_name, kind, key, field, changed_at)` and `(changed_at)`.

### 3.2 When a row is written

The loader writes these rows in the same transaction as the run. A run that is not applied (`superseded`, `failed`,
`already_loaded`, `no_mapper`, `empty_no_mapper`) writes none. Loading the same files into an empty database again gives
the same rows.

| `change` | Written when |
|---|---|
| `appeared` | a row is inserted with `ended_at` NULL, and an earlier complete look at its scope exists (below) |
| `ended` | a row that had `ended_at` NULL gets an `ended_at`, by either ending policy |
| `reappeared` | a row that had an `ended_at` is seen again and reopened |
| `changed` | a row that already existed is seen again and a tracked column in the mapper's row differs from the stored value; one `changes` row per column |

An earlier complete look exists when `run_scopes` has a row with the same `source`, `brand` and scope name, status
`ok` as stored (after the loader's downgrade of a crashed run), for a run with `result` `applied` and a smaller
`run_id`. Covering scopes are not consulted: `run_scopes` does not store what a scope covers.

Why `appeared` needs an earlier complete look: on the first load every row is new to us, and after a "could not look"
or a partial look a row may simply not have been read before. Calling those "appeared" would report launches that did
not happen. This mirrors the ending rule (only a complete look may end a row).

A row inserted already ended (an old Google ad) writes nothing: we never saw it running. The same holds for the
source-date policy as for absence: an open Google ad whose last-shown date falls behind writes `ended`, with
`changed_at` the run's `started_at` (the date it stopped is the item's `ended_at`); an ended one that only gets a
newer end date writes nothing; an ended one shown again recently is reopened and writes `reappeared`.

A column the mapper leaves out of a row is not compared, as it is not updated either.

### 3.3 Tracked columns

| Table | Columns |
|---|---|
| `ads` | `headline`, `body`, `cta`, `landing_domain`, `offer_code`, `variation_count` |
| `products` | `price`, `price_max`, `list_price`, `availability`, `rank`, `rating`, `review_count`, `sold_count`, `sponsored` |
| `search_rankings` | `position` |
| `posts` | `views`, `likes`, `comments`, `shares`, `saves`, `creator_followers` |
| `reviews`, `search_interest` | none |

Values are compared in the column's type, so `12.990` and `12.99` are not a change. `old_value` and `new_value` hold
plain text: numbers in decimal notation without an exponent and without trailing zeros after the point (`12.99`,
`30000000`, `4.5`), booleans as `true` / `false`, text as is.

## 4. `radar_running`

A view with one row per row of `ads`.

| Column | Meaning |
|---|---|
| `source`, `brand`, `channel`, `kind`, `key`, `url`, `fetched_at` | from `ads` |
| `format`, `headline`, `body`, `cta`, `landing_domain`, `offer_code`, `variation_count` | from `ads` |
| `destination` | `brand_site`, `retailer`, `other`, or NULL when there is no `landing_domain` (4.1) |
| `started` | `started_at` when the source gives one, else `first_seen_at` |
| `start_basis` | `source` or `first_seen` |
| `ended_at` | from `ads` |
| `status` | `live` when `ended_at` is NULL, else `ended` |
| `days_live` | whole days from `started` to `ended_at`, or to `last_seen_at` while live |
| `verdict` | `working`, `not_working` or `undecided` (4.2) |
| `angles` | the ad's angles as a sorted text array, NULL when none |
| `angle_state` | `labeled`, `not_labeled` or `no_text` (5.4) |

`days_live` counts to `last_seen_at`, not to the current time, so an ad is not credited with days on which nobody looked.
With `start_basis` `first_seen` it is a lower bound: the ad may be older than our first look.

### 4.1 `destination`

- `brand_site` when `landing_domain` is the brand's own domain or a subdomain of it: `batistehair.com`,
  `livingproof.com`, `deathwishcoffee.com`, `blackriflecoffee.com`, `thinkjinx.com`.
- `retailer` when it is, or is a subdomain of, one of: `amazon.com`, `ulta.com`, `target.com`, `sephora.com`,
  `walmart.com`, `chewy.com`, `cvs.com`, `walgreens.com`, `kroger.com`, `petco.com`, `petsmart.com`.
- `other` for any other domain.

Both lists live in `schema.sql` next to the view.

### 4.2 `verdict`

| Verdict | Rule |
|---|---|
| `not_working` | ended, `days_live` at most 7, and the start is known: `start_basis` is `source`, or `changes` has an `appeared` row for the ad |
| `working` | not the above, and `days_live` at least 30 |
| `undecided` | everything else |

The verdict uses time only. `variation_count` is shown but does not decide: an ad launched yesterday with three
variations is being tested, not proven. An ad that ran 200 days and then ended is `working` with `status` `ended`;
filter on `status` for what runs now.

`not_working` needs a known start because an ad we first saw on its hundredth day and that ended three days later did
not fail fast.

## 5. `angles`

An angle is a reading of an ad's words, not something a source publishes. It is kept apart from the collected columns,
with the words it was read from.

### 5.1 The list (version 1)

| Angle | The ad's words are about |
|---|---|
| `offer` | a discount, a free item, a code, a bundle price |
| `gifting_season` | a holiday, a season, giving it as a gift |
| `convenience` | saving time or effort, skipping a step |
| `performance` | what the product does, with or without numbers (hours, degrees, strength) |
| `science` | an ingredient, a technology, a formula, a patent |
| `social_proof` | units sold, awards, "No. 1", a professional's recommendation |
| `creator_voice` | a creator or partner speaking in first person |
| `new_limited` | a new product, a limited edition, a new scent or flavour |
| `where_to_buy` | a named retailer, an exclusive at a retailer |
| `range_guide` | several products for different needs, where to start |
| `urgency` | the offer or stock ending soon |
| `identity` | who the brand is or stands for |
| `other` | none of the above |

An ad may have several angles. A labeled ad has at least one.

### 5.2 Labels file

`part1/pipeline/labels/ad_angles.jsonl`, committed. One line per distinct ad text:

```json
{"text_sha256": "<64 hex>", "list_version": 1, "labeled_by": "<who or what read it>", "labeled_at": "<UTC time>",
 "angles": [{"angle": "offer", "evidence": "Save 20%"}, {"angle": "gifting_season", "evidence": "last-minute gift-givers"}]}
```

- The ad text is `headline` and `body`, each with runs of whitespace turned into one space and trimmed, joined by one
  newline; a missing one counts as empty. When both are empty the ad has no text.
- `text_sha256` is the SHA-256 of that text in UTF-8.
- `evidence` is a phrase of at most 12 words copied from that text. It must occur in the text, and it must not
  contain an `@` handle.
- The file does not hold the ad text itself. Some ads are a creator's words run by the brand, and the repository is public.

Who writes the lines is outside the code: a model or a person reads the pending texts and adds lines. For this delivery
the plan has a labeling task done by the main session, not by an implementer subagent, since no model API key is part
of Part 1: it reads the output of `--pending` (5.3) and writes a line for every pending text, with `labeled_by`
`claude-fable-5-2 (in session)`. The work is done when no text is pending.

### 5.3 Table and loading

`angles`: `source`, `brand`, `kind`, `key`, `angle`, `evidence`, `text_sha256`, `list_version`, `labeled_by`,
`labeled_at`; primary key `(source, brand, kind, key, angle)`.

After its runs, `load.py` rebuilds `angles` from the file: for every `ads` row with text, the rows for the text's hash.
It fails, naming the line, when a line has an angle outside the list, no angles, a duplicate hash, or an `evidence` that
does not occur in the text of an ad with that hash. Evidence is checked against every ad that has the hash. A hash that
matches no ad is not an error (the ad may be in another database).

`load.py` prints one more line before its `runs:` line: `angles: labeled=<ads> not_labeled=<ads> no_text=<ads>`.

The angles step runs after the runs, in its own transaction. When the file is invalid, the runs stay loaded, `angles`
is left as it was, the line is `angles: failed: line <n>: <reason>`, the `runs:` line is still printed, and the exit
code is 1. A missing file is an empty file.

`python part1/pipeline/angles.py --pending` writes the distinct texts that have no line yet to standard output, one
JSON object per line with `text_sha256`, `text`, `brands`, `channels` and `ads` (how many ads use it). That output is
what the labeler reads; it is not committed.

### 5.4 `angle_state`

| State | When |
|---|---|
| `no_text` | `headline` and `body` are both empty (every Google ad: the creative is an image or a video) |
| `labeled` | `angles` has rows for the ad |
| `not_labeled` | the ad has text and no line in the file yet |

`not_labeled` is "not read yet", never "no angle".

## 6. `radar_response`

A view with one row per published number of one item.

| Column | Meaning |
|---|---|
| `source`, `brand`, `key`, `url`, `fetched_at`, `first_seen_at`, `last_seen_at`, `ended_at` | from the item's table |
| `nature` | `post`, `product` or `search_result` |
| `place` | `tiktok` for posts; `retailer` of the product; `google` for search results |
| `label` | the caption; the product title; `<keyword> -> <domain>` |
| `by_brand` | for posts, whether the brand's own account posted it; NULL otherwise |
| `metric` | the number's name (table below) |
| `value` | the number |
| `better` | `higher` or `lower` |
| `baseline`, `baseline_value`, `ratio` | for a post's `views`: `followers`, the creator's followers, views divided by followers; NULL otherwise and when followers is 0 or NULL |
| `previous_value`, `moved`, `moved_at` | from the latest `changed` row in `changes` for this item and column: the old value, `value` minus it, when; NULL when it never moved |
| `verdict` | `working` for a post's `views` row when `ratio` is at least 1; NULL otherwise |

| `nature` | From | Metrics |
|---|---|---|
| `post` | `posts` | `views`, `likes`, `comments`, `shares`, `saves` (higher) |
| `product` | `products` where `kind` is `product` and `source` is `amazon`, `retail_shelf` or `tiktok_shop` | `rank` (lower), `rating`, `review_count`, `sold_count` (higher) |
| `search_result` | `search_rankings` | `position` (lower) |

A number that is NULL gives no row. An ended item keeps its rows; filter on `ended_at` for what is there now.
Brand-site products and Batiste's retailer listings (both from source `brand_site_and_emails`) are left out: they
publish no response number. TikTok Shop's `search_result` rows are left out: they are whatever a search for the
brand's term returns, mostly other brands' products. Price is left out: it is the competitor's move, not the public's response; its changes are in `changes`.

There is no `not_working` here. Posts are collected by popularity, so the ones that went nowhere are not in the sample.
Products and search results get no verdict yet: their evidence is movement, which needs repeated runs.

## 7. Goals, non-goals, anti-goals

Goals
- An agent answers "what changed for these brands since <time>" from `changes` alone.
- An agent answers "which ads have these brands kept running, where do they send people, with which angles" from
  `radar_running` alone, and "what is getting a response" from `radar_response` alone.
- Every row leads back to its item (`source`, `brand`, `key`, `url`), so a person can check it.
- Loading stays one command and rerun-safe; loading the same files again changes nothing.

Non-goals (not in this work)
- Angles for posts; reading images or video; pulling the wording of Google ads out of their saved creative scripts.
- Verdicts for products and search results. `search_interest` in a radar view (it is already a time series).
- A scheduler, and the one command that runs collectors and then the loader.
- Calling a model API to label. The file format is what such a step would write.

Anti-goals
- A verdict or an angle presented as a collected fact. They sit in their own columns and table, with the rule or the evidence.
- "Appeared", "ended" or "not working" claimed without a complete look behind it.
- Storing the words of private individuals in the repository.

## 8. Constraints carried over

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no personal data of private individuals.
5. Local Postgres, one command, reproducible by someone else.
6. Every record keeps its source URL and fetch time.

## 9. Expected results on the current run files

With the 69 runs now on disk, loaded in order into an empty database:

| Check | Expected |
|---|---|
| `radar_running` rows | 835, one per `ads` row |
| Google ads by verdict | `working` 498, `not_working` 34, `undecided` 160 |
| Every other channel | all `undecided` (Meta 89, signup forms 34, site 14, email 3, TikTok 3) |
| `angle_state` | `no_text` 695 (692 Google, 3 site), `labeled` 140, `not_labeled` 0; the labels file has 119 lines |
| `radar_response` rows | 2,224: posts 995 (199 x 5), products 396 (rank 109, rating 120, review_count 138, sold_count 29), search 833 |
| Posts with `verdict` `working` | 95 of 199 |
| `changes` | whatever the repeated runs of sources 1, 3, 5, 7 and 10 show; the builder reports the counts by `change` and looks at ten rows by hand |
| Second load | no new rows anywhere, `changes` included |

These numbers move when new runs are added.

## 10. Calls made by the designer

1. Two radar views, split by the kind of evidence, so that "working" means one thing per view.
2. `radar_response` is long (one number per row). The item tables already hold the wide row; what the view adds is one
   shape across natures, the baseline, and the last move.
3. `appeared` only against an earlier complete look; nothing for a row first seen already ended.
4. `days_live` to `last_seen_at`, not to now.
5. Verdict by time only: 30 days for `working`, 7 for `not_working`. Variations are shown, not used.
6. `not_working` needs a known start.
7. A post is `working` when views are at least the creator's followers. Simple, and it favours small accounts; both
   numbers are in the row.
8. Price is not a response number.
9. The domain lists for `destination` are written in `schema.sql`.
10. Angle labels come from a committed file keyed by the hash of the text, with evidence that must occur in the text.
    The ad text is not committed.
11. Angles only for `ads` rows that have text. Posts are left out: their captions are private individuals' words, and
    content type is a different list.
12. The tracked columns in 3.3.
13. `load.py` applies the labels file itself, so one command still fills everything.
14. An invalid labels file fails the angles step only; the runs stay loaded and the exit code is 1.
15. Evidence may quote an ad, including a creator's words run as the brand's ad, but never a handle. A short phrase
    of a published advertisement is not personal data; a handle is.
16. Only `kind` `product` rows count as a product's response.
17. The two views are dropped and created again every time the schema is ensured, so a changed definition takes
    effect without dropping tables.

## 11. Known limits

- `changes` and every "moved" column stay nearly empty until the collectors have run repeatedly.
- Meta shows only active ads and TikTok gives no dates, so their lifetimes and endings come from our own looks. Today
  every Meta ad is `undecided`: the oldest started 22 days ago.
- Google ads have no text in the tables, so 692 of 835 `radar_running` rows can have no angle.
- A new ad text is `not_labeled` until someone or something reads it.
- The 30-day and 7-day thresholds are a convention from ad-intelligence tools, not something measured on these brands.
- With `start_basis` `first_seen`, `days_live` is a lower bound.
- A scope seen for the first time writes no `appeared` rows, even when a covering scope was complete before: the
  retailer rows of a barcode that Batiste newly lists show up with `first_seen_at` only.

## 12. Rolling it out

`changes` is only written while runs are loaded, so the existing database is dropped and loaded again from the run
files, as `part1/pipeline/README.md` describes for a schema change. That reload is the plan's verification against
section 9. The README's table count and `tests/test_schema.py` are updated for the two new tables and two views.

## 13. Left to the builder

- How the loader reads the stored values to compare (one query per row or per run), and how it collects the keys that
  `_end_absent` ends.
- The SQL of the two views, and whether helper views are used.
- Where the tracked-column list and the angle list live in the code.
- Test layout, following `part1/pipeline/tests/`.
