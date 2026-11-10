# Source 10: the collector reads the inbox; Black Rifle counted right

Date: 2026-11-11. Changes `part1/collectors/10_brand_site_and_emails/` (collector, spec, tools) and the email part of
its mapper. Everything else stands.

## 1. Intent

Two things in source 10 were not what they claimed to be.

- **Welcome emails were not collected.** A person exported three messages once, by hand, through a mail connector of
  a chat session, and the collector parsed the files. Nobody else can repeat that, and every pass replays the same
  three files. The radar is meant to be fed constantly.
- **Black Rifle Coffee's products were reported as 55 of 109.** All 55 were there. The collector summed the actor's
  per-page "found" lines, and the pages of one listing repeat products.

A third thing is tried, and kept only if it works: Black Rifle's home page, which refuses our browser, read through
an Apify actor so that its offers are no longer "could not look".

## 2. Emails

### 2.1 Two routes

| Route | When | What it reads |
|---|---|---|
| `imap` | `INBOX_ADDRESS` and `INBOX_APP_PASSWORD` are both set (environment, or `.env` at the repository root) | the mailbox itself, on every pass |
| `inbox_export` | either is missing | the redacted files in `inbox_export/`, exactly as before |

A pass with credentials that cannot log in or read is "could not look" (`imap_login_failed`, `imap_error: <type>`).
It does not fall back to the files: old mail must not stand in for a mailbox that could not be read.

### 2.2 Reading the mailbox

- Standard library `imaplib`, TLS, host `INBOX_IMAP_HOST` (default `imap.gmail.com`), one connection per brand
  process, opened read-only (`EXAMINE`), messages fetched with `BODY.PEEK[]`: nothing in the mailbox changes, not
  even the read flag.
- Two folders, found by their special-use flags and not by name (the names are localized): the one flagged `\All`
  and the one flagged `\Junk`. Both read means `spam_checked` is true. A missing `\Junk` folder leaves it false.
- Per sender domain of the brand: `UID SEARCH FROM "<domain>" SINCE <signup date>`. Only those messages are
  fetched. Nothing else in the mailbox is opened.
- A message's ID is Gmail's `X-GM-MSGID` in hexadecimal, which is the ID the hand export used, so a message that is
  already in the tables keeps its key. On a host without that extension the ID is the first 16 hex digits of the
  SHA-256 of the raw message. Only Gmail was tried.
- No retries. One login per pass and brand.

### 2.3 Redaction, before anything is written

The rules of `tools/redact_eml.py` move into a function the collector and the tool both call. Two levels:

- **Verified senders** (`livingproof.com`, `deathwishcoffee.com`, `blackriflecoffee.com`): the existing rules, which
  were checked against these senders' mail and keep the product links.
- **Any other sender** (strict): the message is stored as plain text only (its plain part, or the text of its HTML
  part when it has none). Only `From`, `Subject`, `Date` and `MIME-Version` are kept. Every link is cut down to its
  host (`https://host/REDACTED`), every email address in the text is replaced, and the inbox address becomes
  `TRIAL_INBOX`. A new sender's links and markup can carry tokens the existing rules do not know, so none are kept.
  What can still pass is an opaque token written as ordinary text outside any link or address.

Both levels keep the hard check: if the inbox address, its local part or a removed token is still anywhere in the
output, the message is not written and is counted in `eml_invalid`. A message that cannot be read (no text part, an
unknown character set) is treated the same way. Other parts (attachments) are dropped.

The redacted `.eml` goes to `raw/<brand>/<run_id>.eml/`, which git ignores. Nothing the reader fetches is committed,
and the address and the password are never written anywhere.

### 2.4 What is kept

With the `imap` route every message from the brand's senders since `signup_at − SIGNUP_TOLERANCE_S` is a record,
not only the first day's: a reader that stopped after 24 hours would never add anything again. `raw.in_first_day`
says whether it arrived in the first 24 hours. The state is `ok` when both folders were read and no message was
invalid; `partial` with `spam_not_checked` or `eml_invalid=<n>` otherwise. `first_day_not_over` no longer applies
on this route.

The `inbox_export` route keeps its first-day window and its states unchanged.

### 2.5 The record

`email` records keep their key (`email/<gmail id>`) and `raw.eml`. `raw.route` is `imap` or `inbox_export`. The
`imap` route adds `folder` (`all` or `spam`), `in_first_day` and `redaction` (`verified` or `strict`), and its
`fetched_at` is the time of the read. The mapper needs only `raw.eml`, so the tables do not change shape.

### 2.6 The two brands without a newsletter

Batiste and Jinx have no email-only signup (see `inbox_setup.md`). The signups made on 2026-11-10 are recorded as
they were: a community account for Batiste, not yet verified, and a customer account for Jinx. Their `signup_at` is
the arrival time of the first mail, and the record says so. Sender domains: `tintcommunities.com` and
`thinkjinx.com`. Their mail is account mail, redacted at the strict level.

## 3. Black Rifle Coffee

### 3.1 The count

`listed` becomes the number of distinct product URLs the actor's log says it handled (`Product handled: <url>`).
The per-page "found" numbers are kept for the record as `found_per_page` and are not summed. The limit is stated:
the listing's own size cannot be checked by us, because the site refuses our browser.

### 3.2 The home page

The home page's offers are read from its DOM by two selectors. Our Chrome is refused (HTTP 403, and the page sends
an automated browser away). Products of the same site already come through an Apify actor, so the home page is
tried the same way: an actor that renders the page and evaluates the same two selectors, and returns each
element's HTML and text. The records keep their shape with `route` `home_apify`.

Tried on 2026-11-11 with `apify/playwright-scraper` through a US residential proxy, one page, no retry: the home
page answered 200 with the Shopify market US and USD, the announcement selector matched 2 elements and the card
selector 166, in 57 seconds for 0.003 USD. So it is built. (`apify/web-scraper` was not used: it asks for full
access to the Apify account.)

When the actor is refused as well, or returns no page, offers are "could not look" with the reason. No other way
around a refusal is tried.

## 4. Goals, non-goals

Goals
- A pass with credentials collects the brands' mail by itself; one without them gives what it gives today.
- Black Rifle's products are `ok` when all handled products were written.
- Nothing that identifies the inbox leaves the machine or enters a committed file.

Non-goals
- OAuth or the Gmail API (three secrets, a consent screen, and tokens that expire weekly for an unpublished app).
- Signing up anywhere, or pressing a confirmation link, from code.
- Mail from senders that are not in a brand's `email_sender_domains`.

## 5. Constraints carried over

1. Hand-written code; at least one source without a paid scraping service.
2. Rerun-safe: no duplicates on a second run; a missing item is marked ended, never deleted. Emails are never ended.
3. Honest gaps: "could not look" is never recorded as "nothing found"; partial collection is marked.
4. Clean collection: no one else's account; no personal data of private individuals; requests are spaced; a block is
   not worked around.
5. Local Postgres, one command, reproducible by someone else.

## 6. Calls made by the designer

1. The strict level for unknown senders, instead of trying to recognize their tracking links.
2. All mail since signup on the `imap` route, instead of the first day only (offered to the user as the default).
3. No fallback to the files when the credentials are there but the mailbox cannot be read.
4. The Gmail message ID as the key, so that hand-exported and collected copies of one message are one row.
5. `listed` from the actor's "handled" lines; the page counts are shown, not used.
