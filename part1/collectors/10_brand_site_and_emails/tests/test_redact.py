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


def other_message(plain="Hello\n", html=None, extra=None, subject="Hi", to=INBOX):
    m = EmailMessage()
    m["From"] = "Other <hi@other.example>"
    m["To"] = to
    m["Reply-To"] = "reply@other.example"
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
EXPECTED_NONSTRICT_TEMPLATE = (
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


EXPECTED_NONSTRICT = EXPECTED_NONSTRICT_TEMPLATE


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


class StrictLevel(unittest.TestCase):
    def test_urls_cut_to_host(self):
        html = (f'<a href="https://t.other.example/click/{TOKEN}/x">a</a>'
                f'<a href="https://t.other.example/c?uid={TOKEN}&amp;z=1">b</a>')
        out, counts = strict(other_message(plain=f"see https://t.other.example/p/{TOKEN}\n", html=html))
        t = out.decode("ascii")
        self.assertNotIn(TOKEN, t.replace("=\r\n", ""))
        self.assertIn("https://t.other.example/REDACTED", t.replace("=\r\n", ""))
        self.assertEqual(counts["urls"], 3)

    def test_bare_host_not_counted(self):
        out, counts = strict(other_message(plain="https://example.com and https://example.com/ ok\n"))
        self.assertEqual(counts["urls"], 0)
        self.assertIn("https://example.com/ ok", out.decode("ascii"))

    def test_address_and_local_part_replaced(self):
        out, _ = strict(other_message(plain=f"Hi {LOCAL.upper()},\nSent to {INBOX.upper()}.\n"))
        body = parse(out).get_body().get_content()
        self.assertIn("Hi TRIAL_INBOX,", body)
        self.assertIn("Sent to TRIAL_INBOX.", body)

    def test_headers_reduced(self):
        out, _ = strict(other_message())
        msg = parse(out)
        for h in ("Message-ID", "X-Custom", "List-Unsubscribe"):
            self.assertIsNone(msg[h])
        for h in ("From", "Reply-To", "Subject", "Date", "MIME-Version"):
            self.assertIsNotNone(msg[h])
        self.assertEqual(str(msg["To"]), "TRIAL_INBOX <trial_inbox@redacted.invalid>")
        self.assertNotIn("secret-mid", out.decode("ascii"))

    def test_html_only(self):
        out, counts = strict(other_message(plain=None, html="<p>hi</p>"))
        msg = parse(out)
        self.assertEqual(msg.get_content_type(), "text/html")
        self.assertEqual(counts["parts_dropped"], 0)

    def test_plain_only(self):
        out, _ = strict(other_message(plain="hi\n"))
        self.assertEqual(parse(out).get_content_type(), "text/plain")

    def test_attachment_dropped_and_counted(self):
        out, counts = strict(other_message(plain="a\n", html="<p>a</p>", extra=True))
        self.assertEqual(counts["parts_dropped"], 1)
        self.assertNotIn("a.pdf", out.decode("ascii"))
        self.assertIn("1 part(s) dropped", str(parse(out)["X-Trial-Redaction"]))

    def test_no_text_part_raises(self):
        m = EmailMessage()
        m["From"] = "a@other.example"
        m["To"] = INBOX
        m["Subject"] = "x"
        m.set_content(b"data", maintype="application", subtype="pdf")
        with self.assertRaises(redact_eml.RedactionError):
            strict(m.as_bytes())

    def test_subject_with_local_part_raises(self):
        with self.assertRaises(redact_eml.RedactionError):
            strict(other_message(subject=f"for {LOCAL}"))

    def test_redaction_text(self):
        out, _ = strict(other_message(plain="https://a.example/x/y\n"))
        self.assertEqual(str(parse(out)["X-Trial-Redaction"]),
                         "strict: headers reduced; To replaced; 1 URL(s) cut to host; 0 part(s) dropped.")


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
        self.check(strict(other_message(plain="a\n", html="<p>a</p>"))[0])

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

    def test_constants(self):
        self.assertEqual(redact_eml.VERIFIED_DOMAINS,
                         ("livingproof.com", "deathwishcoffee.com", "blackriflecoffee.com"))


if __name__ == "__main__":
    unittest.main()
