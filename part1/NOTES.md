# Market Radar: notes

Five brands, ten sources, one command (`part1/run.py`) into a local Postgres. On 2026-11-11: 3,933 records; of 50
source-and-brand cells 43 `ok`, 6 `partial`, 1 `could not look`. A pass of everything cost 7.34 USD (1.87 per 1,000
records, three quarters of it Amazon and Meta) and takes minutes. The last column is USD per 1,000 records.

| # | Source | How, and why this way | Where it blocked | $/1,000 | Breaks first |
|---|---|---|---|---|---|
| 1 | Google Ads Transparency | Own code: headless Chrome reads the page's own list and detail responses. Public, no login | HTTP 429 when pages load 3 s apart: 10 s kept, and an ad's detail is re-read once a day | 0 | The numbered keys of those responses |
| 2 | TikTok ads | Apify actor on Creative Center "Top Ads": TikTok's Ad Library has no US region | Top-performing ads only; 3 of 296 rows name a brand. Batiste: `could not look` | 24.23 * | Matching a brand by text |
| 3 | Meta Ad Library | Own browser reads each page's ad count; the ads come through an Apify actor and are checked against it | The library refuses paging from a datacenter address | 5.80 | The count read from the page |
| 4 | Amazon | Three Apify actors (search, product, reviews): no account is used, and review text needs a signed-in browser | Review pages redirect to sign-in. Actor sessions see no sponsored results | 5.67 | Search order varies by session |
| 5 | Retail shelf | Ulta: own code (listing in the page, reviews from its review API). Target, Sephora, Chewy: Apify | Target answers a bot-protection block, Sephora 403 to every browser | 0.94 | Ulta's embedded page state |
| 6 | Google results | Apify actor | Automated Chrome gets reCAPTCHA on the first search. Ads came back empty where a person saw two: `could not look` per term | 2.48 | Result types (a "Map" row) |
| 7 | Search interest | Own code: a visible Chrome opens Google Trends and reads the chart's own data request | Headless Chrome gets 429 at once; 28 s between pages; needs a desktop session | 0 | Trends' per-client limit |
| 8 | TikTok posts | Apify actor: the brand profile's popular posts and one hashtag feed | Read by ourselves, TikTok gave only reposts and hashtag statistics | 1.70 | The chosen hashtag |
| 9 | TikTok Shop | Apify actor | A slider puzzle for a logged-out browser; it is not solved. 15 to 19 of 20 products came back for three brands | 1.88 | Per-product fetches |
| 10 | Brand site, emails | Own code: Shopify `products.json`, Batiste's where-to-buy API, home-page offers, signup forms, and the welcome-email inbox read over IMAP. Black Rifle refuses our browser: its products and home page go through Apify | Batiste's API refuses 6 of 63 barcodes. Black Rifle's product actor reports no currency. Batiste and Jinx have no newsletter form: their mail is account mail | 0.26 | Offer-slot selectors; the inbox's app password |

\* 3 records: a keyword search costs the same whatever it finds.

**Why these routes.** Own code wherever a public page answers a plain browser: free, and every record has a URL to
check. One paid service, Apify, where a site refuses automation or wants a login. Nothing solves a CAPTCHA, logs in
or hides from detection: a refusal is recorded as "could not look", never as "nothing found", and the next pass is
the retry. Reviewer names and creators' display names are not stored.

**Assumptions.** Run from a US IP address (a datacenter VPN was used). A pass is a snapshot: "ended" and "changed"
come from comparing passes, and only a complete look ends a row. Per-brand inputs (page IDs, search terms, hashtags,
one Target store) were researched by hand, and so were the signups of the one dedicated inbox. "Working" means an
ad live for 30 days or more; ad angles are a model's reading of the ad text.

**Left out, and not verified.** Each collector was compared with the live site while it was built (its `spec.md`
lists what matched); the final tables were not compared record by record. No pass of all ten sources at once at the
current pace, and no run from a fresh clone (install and start only). Left out: Google search ads, ad media files
(their URLs expire in days), mail from senders outside each brand's listed domains, retries inside a pass.

**Next to build.** (1) A worker that archives ad media before its URLs expire. (2) Backing off by itself after a
block; a schedule per source (free ones hourly, paid ones daily). (3) A routine check of stored records against the
live sites. (4) A second route for Batiste's TikTok ads, and a currency check for Black Rifle's prices.
