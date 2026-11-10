# Inbox setup for welcome emails (source 10)

Who needs this: someone who wants the collector to read a mailbox of their own. Rerunning the collectors without
one needs none of it: they then read the redacted files already in `inbox_export/`.

Everything on this page is done by a person in a browser. No code here signs up anywhere, creates an account or
clicks a confirmation link.

## 1. A dedicated inbox

- Create a mailbox that is used for nothing else. The trial used a new Gmail account.
- It must be your own. The collection rules exclude other people's accounts, and everything that arrives there
  becomes collector input.
- The address never goes into a committed file. The export replaces it (`To: TRIAL_INBOX
  <trial_inbox@redacted.invalid>`) and drops the headers that carry it.

## 2. Access for the collector

The collector reads the mailbox over IMAP with an app password. It opens it read-only: nothing is marked read,
moved or deleted.

1. In the Google Account of the inbox: Security, turn on 2-Step Verification. App passwords exist only with it on.
2. Open `https://myaccount.google.com/apppasswords` and create an app password (any name, for example
   `market radar`). Google shows its 16 characters once.
3. Put both in `.env` at the repository root:

       INBOX_ADDRESS=<the inbox address>
       INBOX_APP_PASSWORD=<the 16 characters, without spaces>

- An app password opens the whole mailbox. Keep it only in `.env` (ignored by git), and revoke it on the same page
  when it is no longer needed.

## 3. Sign up, brand by brand

In a normal browser, from a US IP address. For each brand: use the form in the table, note the time in UTC right
after the submit, and skip any step that asks for a phone number (the SMS steps were skipped in the trial). If the
brand sends a mail that asks to confirm the address, press its button yourself.

| Brand | Where | What happened on 2026-11-10 | Mail comes from |
|---|---|---|---|
| Living Proof | `https://www.livingproof.com/`, the site popup ("15% off your first order...") | The popup went on to an SMS step, which was skipped. First mail 83 s after the submit | `livingproof.com` |
| Death Wish Coffee | `https://www.deathwishcoffee.com/`, the footer form ("...save 20% off your first order") | "THANKS FOR SUBSCRIBING!" on the page. First mail within seconds | `deathwishcoffee.com` |
| Black Rifle Coffee | `https://www.blackriflecoffee.com/`, the site popup ("WANT THE LATEST INTEL?...") | The popup went on to an SMS step, which was skipped. No confirmation text. First mail 94 s after the submit | `blackriflecoffee.com` |
| Batiste | `https://www.batistehair.com/` has no email form. Its "JOIN NOW" link leads to Batiste Nation, a community on a third-party site | Joining the community sends "Verify your email" from `tintcommunities.com`; nothing further arrives until its button is pressed | `tintcommunities.com` |
| Jinx | `https://www.thinkjinx.com/` shows no email-only signup: the newsletter section renders empty and no popup appeared in about 60 s. The other routes are a customer or loyalty account and a support form | Creating a customer account sends "Customer account confirmation" from `thinkjinx.com`, with no offer in it | `thinkjinx.com` |

For Batiste and Jinx the mail above is account mail, not a newsletter welcome. Whether to count it is a choice; the
record (step 4) says which route was used.

## 4. Record the signup

Two files tell the collector what to expect.

- `part1/data/email_signups.json`, one entry per brand:

  | Field | Value |
  |---|---|
  | `brand` | the brand's name as in `brands.json` |
  | `status` | `signed_up`, `submitted_unconfirmed` (submitted, no confirmation seen) or `not_signed_up` |
  | `signup_at` | UTC time right after the submit, `YYYY-MM-DDTHH:MM:SSZ`; `null` when not signed up |
  | `signup_url`, `form` | the page and which form on it |
  | `offer_text` | the offer the form showed, as written |
  | `result` | what the page showed after the submit |
  | `first_email_at` | when the first mail arrived, once known |

  With `signup_at` `null` the collector records the brand's emails as "could not look"
  (`not_signed_up(status=...)`). For Batiste and Jinx the record holds the account signups of 2026-11-10, with
  `signup_at` taken from the arrival of the first mail.

- `brand_inputs.json` in this folder: `email_sender_domains` of the brand, taken from the `From` address of its
  first real mail. While it is empty the collector records `sender_domains_unknown`.

## 5. What a pass then does

- With the two keys set, every pass reads the mail of each brand's sender domains since its `signup_at`, from the
  All Mail folder and the Spam folder, and records each message once. Mail from a sender the redaction rules were
  checked against keeps its product links; mail from any other sender is stored as plain text with every link cut
  to its host. The redacted copies are written under `raw/`, which git ignores.
- Wrong or revoked credentials give "could not look" (`imap_login_failed`); the exported files are not used in
  their place.

## 6. The exported files (the route without a mailbox)

The three files in `inbox_export/` were made by hand on 2026-11-10, by the procedure in section 12 of
`source_info.md`: search the mailbox for the sender domains only, save each message through
`tools/redact_eml.py`, check the result with `tools/verify_eml.py`, and write `inbox_export/export.json`. They are
what a pass without the two keys reads. On that route only the first 24 hours after `signup_at` count, an export
made earlier is marked `first_day_not_over`, and `spam_not_checked` is added while the export's `spam_checked` is
`false`.
