# Source 10: Inbox Reader and Black Rifle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The source 10 collector reads the welcome-email inbox itself over IMAP when credentials are set, and Black Rifle Coffee's product count is judged from what the actor handled.

**Architecture:** The redaction rules move from a command-line tool into a function with two levels (verified senders, strict for all others). The collector gets a second email route that fetches messages with `imaplib`, redacts them in memory and then goes through the same file checks as the hand export. Without credentials the old route runs unchanged.

**Tech Stack:** Python 3 standard library (`imaplib`, `email`), existing `unittest` suites.

**Spec:** `docs/superpowers/specs/2026-11-11-source10-inbox-and-blackrifle-design.md` (binding).

## Global Constraints

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no one else's account; no personal data of private individuals; a block is not worked around.
5. Local Postgres, one command, reproducible by someone else.
6. The inbox address and the app password are never written to a file, a log line, a reason string or an exception message the collector stores. Reasons carry exception type names only.
7. The mailbox is opened read-only and messages are fetched with `BODY.PEEK[]`.
8. No retries: each IMAP command is sent once.
9. Tests use no network: the IMAP connection is a fake object passed in.

## Review Focus

1. A sender not in the verified list whose mail has a tracking link the old rules do not know: nothing of the link beyond its host may survive.
2. The inbox address or its local part in a body ("this email was sent to ..."): replaced on the strict level, and the hard check still refuses a message where it survives.
3. A mailbox whose folder names are localized: `\All` and `\Junk` are found by flag.
4. A message that is in both folders or matches two sender domains: one record.
5. Credentials set but login refused: "could not look", no fallback to the files, and the address is not in the reason.

---

### Task A: Black Rifle's count from handled products

**Files:** Modify `part1/collectors/10_brand_site_and_emails/source_collector.py` (`apify_listed`, new `apify_found_per_page`, `apify_prices`), `spec.md` (4.4 step 8), `tests/test_parsers.py`. Sample: `samples/apify/blackrifle_run4_log.txt`.

**Interfaces:**
- Produces: `apify_listed(log: str, listing_url: str) -> int | None` (distinct URLs of `Product handled: (\S+)` lines); `apify_found_per_page(log: str, listing_url: str) -> list[int]`; `part["found_per_page"]`.

- [ ] Tests: run 4 log gives 55 and `[10, 22, 22, 30, 20, 5]`; run 2 log gives 55 and `[55]`; run 1 log gives 5 and `[10]`; a log without handled lines gives `None` and `[]`.
- [ ] Implement, update spec step 8, run the suite, commit.

### Task B1: Redaction as a function with a strict level

**Files:** Modify `part1/collectors/10_brand_site_and_emails/tools/redact_eml.py`. Create `part1/collectors/10_brand_site_and_emails/tests/test_redact.py`.

**Interfaces:**
- Produces:
  - `VERIFIED_DOMAINS = ("livingproof.com", "deathwishcoffee.com", "blackriflecoffee.com")`
  - `class RedactionError(Exception)`
  - `redact_message(src: bytes, gmail_id: str, received_at: datetime, labels: list[str], inbox: str | None = None, strict: bool = False) -> tuple[bytes, dict]`: the redacted message bytes (ASCII, CRLF) and the counts. `inbox` `None` means "take it from the message's `To`", as today. Raises `RedactionError` where the tool exited.
  - `convert(path, out_dir)` keeps its behaviour and output (it calls `redact_message(..., strict=False)` and turns `RedactionError` into the same `SystemExit` messages).
- Strict level: headers kept are `From`, `Reply-To`, `Subject`, `Date`, `MIME-Version`; every URL in a body (`https?://[^\s"'<>()\]]+`) with anything after the host becomes `<scheme>://<host>/REDACTED`; the inbox address and then its local part, case-insensitive, become `TRIAL_INBOX` in the bodies; the first `text/plain` and first `text/html` parts are used, at least one is required, others are dropped and counted in `counts["parts_dropped"]`; `counts["urls"]` is the number of URLs cut. `X-Trial-Redaction` says `strict` and the counts.
- Both levels: `To` replaced, `X-Trial-*` headers added, and the hard check (inbox address, local part, leftover tracking token, removed token) raises `RedactionError`.

- [ ] Tests with synthetic messages (built with `email.message.EmailMessage`, an invented inbox address): verified level reproduces the tracking and unsubscribe replacements and keeps a product link; strict level cuts a link with a token in its path and one with a token in its query, keeps the host, replaces the address in a footer and the local part in a greeting, drops `Message-ID`, accepts an HTML-only message, drops an attachment and counts it; a message with no text part raises; a message whose `Subject` contains the local part raises on both levels; output is ASCII and passes the collector's `read_eml` checks (headers `X-Trial-Gmail-Id`, `X-Trial-Received-At` in `YYYY-MM-DDTHH:MM:SSZ`, exact `To`, `X-Trial-Redaction`).
- [ ] Implement, run the suite, commit.

### Task B2: The `imap` route

**Files:** Modify `part1/collectors/10_brand_site_and_emails/source_collector.py` (`emails_step` and new functions), `spec.md` (section 3 inputs, 4.6, 5), `brand_inputs.json` (sender domains of Batiste and Jinx), `part1/data/email_signups.json` (the two signups), `part1/pipeline/tests/` (one mapper test). Create `part1/collectors/10_brand_site_and_emails/tests/test_imap.py`.

**Interfaces:**
- Consumes: `redact_message`, `RedactionError`, `VERIFIED_DOMAINS` from `tools/redact_eml.py` (imported by adding `HERE / "tools"` to `sys.path`); `read_eml`, `emit`, `utc_now`, `R`.
- Produces:
  - `inbox_credentials() -> tuple[str, str, str] | None`: address, password, host from `INBOX_ADDRESS`, `INBOX_APP_PASSWORD`, `INBOX_IMAP_HOST` (default `imap.gmail.com`); environment first, then `.env` at the repository root; `None` unless address and password are both non-empty.
  - `imap_folders(list_lines: list[bytes]) -> tuple[str | None, str | None]`: the names flagged `\All` and `\Junk`.
  - `imap_since(dt: datetime) -> str`: `DD-Mon-YYYY` with English month names whatever the locale.
  - `parse_fetch(meta: bytes) -> tuple[str | None, datetime | None, list[str]]`: `X-GM-MSGID` as hexadecimal, `INTERNALDATE` in UTC, `X-GM-LABELS`.
  - `emails_imap(cfg, signup, creds, out_dir, connect=imaplib.IMAP4_SSL) -> dict`: the part, with records emitted.
  - `emails_step(cfg, name, out_dir)`: chooses the route; `run_brand` passes `out / f"{run_id}.eml"`.
- Part fields on the `imap` route: `state`, `reason`, `route` `"imap"`, `signup_at`, `first_day_ends_at`, `fetched_at`, `spam_checked`, `messages` (found), `in_window` (records written), `in_first_day`, `before_signup`, `eml_invalid`, and the old keys that do not apply as `None`. The `inbox_export` route adds `route` `"inbox_export"` and is otherwise unchanged.
- Record on the `imap` route: key `email/<gmail id>`, url `signup["signup_url"]`, fetched_at the time of the read, raw `{"route": "imap", "file", "sha256", "eml", "signup_at", "first_day_ends_at", "folder": "all" | "spam", "in_first_day", "redaction": "verified" | "strict", "spam_checked"}`.
- States: `could_not_look` for `no_signup_entry`, `not_signed_up(status=...)`, `sender_domains_unknown` (as before), `imap_login_failed`, `imap_error: <ExceptionType>`, `imap_no_all_folder`; `ok` when both folders were read and `eml_invalid` is 0; otherwise `partial` with `spam_not_checked` and/or `eml_invalid=<n>`.
- Data: Batiste `email_sender_domains` `["tintcommunities.com"]`, Jinx `["thinkjinx.com"]`. Signups: Batiste `submitted_unconfirmed`, `signup_at` and `first_email_at` `2026-11-10T15:13:02Z`, community signup on a third-party site, "Verify your email" received and not confirmed; Jinx `signed_up`, both times `2026-11-10T15:12:32Z`, customer account registration, "Customer account confirmation" received. Each `result` says that `signup_at` is the arrival time of the first mail.

- [ ] Tests with a fake connection (records every command; `select` must be called with `readonly=True`; `uid("FETCH", ...)` must ask for `BODY.PEEK[]`): folders found by flag with localized names; a message present in both folders and matching once gives one record; a message before `signup_at − SIGNUP_TOLERANCE_S` is counted in `before_signup` and not written; a strict sender's message is written with `redaction` `strict`; a message that fails redaction is counted in `eml_invalid` and the state is `partial`; no `\Junk` folder gives `spam_not_checked`; login raising `imaplib.IMAP4.error` gives `could_not_look` / `imap_login_failed` with no address in any stored string; no credentials runs the old route with the committed files and the same result as before; `imap_since` and `parse_fetch` on fixed inputs.
- [ ] Mapper test: an `imap`-route record with an HTML-only message maps to an `ads` row with `body` `None`.
- [ ] Implement, update the spec, run the collector suite and the pipeline suite, commit.

### Task C: Black Rifle's home page through an actor

The trial run got the page (design 3.2), so this is built.

**Files:** Modify `part1/collectors/10_brand_site_and_emails/source_collector.py` (new `home_page_function`, `home_apify`; `run_brand`), `brand_inputs.json` (Black Rifle's `home` gets `"route": "apify_playwright"`), `spec.md` (inputs, a new procedure subsection, output, run result, one fact row), the mapper only if it reads `raw.route` of `offer_slot` records. Create `part1/collectors/10_brand_site_and_emails/tests/test_home_apify.py`.

**Interfaces:**
- Constants: `HOME_APIFY_ACTOR = "apify~playwright-scraper"`, `HOME_APIFY_MEMORY_MB = 2048`, `HOME_APIFY_RUN_TIMEOUT_S = 180`.
- `home_page_function(slots: dict[str, str], settle_s: int) -> str`: the JavaScript `pageFunction` source. It waits `settle_s` seconds, then returns one object: `requested`, `url` (`page.url()`), `title`, `status` (`response.status` or `response.status()`, whichever exists; `null` without a response), `market` (`[window.Shopify?.country ?? null, window.Shopify?.currency?.active ?? null]`), and `slots`: for each slot name the list of `{outer_html, text}` of the elements matching its selector (`page.$$eval`). The selectors are passed in as JSON inside the source, never concatenated unescaped.
- `home_apify_input(cfg) -> dict`: exactly `{"startUrls": [{"url": <home url>}], "linkSelector": "", "pageFunction": <source>, "launcher": "chromium", "proxyConfiguration": {"useApifyProxy": true, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "US"}, "maxPagesPerCrawl": 1, "maxRequestRetries": 0, "pageLoadTimeoutSecs": 60, "waitUntil": "domcontentloaded"}`.
- `home_apify_part(run_status: str | None, items: list | None, cfg) -> tuple[dict, list[dict]]`: pure. The part (`state`, `reason`, `route` `"home_apify"`, `market`, `slots_not_found`) and the `offer_slot` raws to emit. Rules, in order: run not `SUCCEEDED` → `could_not_look` / `apify_run_<status>`; items not a list or empty → `could_not_look` / `home_not_returned`; the item's `url` host differs from `cfg["home"]["host"]` → `blocked: host=<host>`; `status` 403 or 429 → `blocked: http_<status>`; title containing `attention required` or `just a moment` (case-insensitive) → `blocked: title=<phrase>`; `status` 400 or above → `http_<status>`; otherwise one raw per slot `{"route": "home_apify", "slot", "selector", "state": "found" | "not_found", "elements": [...]}`, state `ok`, or `partial` with `slots_not_found(<names>)`.
- `home_apify(cfg) -> tuple[dict, float]`: token missing → `could_not_look` / `missing_token`, cost 0, no request. Start `POST https://api.apify.com/v2/acts/apify~playwright-scraper/runs?timeout=180&memory=2048`, once; not 201 → `could_not_look` / `apify_start_failed: http_<status>` (or the exception type). Poll and read the dataset the way `apify_prices` does, with its constants and its failure reasons (`apify_wait_failed(run=<id>)`, `apify_items_failed: ...`). Emits the records with the key and URL the `home_dom` route uses. Returns the part and `usageTotalUsd` of the last run object.
- `run_brand`: when `cfg["home"].get("route") == "apify_playwright"`, `home` comes from `home_apify(cfg)` instead of `home_step(page, cfg)`, and its cost is added to the run's `cost_usd`.

- [ ] Tests: `home_page_function` embeds both selectors as valid JSON and contains no unescaped quote from a selector with `"` in it; `home_apify_input` equals the dict above for Black Rifle's inputs; `home_apify_part` for a good item (2 and 3 elements) gives `ok` and two raws in slot order with the elements; one empty slot gives `partial` / `slots_not_found(<name>)`; statuses 403 and 429, a foreign host, a Cloudflare title, status 500, a failed run and an empty dataset each give `could_not_look` with the reason above; `home_apify` without a token sends nothing.
- [ ] Implement, update the spec, run the collector suite and the pipeline suite, commit.
