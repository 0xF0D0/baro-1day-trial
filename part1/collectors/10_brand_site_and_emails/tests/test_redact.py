import base64
import json
import re
import sys
import unittest
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import redact_eml  # noqa: E402

INBOX = "radar.inbox77@example.org"
LOCAL = "radar.inbox77"
RECEIVED = datetime(2026, 11, 10, 15, 12, 32, tzinfo=timezone.utc)
INTERNAL_MS = str(int(RECEIVED.timestamp() * 1000))
TOKEN = "AbCdEfGhIjKlMnOpQrStUv123456"


def klaviyo_message():
    m = EmailMessage()
    m["From"] = "Shop <news@livingproof.com>"
    m["To"] = f"Radar <{INBOX}>"
    m["Subject"] = "Welcome"
    m["Date"] = "Tue, 10 Nov 2026 15:12:00 +0000"
    m["Message-ID"] = "<abc123@mail.livingproof.com>"
    m["List-Unsubscribe"] = f"<https://manage.kmail-lists.com/unsub?u={TOKEN}&x=1>, <mailto:u@x.com>"
    m["Received"] = f"from mx by {INBOX}"
    m.set_content(
        f"Hi\nhttps://ctrk.klclick.com/l/{TOKEN}\nhttps://ctrk.klclick.com/o/{TOKEN}\n"
        "https://manage.kmail-lists.com/prefs?id=abcdefghijkl\nhttps://livingproof.com/products/shampoo?v=1\n")
    m.add_alternative(
        f'<p><a href="https://ctrk.klclick.com/l/{TOKEN}">go</a>'
        '<a href="https://livingproof.com/products/shampoo">buy</a></p>', subtype="html")
    return m.as_bytes()


def connector_json(src):
    return {"id": "gm1", "internalDate": INTERNAL_MS, "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"],
            "raw": base64.urlsafe_b64encode(src).decode()}


def parse(data):
    return BytesParser(policy=policy.default).parsebytes(data)


def strict(src, inbox=INBOX, **kw):
    return redact_eml.redact_message(src, "gm1", RECEIVED, ["INBOX"], inbox=inbox, strict=True, **kw)


def other_message(plain="Hello\n", html=None, extra=None, subject="Hi", to=INBOX,
                  reply_to="reply@other.example"):
    m = EmailMessage()
    m["From"] = "Other <hi@other.example>"
    if to is not None:
        m["To"] = to
    m["Reply-To"] = reply_to
    m["Subject"] = subject
    m["Date"] = "Tue, 10 Nov 2026 15:12:00 +0000"
    m["Message-ID"] = "<secret-mid-9f8e7d@other.example>"
    m["X-Custom"] = "keepme"
    if plain is not None:
        m.set_content(plain)
        if html is not None:
            m.add_alternative(html, subtype="html")
    else:
        m.set_content(html, subtype="html")
    if extra:
        m.add_attachment(b"data", maintype="application", subtype="pdf", filename="a.pdf")
    return m.as_bytes()


# Output of the pre-refactor convert() on klaviyo_message(), recorded before the change.
# The MIME boundary is random per call, so it is normalised in both sides.
EXPECTED_NONSTRICT = (
    b'From: Shop <news@livingproof.com>\r\n'
    b'Subject: Welcome\r\n'
    b'Date: Tue, 10 Nov 2026 15:12:00 +0000\r\n'
    b'Message-ID: <abc123@mail.livingproof.com>\r\n'
    b'MIME-Version: 1.0\r\n'
    b'To: TRIAL_INBOX <trial_inbox@redacted.invalid>\r\n'
    b'List-Unsubscribe: <https://manage.kmail-lists.com/unsub?REDACTED>\r\n'
    b'X-Trial-Gmail-Id: gm1\r\n'
    b'X-Trial-Received-At: 2026-11-10T15:12:32Z\r\n'
    b'X-Trial-Gmail-Labels: INBOX, CATEGORY_PROMOTIONS\r\n'
    b'Content-Type: multipart/alternative;\r\n'
    b' boundary="=BOUNDARY="\r\n'
    b'X-Trial-Redaction: Receiving-path headers dropped; To replaced; per-recipient\r\n'
    b' tracking tokens replaced (3 tracking, 1 unsubscribe/manage). Body text\r\n'
    b' otherwise unchanged; parts re-encoded as quoted-printable.\r\n'
    b'\r\n'
    b'--=BOUNDARY=\r\n'
    b'Content-Type: text/plain; charset="utf-8"\r\n'
    b'Content-Transfer-Encoding: quoted-printable\r\n'
    b'\r\n'
    b'Hi\r\n'
    b'https://ctrk.klclick.com/l/REDACTED\r\n'
    b'https://ctrk.klclick.com/o/REDACTED\r\n'
    b'https://manage.kmail-lists.com/prefs?REDACTED\r\n'
    b'https://livingproof.com/products/shampoo?v=3D1\r\n'
    b'\r\n'
    b'--=BOUNDARY=\r\n'
    b'Content-Type: text/html; charset="utf-8"\r\n'
    b'Content-Transfer-Encoding: quoted-printable\r\n'
    b'MIME-Version: 1.0\r\n'
    b'\r\n'
    b'<p><a href=3D"https://ctrk.klclick.com/l/REDACTED">go</a><a href=3D"https://l=\r\n'
    b'ivingproof.com/products/shampoo">buy</a></p>\r\n'
    b'\r\n'
    b'--=BOUNDARY=--\r\n'
)


def norm(data):
    return re.sub(rb"={15}\d+==", b"=BOUNDARY=", data)


class VerifiedLevel(unittest.TestCase):
    def test_nonstrict_matches_old_convert_bytes(self):
        out, counts = redact_eml.redact_message(klaviyo_message(), "gm1", RECEIVED,
                                                ["INBOX", "CATEGORY_PROMOTIONS"], strict=False)
        self.assertEqual(norm(out), EXPECTED_NONSTRICT)

    def test_replacements_and_product_link_kept(self):
        out, counts = redact_eml.redact_message(klaviyo_message(), "gm1", RECEIVED, ["INBOX"], strict=False)
        t = out.decode("ascii")
        self.assertNotIn(TOKEN, t)
        self.assertIn("/l/REDACTED", t)
        self.assertIn("/o/REDACTED", t)
        self.assertIn("?REDACTED", t)
        self.assertIn("https://livingproof.com/products/shampoo", t.replace("=\r\n", ""))
        self.assertEqual(counts["tracking"], 3)

    def test_inbox_override(self):
        out, _ = redact_eml.redact_message(klaviyo_message(), "gm1", RECEIVED, [], inbox=INBOX.upper())
        self.assertNotIn(LOCAL, out.decode("ascii").lower())

    def test_missing_part_raises(self):
        with self.assertRaises(redact_eml.RedactionError):
            redact_eml.redact_message(other_message(plain=None, html="<p>x</p>"), "gm1", RECEIVED, [])

    def test_unexpected_part_raises(self):
        with self.assertRaises(redact_eml.RedactionError):
            redact_eml.redact_message(other_message(plain="a", html="<p>a</p>", extra=True), "gm1", RECEIVED, [])

    def test_subject_with_local_part_raises(self):
        src = klaviyo_message().replace(b"Subject: Welcome", f"Subject: hi {LOCAL}".encode())
        with self.assertRaises(redact_eml.RedactionError):
            redact_eml.redact_message(src, "gm1", RECEIVED, [])

    def test_convert_still_writes_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.json"
            p.write_text(json.dumps(connector_json(klaviyo_message())))
            name, counts, a, b = redact_eml.convert(str(p), d)
            self.assertEqual(norm((Path(d) / name).read_bytes()), EXPECTED_NONSTRICT)


def body(out):
    """Decoded text of the single text/plain part of a strict output."""
    msg = parse(out)
    assert msg.get_content_type() == "text/plain", msg.get_content_type()
    return msg.get_content()


def raw(extra_headers="", body_text="hi\r\n", ctype="text/plain; charset=utf-8", cte="8bit", subject="Hi"):
    return (f"From: Other <hi@other.example>\r\nTo: {INBOX}\r\nSubject: {subject}\r\n"
            f"Date: Tue, 10 Nov 2026 15:12:00 +0000\r\nMIME-Version: 1.0\r\n{extra_headers}"
            f"Content-Type: {ctype}\r\nContent-Transfer-Encoding: {cte}\r\n\r\n{body_text}").encode()


class StrictLevel(unittest.TestCase):
    def cut(self, text):
        out, counts = strict(other_message(plain=text))
        return body(out), counts

    def test_link_with_brackets_and_quotes_in_path(self):
        for link in ("https://h.example/a(b)?token=TOK", "https://h.example/a?x=it's&t=TOK",
                     "https://h.example/a[1]?t=TOK"):
            with self.subTest(link=link):
                b, counts = self.cut(f"see ({link}) and [{link}] end\n")
                for s in ("TOK", "(b)", "[1]", "it's"):
                    self.assertNotIn(s, b)
                self.assertIn("https://h.example/REDACTED", b)
                self.assertGreaterEqual(counts["urls"], 2)

    def test_host_only_forms_are_left(self):
        b, counts = self.cut("a https://h.example b https://h.example/ c\n")
        self.assertIn("a https://h.example b https://h.example/ c", b)
        self.assertEqual(counts["urls"], 0)

    def test_odd_host_tails(self):
        for link in ("https://h.example\\TOK", "https://h.example|TOK", "https://h.example,TOK",
                     "https://TOK@h.example", "https://h.example:8443/x?TOK", "HTTPS://H.EXAMPLE/x?TOK"):
            with self.subTest(link=link):
                b, counts = self.cut(f"go {link} now\n")
                self.assertNotIn("TOK", b)
                self.assertEqual(counts["urls"], 1)

    def test_schemeless_links(self):
        b, counts = self.cut("a //h.example/p?TOK b www.h.example/p?TOK c\n")
        self.assertNotIn("TOK", b)
        self.assertIn("h.example/REDACTED", b)
        self.assertIn("www.h.example/REDACTED", b)
        self.assertEqual(counts["urls"], 2)

    def test_mailto_and_bare_address(self):
        b, counts = self.cut("a mailto:reply+TOK@h.example?subject=x b reply+TOK@h.example c\n")
        self.assertNotIn("TOK", b)
        self.assertIn("mailto:REDACTED", b)
        self.assertIn("REDACTED@h.example", b)
        self.assertEqual(counts["urls"], 1)
        self.assertEqual(counts["addresses"], 1)

    def test_inbox_address_in_every_form(self):
        text = (f"Hi {LOCAL},\nlower {INBOX} upper {INBOX.upper()}\n"
                f"link https://h.example/u?e=radar.inbox77%40example.org end\n"
                f"loose radar.inbox77%40example.org\n")
        out, counts = strict(other_message(plain=text))
        b = body(out)
        self.assertNotIn(LOCAL, b.lower())
        self.assertNotIn(LOCAL.encode(), out.lower())
        self.assertIn("Hi TRIAL_INBOX,", b)
        self.assertIn("lower TRIAL_INBOX upper TRIAL_INBOX", b)
        self.assertIn("https://h.example/REDACTED", b)
        self.assertEqual(counts["addresses"], 4)

    def test_html_only_becomes_plain_text(self):
        html = ('<html><head><title>TITLEWORD</title><style>.x{color:red}</style></head><body>'
                '<script>var s="SCRIPTVAL";</script><p>Hello <a href="https://h.example/p?TOK">visible words</a></p>'
                '<div>Second line</div></body></html>')
        out, counts = strict(other_message(plain=None, html=html))
        msg = parse(out)
        self.assertEqual(msg.get_content_type(), "text/plain")
        self.assertFalse(msg.is_multipart())
        b = msg.get_content()
        self.assertIn("Hello visible words", b)
        self.assertIn("Second line", b)
        for s in ("<", ">", "href", "TOK", "SCRIPTVAL", "color:red", "TITLEWORD"):
            self.assertNotIn(s, b)
        self.assertEqual(counts["source"], "html")
        self.assertEqual(counts["parts_dropped"], 0)
        self.assertNotIn(b"text/html", out)

    def test_html_address_with_entities(self):
        out, _ = strict(other_message(plain=None, html="<p>Mail radar&#46;inbox77&#64;example.org now</p>"))
        self.assertIn("Mail TRIAL_INBOX now", body(out))
        self.assertNotIn(LOCAL.encode(), out.lower())

    def test_html_address_split_by_tags(self):
        out, _ = strict(other_message(plain=None, html="<p>radar.<b>inbox77</b>@example.org</p>"))
        self.assertNotIn(LOCAL, body(out).lower())
        self.assertNotIn(LOCAL.encode(), out.lower())

    def test_both_parts_plain_is_used(self):
        out, counts = strict(other_message(plain="plain words\n", html="<p>html words</p>"))
        self.assertEqual(counts["source"], "plain")
        self.assertEqual(counts["html_not_kept"], 1)
        self.assertEqual(counts["parts_dropped"], 0)
        self.assertNotIn(b"text/html", out)
        self.assertIn("plain words", body(out))
        self.assertNotIn("html words", body(out))

    def test_headers_reduced(self):
        out, _ = strict(other_message(reply_to="<reply+TOK@h.example>"))
        msg = parse(out)
        for h in ("Message-ID", "Reply-To", "X-Custom", "List-Unsubscribe"):
            self.assertIsNone(msg[h])
        for h in ("From", "Subject", "Date", "MIME-Version"):
            self.assertIsNotNone(msg[h])
        self.assertNotIn(b"TOK", out)
        self.assertNotIn(b"secret-mid", out)

    def test_attachment_dropped_and_counted(self):
        out, counts = strict(other_message(plain="a\n", html="<p>a</p>", extra=True))
        self.assertEqual(counts["parts_dropped"], 1)
        self.assertNotIn(b"a.pdf", out)
        self.assertIn("1 part(s) dropped", str(parse(out)["X-Trial-Redaction"]))

    def test_unknown_charset_raises_fixed_text(self):
        with self.assertRaises(redact_eml.RedactionError) as cm:
            strict(raw(ctype="text/plain; charset=bogus"))
        self.assertNotIn("bogus", str(cm.exception))

    def test_duplicated_subject_uses_first(self):
        out, _ = strict(raw(extra_headers="Subject: second\r\n", subject="first"))
        self.assertEqual(str(parse(out)["Subject"]), "first")

    def test_no_to_and_no_inbox_raises(self):
        with self.assertRaises(redact_eml.RedactionError):
            strict(other_message(to=None), inbox=None)

    def test_no_text_part_raises(self):
        m = EmailMessage()
        m["From"] = "a@other.example"
        m["To"] = INBOX
        m["Subject"] = "x"
        m.set_content(b"data", maintype="application", subtype="pdf")
        with self.assertRaises(redact_eml.RedactionError):
            strict(m.as_bytes())

    def test_address_in_subject_raises(self):
        for subject in (f"for {INBOX}", f"for {LOCAL}"):
            with self.subTest(subject=subject), self.assertRaises(redact_eml.RedactionError):
                strict(other_message(subject=subject))

    def test_redaction_text(self):
        out, _ = strict(other_message(plain="https://a.example/x/y and a@b.example\n"))
        self.assertEqual(str(parse(out)["X-Trial-Redaction"]),
                         "strict: plain text only (from plain); headers reduced; To replaced; "
                         "1 link(s) cut; 1 address(es) replaced; 0 part(s) dropped.")


class Output(unittest.TestCase):
    def check(self, out):
        self.assertEqual(out, out.decode("ascii").encode("ascii"))
        self.assertIn(b"\r\n", out)
        self.assertNotIn(b"\n", out.replace(b"\r\n", b""))
        msg = parse(out)
        self.assertEqual(str(msg["X-Trial-Gmail-Id"]), "gm1")
        self.assertRegex(str(msg["X-Trial-Received-At"]), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(str(msg["X-Trial-Received-At"]), "2026-11-10T15:12:32Z")
        self.assertEqual(str(msg["To"]), "TRIAL_INBOX <trial_inbox@redacted.invalid>")
        self.assertIsNotNone(msg["X-Trial-Redaction"])

    def test_both_levels(self):
        self.check(redact_eml.redact_message(klaviyo_message(), "gm1", RECEIVED, ["INBOX"])[0])
        self.check(strict(other_message(plain="a\n", html="<p>a</p>", subject="Gr\u00fc\u00dfe \u2713"))[0])

    def test_read_eml_accepts(self):
        import tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import source_collector
        for out in (redact_eml.redact_message(klaviyo_message(), "gm1", RECEIVED, [])[0],
                    strict(other_message())[0]):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "x.eml"
                p.write_bytes(out)
                self.assertIsNotNone(source_collector.read_eml(p, "gm1"))


if __name__ == "__main__":
    unittest.main()
