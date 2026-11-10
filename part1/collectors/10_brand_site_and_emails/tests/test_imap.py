import hashlib
import imaplib
import io
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
COLLECTOR = HERE.parent
sys.path.insert(0, str(COLLECTOR))
import source_collector as sc  # noqa: E402

ADDRESS = "radar.inbox77@example.org"
PASSWORD = "dummy pass word xx"
PASSWORD_SQUEEZED = "dummypasswordxx"
HOST = "imap.example.org"
CREDS = (ADDRESS, PASSWORD_SQUEEZED, HOST)

LIST_LINES = [
    b'(\\HasNoChildren) "/" "INBOX"',
    b'(\\HasNoChildren \\All) "/" "[Gmail]/Alle Nachrichten"',
    b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"',
    b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Papierkorb"',
]
ALL_Q, SPAM_Q = '"[Gmail]/Alle Nachrichten"', '"[Gmail]/Spam"'

JINX = {"email_sender_domains": ["thinkjinx.com"]}
SIGNUP = {"brand": "Jinx", "status": "signed_up", "signup_at": "2026-11-10T15:12:32Z",
          "signup_url": "https://www.thinkjinx.com/"}


def raw_message(sender="support@thinkjinx.com", subject="Customer account confirmation", html=True,
                body=None, both=False):
    m = EmailMessage()
    m["From"] = f"Shop <{sender}>"
    m["To"] = f"Me <{ADDRESS}>"
    m["Subject"] = subject
    m["Date"] = "Tue, 10 Nov 2026 15:12:32 +0000"
    m["Message-ID"] = "<abc@example.test>"
    if both:
        m.set_content(body)
        m.add_alternative(f"<p>{body}</p>", subtype="html")
    elif html:
        m.set_content(body or '<p>Welcome <a href="https://www.thinkjinx.com/account/activate/77/aabbccddeeff?x=1">go</a></p>',
                      subtype="html")
    else:
        m.set_content(body or "Welcome")
    return m.as_bytes()


def meta(gid, date="10-Nov-2026 15:13:02 +0000", labels='"\\\\Inbox"', size=100):
    return (f'1 (X-GM-MSGID {gid} X-GM-LABELS ({labels}) UID 12 INTERNALDATE "{date}" '
            f'BODY[] {{{size}}}').encode()


class FakeConn:
    """folders: {quoted folder name: {domain: [(uid, meta bytes or None, raw)]}}"""

    def __init__(self, folders, list_lines=LIST_LINES, login_error=None, fail=None, search_status="OK",
                 bad_select=(), select_raises=()):
        self.folders, self.list_lines = folders, list_lines
        self.select_raises = select_raises
        self.login_error, self.fail, self.search_status, self.bad_select = login_error, fail, search_status, bad_select
        self.calls, self.current, self.loggedout = [], None, False

    def _log(self, cmd, args, kwargs):
        self.calls.append((cmd, args, kwargs))
        if self.fail and self.fail[0] == cmd:
            raise self.fail[1]

    def login(self, *a, **k):
        self._log("login", a, k)
        if self.login_error:
            raise self.login_error
        return "OK", [b"ok"]

    def list(self, *a, **k):
        self._log("list", a, k)
        return "OK", list(self.list_lines)

    def select(self, name, *a, **k):
        self._log("select", (name,) + a, k)
        if name in self.select_raises:
            raise OSError("select broke")
        if name in self.bad_select:
            return "NO", [b"no"]
        self.current = name
        return "OK", [b"1"]

    def uid(self, command, *a, **k):
        self._log("uid " + command, a, k)
        box = self.folders.get(self.current, {})
        if command == "SEARCH":
            domain = a[2].strip('"')
            if self.search_status != "OK":
                return self.search_status, [b"err"]
            uids = [u for u, _, _ in box.get(domain, [])]
            return "OK", [" ".join(uids).encode()]
        uid = a[0]
        for rows in box.values():
            for u, m, raw in rows:
                if u == uid:
                    if isinstance(m, tuple):  # attributes on both sides of the literal
                        return "OK", [(m[0], raw), m[1]]
                    return "OK", [(m, raw), b")"]
        return "OK", [None]

    def logout(self, *a, **k):
        self.calls.append(("logout", a, k))
        self.loggedout = True
        return "BYE", [b""]

    def commands(self):
        return [c[0] for c in self.calls]


def run_imap(conn, cfg=JINX, signup=SIGNUP, out_dir=None):
    records = []
    with tempfile.TemporaryDirectory() as td:
        out = out_dir or Path(td) / "x.eml"
        with mock.patch.object(sc, "emit", lambda *a: records.append(a)), \
                mock.patch.dict(sc.R, {"requests": 0, "kinds": Counter(), "fh": io.StringIO()}), \
                mock.patch.object(sc, "utc_now", lambda: "2026-11-10T19:00:00Z"):
            part = sc.emails_imap(cfg, signup, CREDS, out, connect=lambda host, timeout=None: conn)
            requests = sc.R["requests"]
        files = sorted(p.name for p in out.glob("*.eml")) if out.exists() else None
        existed = out.exists()
    return part, records, requests, files, existed


class PureTests(unittest.TestCase):
    def test_imap_since_ignores_locale(self):
        self.assertEqual(sc.imap_since(datetime(2026, 11, 10, 15, 7, 32, tzinfo=timezone.utc)), "10-Nov-2026")
        self.assertEqual(sc.imap_since(datetime(2027, 3, 5, tzinfo=timezone.utc)), "05-Mar-2027")
        self.assertEqual(sc.imap_since(datetime(2027, 5, 31, tzinfo=timezone.utc)), "31-May-2027")

    def test_parse_fetch(self):
        gid, dt, labels = sc.parse_fetch(meta(1881484645376574926, labels='"\\\\Inbox" "\\\\Important" Work'))
        self.assertEqual(gid, format(1881484645376574926, "x"))
        self.assertEqual(dt, datetime(2026, 11, 10, 15, 13, 2, tzinfo=timezone.utc))
        self.assertEqual(labels, ["\\Inbox", "\\Important", "Work"])
        gid, dt, labels = sc.parse_fetch(b'1 (UID 3 INTERNALDATE " 5-Nov-2026 01:00:00 +0900" BODY[] {3}')
        self.assertEqual((gid, labels), (None, []))
        self.assertEqual(dt, datetime(2026, 11, 4, 16, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(sc.parse_fetch(b"garbage"), (None, None, []))

    def test_imap_folders_by_flag(self):
        self.assertEqual(sc.imap_folders(LIST_LINES), ("[Gmail]/Alle Nachrichten", "[Gmail]/Spam"))
        self.assertEqual(sc.imap_folders([b'(\\All) "/" Alles', (b'x', b'y')]), ("Alles", None))
        self.assertEqual(sc.imap_folders([b'(\\HasNoChildren) "/" "INBOX"']), (None, None))


class CredentialTests(unittest.TestCase):
    def creds(self, env, dotenv):
        with tempfile.TemporaryDirectory() as td:
            if dotenv is not None:
                (Path(td) / ".env").write_text(dotenv)
            with mock.patch.object(sc, "ROOT", Path(td)), mock.patch.dict(os.environ, env, clear=True):
                return sc.inbox_credentials()

    def test_env_first_then_dotenv(self):
        dot = f'APIFY_TOKEN=zzz\nINBOX_ADDRESS="{ADDRESS}"\nINBOX_APP_PASSWORD= "abcd efgh ijkl mnop" \n'
        self.assertEqual(self.creds({}, dot), (ADDRESS, "abcdefghijklmnop", "imap.gmail.com"))
        env = {"INBOX_ADDRESS": "other@example.org", "INBOX_IMAP_HOST": "imap.example.org"}
        self.assertEqual(self.creds(env, dot), ("other@example.org", "abcdefghijklmnop", "imap.example.org"))

    def test_none_without_both(self):
        self.assertIsNone(self.creds({}, None))
        self.assertIsNone(self.creds({"INBOX_ADDRESS": ADDRESS}, "INBOX_APP_PASSWORD=\n"))
        self.assertIsNone(self.creds({"INBOX_APP_PASSWORD": "x"}, ""))


class ImapRouteTests(unittest.TestCase):
    def one(self, uid="12", gid=1000, date="10-Nov-2026 15:13:02 +0000", **kw):
        raw = raw_message(**kw)
        return (uid, meta(gid, date, size=len(raw)), raw)

    def test_flow_is_read_only_and_peeks(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}, SPAM_Q: {}})
        part, recs, requests, files, _ = run_imap(conn)
        self.assertEqual(conn.commands(),
                         ["login", "list", "select", "uid SEARCH", "uid FETCH", "select", "uid SEARCH", "logout"])
        self.assertEqual(requests, len(conn.calls))
        self.assertEqual(conn.calls[0][1], (ADDRESS, PASSWORD_SQUEEZED))
        selects = [c for c in conn.calls if c[0] == "select"]
        self.assertEqual([c[1][0] for c in selects], [ALL_Q, SPAM_Q])
        self.assertTrue(all(c[2].get("readonly") is True for c in selects))
        search = next(c for c in conn.calls if c[0] == "uid SEARCH")
        self.assertEqual(search[1], (None, "FROM", '"thinkjinx.com"', "SINCE", "09-Nov-2026"))
        fetch = next(c for c in conn.calls if c[0] == "uid FETCH")
        self.assertEqual(fetch[1][0], "12")
        self.assertIn("BODY.PEEK[]", fetch[1][1])
        self.assertNotIn("BODY[]", fetch[1][1].replace("BODY.PEEK[]", ""))
        self.assertTrue(conn.loggedout)
        self.assertEqual((part["state"], part["reason"], part["route"]), ("ok", "", "imap"))
        self.assertEqual((part["messages"], part["in_window"], part["in_first_day"], part["before_signup"],
                          part["eml_invalid"], part["spam_checked"]), (1, 1, 1, 0, 0, True))
        self.assertEqual((part["signup_at"], part["first_day_ends_at"], part["fetched_at"]),
                         ("2026-11-10T15:12:32Z", "2026-11-11T15:12:32Z", "2026-11-10T19:00:00Z"))
        self.assertEqual((part["exported_at"], part["first_day_complete"], part["after_first_day"]), (None, None, None))
        self.assertEqual(files, [f"{format(1000, 'x')}.eml"])
        kind, key, url, fetched_at, raw = recs[0]
        self.assertEqual((kind, key, url, fetched_at), ("email", "email/3e8", SIGNUP["signup_url"], "2026-11-10T19:00:00Z"))
        self.assertEqual(raw["route"], "imap")
        self.assertEqual((raw["folder"], raw["in_first_day"], raw["redaction"], raw["spam_checked"]),
                         ("all", True, "strict", True))
        self.assertEqual(raw["file"], "3e8.eml")
        self.assertEqual(raw["sha256"], hashlib.sha256(raw["eml"].encode("ascii")).hexdigest())
        self.assertEqual((raw["signup_at"], raw["first_day_ends_at"]), (part["signup_at"], part["first_day_ends_at"]))
        self.assertNotIn(ADDRESS, json.dumps(recs))
        self.assertIn("strict: plain text only (from html)", raw["eml"].replace("\r\n ", " "))
        self.assertNotIn("aabbccddeeff", raw["eml"])
        self.assertNotIn("<a", raw["eml"])

    def test_message_in_both_folders_and_two_domains_is_one_record(self):
        row = self.one(sender="support@mail.thinkjinx.com")
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [row], "mail.thinkjinx.com": [row]},
                         SPAM_Q: {"thinkjinx.com": [row]}})
        cfg = {"email_sender_domains": ["thinkjinx.com", "mail.thinkjinx.com"]}
        part, recs, _, files, _ = run_imap(conn, cfg=cfg)
        self.assertEqual(len(recs), 1)
        self.assertEqual((part["messages"], part["in_window"]), (1, 1))
        self.assertEqual(recs[0][4]["folder"], "all")
        self.assertEqual(len(files), 1)

    def test_before_signup_is_counted_not_written(self):
        # signup_at - 300 s = 15:07:32
        early = self.one("1", 1, "10-Nov-2026 15:07:31 +0000")
        edge = self.one("2", 2, "10-Nov-2026 15:07:32 +0000")
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [early, edge]}, SPAM_Q: {}})
        part, recs, _, files, _ = run_imap(conn)
        self.assertEqual((part["before_signup"], part["in_window"], part["messages"]), (1, 1, 2))
        self.assertEqual(files, ["2.eml"])
        self.assertEqual([r[1] for r in recs], ["email/2"])
        since = next(c for c in conn.calls if c[0] == "uid SEARCH")[1][4]
        # start = 15:07:32 on the 10th, minus one day = the 9th
        self.assertEqual(since, "09-Nov-2026")

    def test_after_first_day_is_kept_and_flagged(self):
        late = self.one("1", 5, "11-Nov-2026 15:12:32 +0000")
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [late]}, SPAM_Q: {}})
        part, recs, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["in_window"], part["in_first_day"]), ("ok", 1, 0))
        self.assertFalse(recs[0][4]["in_first_day"])

    def test_verified_sender_uses_verified_level_and_spam_folder(self):
        raw = raw_message(sender="hello@livingproof.com", both=True,
                          body="Shop https://www.livingproof.com/products/shampoo now")
        row = ("7", meta(77, size=len(raw)), raw)
        conn = FakeConn({ALL_Q: {}, SPAM_Q: {"livingproof.com": [row]}})
        cfg = {"email_sender_domains": ["livingproof.com"]}
        part, recs, *_ = run_imap(conn, cfg=cfg)
        self.assertEqual(part["state"], "ok")
        self.assertEqual((recs[0][4]["redaction"], recs[0][4]["folder"]), ("verified", "spam"))
        self.assertIn("/products/shampoo", recs[0][4]["eml"])

    def test_records_are_ordered_by_time_then_id(self):
        rows = [self.one("1", 0xb, "10-Nov-2026 16:00:00 +0000"), self.one("2", 0xa, "10-Nov-2026 15:30:00 +0000"),
                self.one("3", 0x9, "10-Nov-2026 16:00:00 +0000")]
        conn = FakeConn({ALL_Q: {"thinkjinx.com": rows}, SPAM_Q: {}})
        _, recs, *_ = run_imap(conn)
        self.assertEqual([r[1] for r in recs], ["email/a", "email/9", "email/b"])

    def test_other_senders_in_the_search_are_skipped_silently(self):
        other = self.one("1", 1, sender="news@elsewhere.test")
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [other]}, SPAM_Q: {}})
        part, recs, _, files, _ = run_imap(conn)
        self.assertEqual((part["state"], part["in_window"], part["eml_invalid"], len(recs)), ("ok", 0, 0, 0))
        self.assertEqual((part["messages"], part["before_signup"]), (0, 0))
        self.assertFalse(files)

    def test_substring_sender_is_not_counted(self):
        # the server's FROM search is a substring match: notthinkjinx.com comes back for thinkjinx.com
        other = self.one("1", 1, "01-Nov-2026 10:00:00 +0000", sender="a@notthinkjinx.com")
        broken = ("2", meta(2), b"")
        mine = self.one("3", 3)
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [other, broken, mine]}, SPAM_Q: {}})
        part, recs, *_ = run_imap(conn)
        self.assertEqual((part["messages"], part["before_signup"], part["eml_invalid"], part["in_window"]),
                         (1, 0, 0, 1))
        self.assertEqual([r[1] for r in recs], ["email/3"])

    def test_attributes_after_the_literal(self):
        raw = raw_message()
        head = b'1 (UID 12 BODY[] {%d}' % len(raw)
        tail = b' X-GM-MSGID 1000 X-GM-LABELS ("\\\\Inbox") INTERNALDATE "10-Nov-2026 15:13:02 +0000" )'
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [("12", (head, tail), raw)]}, SPAM_Q: {}})
        part, recs, *_ = run_imap(conn)
        self.assertEqual((part["messages"], part["eml_invalid"], part["in_window"]), (1, 0, 1))
        self.assertEqual(recs[0][1], "email/3e8")
        self.assertIn("15:13:02", recs[0][4]["eml"])

    def test_timeout_reaches_connect(self):
        seen = {}

        def connect(host, **kw):
            seen.update(kw, host=host)
            return FakeConn({ALL_Q: {}, SPAM_Q: {}})

        with tempfile.TemporaryDirectory() as td, mock.patch.object(sc, "emit", lambda *a: None), \
                mock.patch.dict(sc.R, {"requests": 0}):
            sc.emails_imap(JINX, SIGNUP, CREDS, Path(td) / "x.eml", connect=connect)
        self.assertEqual(sc.IMAP_TIMEOUT_S, 60)
        self.assertEqual(seen, {"host": HOST, "timeout": 60})

    def test_timeout_during_a_command_is_an_error(self):
        conn = FakeConn({ALL_Q: {}}, fail=("list", TimeoutError("timed out")))
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_error: TimeoutError"))

    def test_since_is_one_day_early_and_exact_time_decides(self):
        # signup 2026-11-10T23:57:00Z + 5 min... use 2026-11-11T00:02:00Z: start = 2026-11-10 23:57:00,
        # minus one day = 2026-11-09 23:57:00 -> SINCE 09-Nov-2026
        sign = dict(SIGNUP, signup_at="2026-11-11T00:02:00Z")
        early = self.one("1", 1, "10-Nov-2026 23:56:59 +0000")
        inside = self.one("2", 2, "10-Nov-2026 23:58:00 +0000")  # day before the signup, after start
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [early, inside]}, SPAM_Q: {}})
        part, recs, *_ = run_imap(conn, signup=sign)
        self.assertEqual(next(c for c in conn.calls if c[0] == "uid SEARCH")[1][4], "09-Nov-2026")
        self.assertEqual((part["before_signup"], part["in_window"], part["messages"]), (1, 1, 2))
        self.assertEqual([r[1] for r in recs], ["email/2"])

    def test_since_for_a_signup_just_after_midnight(self):
        # signup 2026-11-11T00:12:00Z: start = 00:07:00 on the 11th, minus one day = the 10th
        sign = dict(SIGNUP, signup_at="2026-11-11T00:12:00Z")
        conn = FakeConn({ALL_Q: {"thinkjinx.com": []}, SPAM_Q: {}})
        run_imap(conn, signup=sign)
        self.assertEqual(next(c for c in conn.calls if c[0] == "uid SEARCH")[1][4], "10-Nov-2026")

    def test_junk_select_raising_keeps_all_mail(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}}, select_raises=(SPAM_Q,))
        part, recs, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"], part["spam_checked"], len(recs)),
                         ("partial", "spam_not_checked", False, 1))

    def test_noselect_folders_are_ignored(self):
        lines = [b'(\\Noselect \\All) "/" "[Gmail]"'] + LIST_LINES + [b'(\\Noselect \\Junk) "/" "Dead"']
        self.assertEqual(sc.imap_folders(lines), ("[Gmail]/Alle Nachrichten", "[Gmail]/Spam"))
        only = [b'(\\Noselect \\All) "/" "[Gmail]"']
        conn = FakeConn({}, list_lines=only)
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_no_all_folder"))

    def test_redaction_failure_is_counted_and_partial(self):
        bad = self.one("1", 1, subject="Hi radar.inbox77")
        good = self.one("2", 2)
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [bad, good]}, SPAM_Q: {}})
        part, recs, _, files, _ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"], part["eml_invalid"], part["in_window"]),
                         ("partial", "eml_invalid=1", 1, 1))
        self.assertEqual(files, ["2.eml"])
        self.assertEqual(len(recs), 1)

    def test_unparseable_message_is_counted(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [("1", meta(1), b"")]}, SPAM_Q: {}})
        part, recs, *_ = run_imap(conn)
        # no From can be read: skipped silently, counted nowhere
        self.assertEqual((part["state"], part["messages"], part["eml_invalid"], len(recs)), ("ok", 0, 0, 0))

    def test_no_junk_folder_leaves_spam_unchecked(self):
        lines = [l for l in LIST_LINES if b"Junk" not in l]
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}}, list_lines=lines)
        part, recs, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"], part["spam_checked"]), ("partial", "spam_not_checked", False))
        self.assertEqual(recs[0][4]["spam_checked"], False)
        self.assertEqual(conn.commands().count("select"), 1)

    def test_failing_junk_select_leaves_spam_unchecked(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}}, bad_select=(SPAM_Q,))
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("partial", "spam_not_checked"))

    def test_no_all_folder(self):
        conn = FakeConn({}, list_lines=[b'(\\HasNoChildren) "/" "INBOX"'])
        part, recs, _, _, existed = run_imap(conn)
        self.assertEqual((part["state"], part["reason"], len(recs), existed), ("could_not_look", "imap_no_all_folder", 0, False))
        self.assertTrue(conn.loggedout)

    def test_all_folder_select_refused(self):
        conn = FakeConn({}, bad_select=(ALL_Q,))
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_error: select"))

    def test_dropped_connection_during_login_is_not_a_refusal(self):
        conn = FakeConn({}, login_error=imaplib.IMAP4.abort("x"))
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_error: abort"))

    def test_login_refused_names_nothing(self):
        err = imaplib.IMAP4.error(f"[AUTHENTICATIONFAILED] {ADDRESS} {PASSWORD_SQUEEZED} {HOST}")
        conn = FakeConn({}, login_error=err)
        part, recs, requests, _, existed = run_imap(conn)
        self.assertEqual((part["state"], part["reason"], recs, existed), ("could_not_look", "imap_login_failed", [], False))
        self.assertEqual(conn.commands(), ["login", "logout"])
        blob = json.dumps(part)
        for secret in (ADDRESS, "radar.inbox77", PASSWORD_SQUEEZED, HOST):
            self.assertNotIn(secret, blob)
        self.assertIsNone(part["exported_at"])

    def test_connect_failure_gives_type_name_only(self):
        def connect(host, timeout=None):
            raise OSError(f"cannot reach {host} for {ADDRESS}")

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(sc, "emit", lambda *a: None), \
                mock.patch.dict(sc.R, {"requests": 0}):
            part = sc.emails_imap(JINX, SIGNUP, CREDS, Path(td) / "x.eml", connect=connect)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_error: OSError"))
        self.assertNotIn(ADDRESS, json.dumps(part))

    def test_search_status_not_ok(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": []}}, search_status="NO")
        part, *_ = run_imap(conn)
        self.assertEqual((part["state"], part["reason"]), ("could_not_look", "imap_error: search"))

    def test_error_after_records_keeps_them_and_is_partial(self):
        cfg = {"email_sender_domains": ["thinkjinx.com", "mail.thinkjinx.com"]}
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}, SPAM_Q: {}})
        real = conn.uid
        n = {"search": 0}

        def uid(command, *a, **k):
            if command == "SEARCH":
                n["search"] += 1
                if n["search"] == 2:
                    raise ConnectionResetError(f"reset {ADDRESS}")
            return real(command, *a, **k)

        conn.uid = uid
        part, recs, *_ = run_imap(conn, cfg=cfg)
        self.assertEqual((part["state"], part["reason"], len(recs)), ("partial", "imap_error: ConnectionResetError", 1))
        self.assertFalse(part["spam_checked"])
        self.assertTrue(conn.loggedout)
        self.assertNotIn(ADDRESS, json.dumps(part))

    def test_logout_error_is_ignored(self):
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [self.one()]}, SPAM_Q: {}})

        def bad_logout():
            raise OSError("closed")

        conn.logout = bad_logout
        part, *_ = run_imap(conn)
        self.assertEqual(part["state"], "ok")

    def test_id_without_gmail_extension_is_a_hash(self):
        raw = raw_message()
        m = b'1 (UID 12 INTERNALDATE "10-Nov-2026 15:13:02 +0000" BODY[] {5}'
        conn = FakeConn({ALL_Q: {"thinkjinx.com": [("12", m, raw)]}, SPAM_Q: {}})
        _, recs, *_ = run_imap(conn)
        self.assertEqual(recs[0][1], "email/" + hashlib.sha256(raw).hexdigest()[:16])


class EmailsStepTests(unittest.TestCase):
    LP = {"email_sender_domains": ["livingproof.com"]}

    def step(self, cfg, name, creds, imap_result=None):
        records = []
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(sc, "emit", lambda *a: records.append(a)), \
                mock.patch.object(sc, "inbox_credentials", lambda: creds), \
                mock.patch.object(sc, "emails_imap", return_value=imap_result) as imap:
            part = sc.emails_step(cfg, name, Path(td) / "x.eml")
        return part, records, imap

    def test_no_credentials_runs_the_old_route(self):
        part, recs, imap = self.step(self.LP, "Living Proof", None)
        imap.assert_not_called()
        self.assertEqual(part, {
            "state": "partial", "reason": "first_day_not_over(covered=2.65h); spam_not_checked",
            "route": "inbox_export",
            "signup_at": "2026-11-10T04:47:06Z", "first_day_ends_at": "2026-11-11T04:47:06Z",
            "exported_at": "2026-11-10T07:26:17Z", "first_day_complete": False, "spam_checked": False,
            "in_window": 1, "before_signup": 0, "after_first_day": 0, "eml_invalid": 0})
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0][4]["route"], "inbox_export")
        self.assertEqual(recs[0][1], "email/1a1c3c946076193d")

    def test_credentials_use_imap_and_never_the_files(self):
        sentinel = {"state": "ok", "route": "imap"}
        part, recs, imap = self.step(self.LP, "Living Proof", CREDS, sentinel)
        self.assertIs(part, sentinel)
        self.assertEqual(recs, [])
        args = imap.call_args[0]
        self.assertEqual(args[0], self.LP)
        self.assertEqual(args[1]["brand"], "Living Proof")
        self.assertEqual(args[2], CREDS)
        self.assertEqual(args[3].name, "x.eml")

    def test_early_checks_come_first_on_both_routes(self):
        for creds, route in ((CREDS, "imap"), (None, "inbox_export")):
            for cfg, name, reason in (
                    (self.LP, "Nobody", "no_signup_entry"),
                    ({"email_sender_domains": []}, "Living Proof", "sender_domains_unknown"),
                    ):
                part, recs, imap = self.step(cfg, name, creds, {"state": "x"})
                self.assertEqual((part["state"], part["reason"], part["route"]), ("could_not_look", reason, route))
                imap.assert_not_called()
                self.assertEqual(recs, [])
        signups = {"signups": [{"brand": "Z", "status": "not_signed_up", "signup_at": None, "signup_url": "u"}]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            p.write_text(json.dumps(signups))
            with mock.patch.object(sc, "SIGNUPS_JSON", p):
                part, _, imap = self.step(self.LP, "Z", CREDS, {"state": "x"})
        self.assertEqual((part["state"], part["reason"], part["route"]),
                         ("could_not_look", "not_signed_up(status=not_signed_up)", "imap"))
        imap.assert_not_called()


class DataTests(unittest.TestCase):
    def test_batiste_and_jinx_inputs(self):
        inputs = json.loads((COLLECTOR / "brand_inputs.json").read_text())
        self.assertEqual(inputs["batiste"]["email_sender_domains"], ["tintcommunities.com"])
        self.assertEqual(inputs["jinx"]["email_sender_domains"], ["thinkjinx.com"])
        signups = {s["brand"]: s for s in json.loads(sc.SIGNUPS_JSON.read_text())["signups"]}
        b, j = signups["Batiste"], signups["Jinx"]
        self.assertEqual((b["status"], b["signup_at"], b["first_email_at"]),
                         ("submitted_unconfirmed", "2026-11-10T15:13:02Z", "2026-11-10T15:13:02Z"))
        self.assertEqual((j["status"], j["signup_at"], j["first_email_at"]),
                         ("signed_up", "2026-11-10T15:12:32Z", "2026-11-10T15:12:32Z"))
        self.assertEqual(b["signup_url"], "https://batistenation.socialmedialink.com/")
        self.assertIsNone(b["offer_text"])
        self.assertIsNone(j["offer_text"])
        for s in (b, j):
            self.assertIn("arrival time of the first mail", s["result"])


if __name__ == "__main__":
    unittest.main()
