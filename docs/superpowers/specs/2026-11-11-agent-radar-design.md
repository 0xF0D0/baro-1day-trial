# Market Radar: what the agents read

Date: 2026-11-11. Builds on `2026-11-10-market-radar-tables-design.md` (the "tables design"), which stays in force.

## 1. Intent

The radar exists to tell a brand which angles and strategies work for its competitors right now, and which do not.
It is fed constantly, and it is one of the inputs that agents read (with people reviewing).

The tables design gave us six tables that hold what each source shows, with `first_seen_at`, `last_seen_at` and
`ended_at` per row. That answers "what are competitors doing". It does not yet answer "is it working", "what changed",
or "with which angle".

None of the sources publishes results, so "working" has to be read from two kinds of evidence:

| Evidence | Measured by | Applies to |
|---|---|---|
| The competitor keeps doing it | how long it stays up | ads, home-page offers, signup forms, emails: things a competitor pays for or gives space to |
| The public responded | published numbers and how they move | posts (views), products (rank, reviews, units sold), search results (position) |

Both need time, so the first thing added is a record of what changed and when.

A flat count of angles over everything shows nothing. An angle only says something next to what the ad sells, whose ad
it is, and how long it lasted. So the agents' first read is a summary by brand, by what is sold, by angle.

## 2. What gets built

Five things on top of the six tables. The six tables, the mappers and the collectors do not change.

| Name | Kind | One row is | Answers |
|---|---|---|---|
| `changes` | table, written by the loader, append-only | one change to one item, seen at one run | what changed, and when |
| `ad_angles` | table, filled from a labels file | the three angles of one ad, with the words they were read from | how does this ad sell |
| `radar_running` | view over `ads` (+ `changes`, `ad_angles`) | one ad or owned-channel message | how long has it run, what does it sell, where does it send people, with which angles |
| `radar_angles` | view over `radar_running` | one angle of one thing a brand sells | which angles does a brand use for a product, and do they last |
| `radar_response` | view over `posts`, `products`, `search_rankings` (+ `changes`) | one published number of one item, with its last move | what is getting a response |

An agent reads `radar_angles` first, goes down to `radar_running` for the ads behind a line, to `changes` for what
started and stopped lately, and to `radar_response` for what the public responds to.

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
| `old_value`, `new_value` | text | only for `changed`, and then never NULL |

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
| `changed` | a row that already existed is seen again and a tracked column in the mapper's row differs from the stored value, both being known (not NULL); one `changes` row per column |

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

A value that was not known before, or is not known now, is not a change. NULL stands for "not read" as well as for
"none", and the two cannot be told apart: on the real run files, 131 Google ads went from no variation count to one
only because the first look had not read the ad's detail. Such a row is updated and writes nothing to `changes`.

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
| `format`, `headline`, `body`, `cta`, `landing_url`, `landing_domain`, `offer_code`, `variation_count` | from `ads` |
| `destination` | `brand_site`, `retailer`, `other`, or NULL when there is no `landing_domain` (4.1) |
| `subject_type`, `subject` | what the ad sells, read from `landing_url`; both NULL when there is none (4.2) |
| `started` | `started_at` when the source gives one, else `first_seen_at` |
| `start_basis` | `source` or `first_seen` |
| `ended_at` | from `ads` |
| `status` | `live` when `ended_at` is NULL, else `ended` |
| `days_live` | whole days from `started` to `ended_at`, or to `last_seen_at` while live |
| `verdict` | `working`, `not_working` or `undecided` (4.3) |
| `angle_offer`, `angle_message`, `angle_voice` | the ad's three angles from `ad_angles`, NULL when not labeled (5) |
| `angle_state` | `labeled`, `not_labeled` or `no_text` (5.5) |

`days_live` counts to `last_seen_at`, not to the current time, so an ad is not credited with days on which nobody looked.
With `start_basis` `first_seen` it is a lower bound: the ad may be older than our first look.

### 4.1 `destination`

- `brand_site` when `landing_domain` is the brand's own domain or a subdomain of it: `batistehair.com`,
  `livingproof.com`, `deathwishcoffee.com`, `blackriflecoffee.com`, `thinkjinx.com`.
- `retailer` when it is, or is a subdomain of, one of: `amazon.com`, `ulta.com`, `target.com`, `sephora.com`,
  `walmart.com`, `chewy.com`, `cvs.com`, `walgreens.com`, `kroger.com`, `petco.com`, `petsmart.com`.
- `other` for any other domain.

Both lists live in `schema.sql` next to the view.

### 4.2 `subject`

The path is `landing_url` without scheme, host, query, fragment and trailing slashes.

| `subject_type` | When | `subject` |
|---|---|---|
| `retailer_product` | `destination` is `retailer` | `landing_domain` followed by the path |
| `other` | `destination` is `other` | `landing_domain` followed by the path |
| `product` | `brand_site`, and the path has `/products/<handle>` | the handle |
| `collection` | `brand_site`, and the path starts with `/collections/<name>` without `/products/` | `collections/<name>` |
| `home` | `brand_site`, and the path is empty | `home` |
| `page` | `brand_site`, anything else | the path without its leading slash |

The handle is kept as written in the URL (percent-encoded characters included). Google gives a landing domain but no
URL, so every Google ad has a `destination` and no `subject`.

### 4.3 `verdict`

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

## 5. Angles

An angle is how an ad sells: a reading of its words, not something a source publishes. It is kept apart from the
collected columns, with the words it was read from.

### 5.1 Three kinds, one value each

"Angle" is the whole of it. Each ad gets exactly one value of each kind, so that counts by any kind add up to the
number of ads.

| Kind | Column | Question | Values |
|---|---|---|---|
| offer | `angle_offer` | what does the ad give for acting now | `discount`, `free_gift`, `bundle`, `subscription`, `giveaway`, `free_shipping`, `none` |
| message | `angle_message` | what does the ad put forward about the product | `benefit`, `ingredient`, `convenience`, `proof`, `personal_fit`, `novelty`, `gifting`, `availability`, `brand`, `none` |
| voice | `angle_voice` | who is speaking | `brand`, `creator`, `customer`, `expert`, `celebrity_event` |

| Value | Meaning |
|---|---|
| `discount` | money or a percentage off, a code |
| `free_gift` | a free item with purchase: samples, minis, a bag |
| `bundle` | a set or a build-your-own bundle at a lower price |
| `subscription` | a lower price or perk for subscribing |
| `giveaway` | a draw, a contest, an entry to win |
| `free_shipping` | free delivery |
| `benefit` | what the product does for the buyer: result, taste, strength, with or without numbers |
| `ingredient` | an ingredient, a technology, a formula, nutrition |
| `convenience` | saving time or effort, portability, fast delivery |
| `proof` | units sold, awards, "No. 1", ratings, a quoted review, a professional's recommendation |
| `personal_fit` | several products for different needs, a quiz, where to start, build your own |
| `novelty` | a new product, a limited edition, a new scent or flavour, a return |
| `gifting` | a holiday, a season, giving it as a gift |
| `availability` | now sold at a named retailer, an exclusive, back in stock |
| `brand` | who the brand is or stands for, belonging, a cause |
| `creator` | a creator or partner speaking in first person |
| `customer` | a customer's words quoted |
| `expert` | a professional speaking or cited (stylist, vet, barista) |
| `celebrity_event` | a named celebrity, athlete, band, or event tie-in |

Choosing one: the value the headline or the first sentence leads with; when the ad leads with nothing of that kind,
the kind that takes most of the words. An ad that only states a deal has `angle_message` `none`. `angle_voice` is
`brand` unless the words are clearly someone else's.

Signup forms carry the brand's internal name of the form, not what a visitor reads. Their angles are read from that
name: usually an offer (`giveaway`, `discount`) or a message (`novelty`, `availability`), often `none`.

### 5.2 Labels file

`part1/pipeline/labels/ad_angles.jsonl`, committed. One line per distinct ad text:

```json
{"text_sha256": "<64 hex>", "list_version": 1, "labeled_by": "<who or what read it>", "labeled_at": "<UTC time>",
 "angle_offer": "discount", "offer_evidence": "Save 20%",
 "angle_message": "gifting", "message_evidence": "last-minute gift-givers",
 "angle_voice": "brand", "voice_evidence": null}
```

- The ad text is `headline` and `body`, each with runs of whitespace turned into one space and trimmed, joined by one
  newline; a missing one counts as empty. When both are empty the ad has no text.
- `text_sha256` is the SHA-256 of that text in UTF-8.
- An evidence is a phrase of at most 12 words copied from that text. It must occur in the text, and it must not
  contain an `@` handle. It is required when the value is not `none` (offer, message) and not `brand` (voice), and
  NULL otherwise.
- The file does not hold the ad text itself. Some ads are a creator's words run by the brand, and the repository is public.

### 5.3 Who writes the lines

`python part1/pipeline/angles.py --pending` writes the distinct texts that have no line yet to standard output, one
JSON object per line with `text_sha256`, `text`, `brands`, `channels`, `kinds` and `ads` (how many ads use it). It is
not committed.

`python part1/pipeline/angles.py --label` reads the pending texts, asks a model for the three angles of each, checks
the answer and appends a line per text.

- One request per text, sent once. The model must answer in a fixed structure with the values of 5.1.
- An answer is checked like any line (5.4). A text whose answer fails the check, or whose request fails, gets no line
  and is counted; it stays pending.
- The key is `ANTHROPIC_API_KEY`, from the environment or from `.env` at the repository root. Without it the command
  prints `label: could not look: missing_key`, writes nothing and exits 1.
- The model is `claude-opus-5-5`; the environment variable `ANGLE_MODEL` overrides it. `labeled_by` is
  `<model>/prompt-v1`.
- A request the API rejects as invalid (HTTP 400: a request shape it does not accept, or an account it will not
  serve) will not get better for the next text. The run stops, prints `label: could not look: bad_request: <the
  API's message>` and exits 1; lines already appended stay. An authentication or permission error stops it the
  same way with `label: could not look: auth`.
- It prints `label: labeled=<n> failed=<n> pending=<n>` and exits 0 when nothing failed, 1 otherwise.
- The official `anthropic` Python package is used; it is added to `part1/pipeline/requirements.txt`.

A person may also add or correct lines by hand; the file is the record either way. For this delivery the lines come
from `--label` with a key that is not committed, and the main session reads a sample of them against the texts.

### 5.4 Table and loading

`ad_angles`: `source`, `brand`, `kind`, `key`, `angle_offer`, `offer_evidence`, `angle_message`, `message_evidence`,
`angle_voice`, `voice_evidence`, `text_sha256`, `list_version`, `labeled_by`, `labeled_at`; primary key
`(source, brand, kind, key)`.

After its runs, `load.py` rebuilds `ad_angles` from the file: for every `ads` row with text, the line for the text's
hash. It fails, naming the line, when a line has a value outside the lists, a missing or unexpected evidence, a
duplicate hash, an evidence with an `@`, or an evidence that does not occur in the text of an ad with that hash.
Evidence is checked against every ad that has the hash. A hash that matches no ad is not an error (the ad may be in
another database).

`load.py` prints one more line before its `runs:` line: `angles: labeled=<ads> not_labeled=<ads> no_text=<ads>`.

The angles step runs after the runs, in its own transaction. When the file is invalid, the runs stay loaded,
`ad_angles` is left as it was, the line is `angles: failed: line <n>: <reason>`, the `runs:` line is still printed, and
the exit code is 1. A missing file is an empty file.

### 5.5 `angle_state`

| State | When |
|---|---|
| `no_text` | `headline` and `body` are both empty (every Google ad: the creative is an image or a video) |
| `labeled` | `ad_angles` has a row for the ad |
| `not_labeled` | the ad has text and no line in the file yet |

`not_labeled` is "not read yet", never "no angle".

## 6. `radar_angles`

A view: `radar_running` rows with `angle_state` `labeled`, turned into one row per kind, without the value `none`,
then grouped.

| Column | Meaning |
|---|---|
| `brand` | |
| `subject_type`, `subject` | what is sold; NULL for ads without a landing URL (owned-channel messages) |
| `angle_kind` | `offer`, `message` or `voice` |
| `angle` | the value |
| `ads` | ads in the group |
| `live` | of those, with `status` `live` |
| `started_last_7d` | of those, with `started` in the 7 days before the latest look, which is the greatest `last_seen_at` in `ads` |
| `oldest_days_live` | the greatest `days_live` in the group |
| `working`, `not_working` | of those, by `verdict` |

Within one brand, subject and kind, `ads` adds up to the labeled ads of that subject minus those whose value is `none`.

## 7. `radar_response`

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
brand's term returns, mostly other brands' products. Price is left out: it is the competitor's move, not the public's
response; its changes are in `changes`.

There is no `not_working` here. Posts are collected by popularity, so the ones that went nowhere are not in the sample.
Products and search results get no verdict yet: their evidence is movement, which needs repeated runs.

## 8. Goals, non-goals, anti-goals

Goals
- An agent answers "which angles does this brand use for this product, and do they last" from `radar_angles` alone,
  and reaches the ads behind a line in `radar_running`.
- An agent answers "what changed for these brands since <time>" from `changes` alone, and "what is getting a response"
  from `radar_response` alone.
- Every row leads back to its item (`source`, `brand`, `key`, `url`), so a person can check it.
- Loading stays one command and rerun-safe; loading the same files again changes nothing.

Non-goals (not in this work)
- Angles for posts; reading images or video; pulling the wording of Google ads out of their saved creative scripts.
- Linking an ad's subject to a row of `products`.
- Verdicts for products and search results. `search_interest` in a radar view (it is already a time series).
- A scheduler, and the one command that runs collectors and then the loader.

Anti-goals
- A verdict or an angle presented as a collected fact. They sit in their own columns and table, with the rule or the evidence.
- "Appeared", "ended" or "not working" claimed without a complete look behind it.
- Storing the words of private individuals in the repository.

## 9. Constraints carried over

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no personal data of private individuals.
5. Local Postgres, one command, reproducible by someone else.
6. Every record keeps its source URL and fetch time.

## 10. Expected results on the current run files

With the 69 runs now on disk, loaded in order into an empty database:

| Check | Expected |
|---|---|
| `radar_running` rows | 835, one per `ads` row |
| Google ads by verdict | `working` 498, `not_working` 47, `undecided` 147 (`days_live` is whole days, so an ad that ran 7 days and 22 hours counts as 7) |
| Every other channel | all `undecided` (Meta 89, signup forms 34, site 14, email 3, TikTok 3) |
| `destination` | `brand_site` 770 (692 Google, 78 Meta), `retailer` 11 (Meta), NULL 54 |
| `subject_type` | only Meta has one: `product` 33, `collection` 27, `page` 17, `retailer_product` 11, `home` 1 |
| `angle_state` | `no_text` 695 (692 Google, 3 site), and 140 with text over 119 distinct texts: `labeled` after labeling, `not_labeled` before |
| `radar_angles` | the builder reports the rows for Living Proof and Batiste and checks one subject by hand against its ads |
| `radar_response` rows | 2,224: posts 995 (199 x 5), products 396 (rank 109, rating 120, review_count 138, sold_count 29), search 833 |
| Posts with `verdict` `working` | 95 of 199 |
| `changes` | 10 rows, all `changed` on `price` of Ulta products (the two Ulta runs made before and after the collector began to read the price at the product's own URL). No item appeared or ended between two complete looks yet |
| Second load | no new rows anywhere, `changes` included |

These numbers move when new runs are added.

## 11. Calls made by the designer

1. Two radar views for the two kinds of evidence, so that "working" means one thing per view, and a third that sums
   up angles by what is sold.
2. `radar_response` is long (one number per row). The item tables already hold the wide row; what the view adds is one
   shape across natures, the baseline, and the last move.
3. `appeared` only against an earlier complete look; nothing for a row first seen already ended.
4. `days_live` to `last_seen_at`, not to now.
5. Verdict by time only: 30 days for `working`, 7 for `not_working`. Variations are shown, not used.
6. `not_working` needs a known start.
7. A post is `working` when views are at least the creator's followers. Simple, and it favours small accounts; both
   numbers are in the row.
8. Price is not a response number.
9. The domain lists for `destination` and the rule for `subject` are written in `schema.sql`.
10. Three kinds of angle with one value each, instead of one list with several values per ad: counts add up and no
    kind is hidden inside another.
11. A deal is an offer, not a message: an ad that only states a deal has message `none`.
12. Labels live in a committed file keyed by the hash of the text, with evidence that must occur in the text. The ad
    text is not committed.
13. Angles only for `ads` rows that have text. Posts are left out: their captions are private individuals' words.
14. The tracked columns in 3.3.
15. `load.py` applies the labels file itself, so one command still fills everything. An invalid file fails the angles
    step only; the runs stay loaded and the exit code is 1.
16. Evidence may quote an ad, including a creator's words run as the brand's ad, but never a handle. A short phrase
    of a published advertisement is not personal data; a handle is.
17. Only `kind` `product` rows count as a product's response.
18. The three views are dropped and created again every time the schema is ensured, so a changed definition takes
    effect without dropping tables.
19. `--label` calls the model once per pending text and never relabels a text that has a line.
20. `started_last_7d` counts back from the latest look, not from the current time.

## 12. Known limits

- `changes` and every "moved" column stay nearly empty until the collectors have run repeatedly.
- A value that appears where there was none, or goes away, writes no `changed` row: a discount code or a list price
  showing up is visible in the item's row, not in `changes`.
- Meta shows only active ads and TikTok gives no dates, so their lifetimes and endings come from our own looks. Today
  every Meta ad is `undecided`: the oldest started 22 days ago.
- Google ads have no text and no landing URL in the tables, so 692 of 835 `radar_running` rows have no angle and no
  subject. For Google only format, destination and lifetime are known.
- Meta has runs for two of the five brands, so `radar_angles` covers Batiste and Living Proof, plus the owned-channel
  messages of all five.
- One value per kind drops an ad's second message. The evidence and the ad's words stay in the row.
- A model's reading is not checked against a person's beyond a sample. The evidence check catches invented quotes, not
  a wrong choice of value.
- The 30-day and 7-day thresholds are a convention from ad-intelligence tools, not something measured on these brands.
- With `start_basis` `first_seen`, `days_live` is a lower bound.
- A scope seen for the first time writes no `appeared` rows, even when a covering scope was complete before: the
  retailer rows of a barcode that Batiste newly lists show up with `first_seen_at` only.

## 13. Rolling it out

`changes` is only written while runs are loaded, so the existing database is dropped and loaded again from the run
files, as `part1/pipeline/README.md` describes for a schema change. That reload is the plan's verification against
section 10. The README's table count and `tests/test_schema.py` are updated for the two new tables and three views.

## 14. Left to the builder

- How the loader reads the stored values to compare (one query per row or per run), and how it collects the keys that
  `_end_absent` ends.
- The SQL of the three views, and whether helper views are used.
- Where the tracked-column list and the angle lists live in the code.
- The wording of the prompt for `--label`.
- Test layout, following `part1/pipeline/tests/`.
