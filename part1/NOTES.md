# Market Radar: notes

Five brands, ten sources, one command (`part1/run.py`) into a local Postgres. The full pass of 2026-11-11: 3,933
records in 7 minutes for 7.05 USD (1.79 per 1,000, most of it Amazon and Meta); of 50 source-and-brand cells 41
`ok`, 8 `partial`, 1 `could not look`. The tables are in `part1/data/market_radar.sql.gz`. Last column: USD per 1,000.

| # | Source | How, and why this way | Where it blocked | $/1,000 | Breaks first |
|---|---|---|---|---|---|
| 1 | Google Ads Transparency | Own code: headless Chrome reads the page's own list and detail responses. Public, no login | HTTP 429 when pages load 3 s apart: 10 s kept, and an ad's detail is re-read once a day | 0 | The numbered keys of those responses |
| 2 | TikTok ads | Apify actor on Creative Center "Top Ads": TikTok's Ad Library has no US region | Top-performing ads only; 3 of 296 rows name a brand. Batiste: `could not look` | 24.47 * | Matching a brand by text |
| 3 | Meta Ad Library | Own browser reads each page's ad count; the ads come through an Apify actor and are checked against it | The library refuses paging from a datacenter address | 5.80 | The count read from the page |
| 4 | Amazon | Three Apify actors (search, product, reviews): no account is used, and review text needs a signed-in browser | Review pages redirect to sign-in. Actor sessions see no sponsored results | 5.68 | Search order varies by session |
| 5 | Retail shelf | Ulta: own code (listing in the page, reviews from its review API). Target, Sephora, Chewy: Apify | Target answers a bot-protection block, Sephora 403 to every browser | 0.94 | Ulta's embedded page state |
| 6 | Google results | Apify actor | Automated Chrome gets reCAPTCHA on the first search. Ads came back empty: `could not look` per term | 2.41 | Results differ run to run: half the URLs changed in 5 hours |
| 7 | Search interest | Own code: a visible Chrome opens Google Trends and reads the chart's own data request | Headless Chrome gets 429 at once; 28 s between pages; needs a desktop session | 0 | Trends' per-client limit |
| 8 | TikTok posts | Apify actor: the brand profile's popular posts and one hashtag feed | Read by ourselves, TikTok gave only reposts and hashtag statistics | 0.63 | The chosen hashtag |
| 9 | TikTok Shop | Apify actor | A slider puzzle for a logged-out browser; it is not solved. 11 to 18 of 20 products came back, for every brand | 1.34 | Per-product fetches |
| 10 | Brand site, emails | Own code: Shopify `products.json`, Batiste's where-to-buy API, home-page offers, signup forms, the inbox over IMAP. Black Rifle refuses our browser: Apify for it | Batiste's API refuses 6 of 63 barcodes. Black Rifle's actor sometimes reports no currency. Batiste and Jinx send account mail only | 0.23 | Offer-slot selectors; the app password |

\* 3 records: a keyword search costs the same whatever it finds.

**Why these routes.** Own code wherever a public page answers a plain browser: free, and every record has a URL to
check. One paid service, Apify, where a site refuses automation or wants a login. Nothing solves a CAPTCHA, logs in
or hides from detection: a refusal is recorded as "could not look", never as "nothing found", and the next pass is
the retry. Reviewer names and creators' display names are not stored.

**Assumptions.** Run from a US IP address (a VPN). A pass is a snapshot: "ended" and "changed"
come from comparing passes, and only a complete look ends a row. Per-brand inputs (page IDs, search terms, hashtags,
one Target store, the inbox signups) were set up by hand. "Working" means an ad live for 30 days or more; ad
angles are a model's reading of the ad text.

**Left out, and not verified.** Each collector was compared with the live site while it was built (its `spec.md`
lists what matched); the final tables were not compared record by record. The full pass ran from a fresh
environment built by the README, on the machine it was written on, not on another. Left out: Google search ads,
ad media files, mail from senders outside each brand's listed domains, retries inside a pass.

**Next to build.** (1) A worker that archives ad media before its URLs expire. (2) Backing off after a block, and a
schedule per source (free hourly, paid daily). (3) A routine check of stored records against the live sites.
(4) A second route for Batiste's TikTok ads; a currency check for Black Rifle's prices.
