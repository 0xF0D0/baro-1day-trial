"""Turn Gmail connector RAW responses into redacted .eml files.

Usage: python3 -I redact.py OUT_DIR RAW_JSON [RAW_JSON ...]

Rules
- Headers: keep only a whitelist. Receiving-path headers (Received, Delivered-To,
  Return-Path, ARC-*, DKIM-*, Authentication-Results, ...) are dropped because they
  carry the inbox address. DKIM signatures no longer verify after this.
- To: replaced with TRIAL_INBOX.
- List-Unsubscribe: query string replaced with REDACTED, mailto form dropped.
- Body (text/plain and text/html, decoded first so quoted-printable line breaks
  cannot split a token): per-recipient tracking tokens are replaced:
    <tracker host>/l/<token>  -> /l/REDACTED   (click tracking)
    <tracker host>/o/<token>  -> /o/REDACTED   (open pixel)
    manage.kmail-lists.com/...?<query> -> ?REDACTED (unsubscribe / preferences)
  Tracker hosts: any host containing "klclick", or starting with "trk.".
- Added headers: X-Trial-Gmail-Id, X-Trial-Received-At (Gmail internalDate, UTC),
  X-Trial-Gmail-Labels, X-Trial-Redaction.
- The script refuses to write a file if the inbox address or its local part is
  still anywhere in the output.

Two levels (redact_message):
- verified (default): senders we checked by hand; the rules above apply, the body is
  otherwise unchanged and keeps both text parts.
- strict (strict=True): unknown senders. Output is one text/plain part (the first plain
  part, else the text of the first HTML part); headers From/Subject/Date/MIME-Version
  only; every link cut to its host, mailto: and other addresses replaced; the inbox
  address and its local part replaced; any error raises RedactionError with a fixed text.
"""
import base64, datetime, json, re, sys
from html.parser import HTMLParser
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from urllib.parse import urlsplit

KEEP = ['From', 'Reply-To', 'Subject', 'Date', 'Message-ID', 'MIME-Version',
        'Feedback-ID', 'List-Unsubscribe-Post', 'X-Kmail-Account', 'X-Kmail-Flow',
        'X-Kmail-Message', 'X-Report-Abuse']

TRACK_RE = re.compile(
    r'(https?://(?:[A-Za-z0-9\-]+\.)*(?:[A-Za-z0-9\-]*klclick[A-Za-z0-9\-]*|c?trk)(?:\.[A-Za-z0-9\-]+)*)'
    r'/(l|o)/([^\s"\'<>)\]]+)',
    re.I)
MANAGE_RE = re.compile(r'(https?://manage\.kmail-lists\.com/[^\s"\'<>?)\]]*)\?([^\s"\'<>)\]]+)', re.I)
# independent check: any /l/ or /o/ path with a long token that is not REDACTED
LEFTOVER_RE = re.compile(r'https?://[^\s"\'<>]+/(?:l|o)/(?!REDACTED)[A-Za-z0-9_\-]{16,}', re.I)


def redact_text(t, removed):
    n = {}

    def tr(m):
        tok = m.group(3)
        removed.add(tok)
        removed.update(s for s in re.split(r'[_\-\.]', tok) if len(s) >= 10)
        return f'{m.group(1)}/{m.group(2)}/REDACTED'

    def mg(m):
        for kv in m.group(2).replace('&amp;', '&').split('&'):
            v = kv.split('=', 1)[-1]
            if len(v) >= 8:
                removed.add(v)
        return f'{m.group(1)}?REDACTED'

    t, n['tracking'] = TRACK_RE.subn(tr, t)
    t, n['manage'] = MANAGE_RE.subn(mg, t)
    return t, n


def slug(from_header):
    addr = getaddresses([from_header])[0][1].lower()
    dom = addr.split('@')[-1]
    return {'livingproof.com': 'livingproof', 'deathwishcoffee.com': 'deathwish',
            'blackriflecoffee.com': 'blackrifle'}.get(dom, dom.replace('.', '_'))


VERIFIED_DOMAINS = ("livingproof.com", "deathwishcoffee.com", "blackriflecoffee.com")

STRICT_KEEP = ['From', 'Subject', 'Date', 'MIME-Version']
LINK_RE = re.compile(
    r'(?P<url>https?://[^\s<>"]+)'
    r'|(?P<mailto>mailto:[^\s<>"]+)'
    r'|(?<![\w/])(?P<bare>(?://|www\.)[^\s<>"]+)',
    re.I)
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
HOST_RE = re.compile(r'[A-Za-z0-9.\-]+')
BLOCK_TAGS = {'p', 'div', 'br', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table'}
SKIP_TAGS = {'script', 'style', 'head', 'title'}


class RedactionError(Exception):
    """The message cannot be written. `convert` turns it into the old SystemExit text:
    before + joiner + path + after."""

    def __init__(self, before, joiner='', after=''):
        super().__init__(before + after)
        self.before, self.joiner, self.after = before, joiner, after


def cut_links(t):
    """Cut links to scheme://host/REDACTED (host-only links stay), mailto: to mailto:REDACTED,
    scheme-less //host/... and www.host/... to host/REDACTED. Returns (text, replacements)."""
    n = [0]

    def cut(m):
        if m.group('url'):
            tok = m.group('url')
            scheme = tok.split('://', 1)[0].lower()
            try:
                host = urlsplit(tok).hostname
            except ValueError:
                host = None
            if host and not HOST_RE.fullmatch(host):
                host = None
            if host and tok.lower() in (f'{scheme}://{host}', f'{scheme}://{host}/'):
                return tok
            n[0] += 1
            return f'{scheme}://{host}/REDACTED' if host else f'{scheme}://REDACTED'
        if m.group('mailto'):
            n[0] += 1
            return 'mailto:REDACTED'
        tok = m.group('bare')
        rest = tok[2:] if tok.startswith('//') else tok
        i = min((rest.find(c) for c in '/?#:' if c in rest), default=len(rest))
        host, tail = rest[:i], rest[i:]
        if not HOST_RE.fullmatch(host):
            n[0] += 1
            return 'REDACTED'
        if tail in ('', '/'):
            return tok
        n[0] += 1
        return f'{host}/REDACTED'

    return LINK_RE.sub(cut, t), n[0]


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html):
    p = _TextExtractor()
    p.feed(html)
    p.close()
    return _tidy(''.join(p.parts))


def _tidy(text):
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = line.rstrip()
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines) + '\n'


def _strict_text(t, inbox, local):
    """Links first, then addresses. Returns (text, links_cut, addresses_replaced)."""
    t, links = cut_links(t)
    t, a1 = re.subn(re.escape(inbox), 'TRIAL_INBOX', t, flags=re.I)
    t, a2 = EMAIL_RE.subn(lambda m: 'REDACTED@' + m.group(0).split('@', 1)[1], t)
    t, a3 = re.subn(re.escape(local), 'TRIAL_INBOX', t, flags=re.I)
    return t, links, a1 + a2 + a3


def _redact_strict(src, gmail_id, received_at, labels, inbox):
    try:
        return _redact_strict_inner(src, gmail_id, received_at, labels, inbox)
    except RedactionError:
        raise
    except Exception:
        raise RedactionError('unreadable message', ' for ', '; nothing written') from None


def _redact_strict_inner(src, gmail_id, received_at, labels, inbox):
    msg = BytesParser(policy=policy.default).parsebytes(src)
    if inbox is None:
        inbox = getaddresses(msg.get_all('To', []))[0][1]
    inbox = inbox.lower()
    local = inbox.split('@')[0]
    received = received_at.astimezone(datetime.timezone.utc)

    plain = html = None
    dropped = 0
    for part in msg.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        if part.get_content_disposition() != 'attachment':
            if ct == 'text/plain' and plain is None:
                plain = part.get_content()
                continue
            if ct == 'text/html' and html is None:
                html = part.get_content()
                continue
        dropped += 1
    if plain is not None:
        source, text = 'plain', plain
    elif html is not None:
        source, text = 'html', html_to_text(html)
    else:
        raise RedactionError('missing text part', ' in ')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text, links, addresses = _strict_text(text, inbox, local)
    counts = {'urls': links, 'addresses': addresses, 'parts_dropped': dropped,
              'source': source, 'html_not_kept': 1 if (source == 'plain' and html is not None) else 0}

    out = EmailMessage(policy=policy.default.clone(linesep='\r\n'))
    for h in STRICT_KEEP:
        v = msg.get(h)
        if v is not None:
            out[h] = str(v)
    out['To'] = 'TRIAL_INBOX <trial_inbox@redacted.invalid>'
    out['X-Trial-Gmail-Id'] = gmail_id
    out['X-Trial-Received-At'] = received.strftime('%Y-%m-%dT%H:%M:%SZ')
    out['X-Trial-Gmail-Labels'] = ', '.join(labels)
    out.set_content(text, subtype='plain', charset='utf-8', cte='quoted-printable')
    out['X-Trial-Redaction'] = (
        f'strict: plain text only (from {source}); headers reduced; To replaced; '
        f'{links} link(s) cut; {addresses} address(es) replaced; {dropped} part(s) dropped.')

    data = out.as_bytes()
    check = data.decode('latin-1')
    for k, v in out.items():
        check += '\n' + str(v)
    check += '\n' + out.get_content()
    low = check.lower()
    low += '\n' + low.replace('%40', '@')
    if inbox in low or local in low:
        raise RedactionError('inbox address still present', ' for ', '; nothing written')
    return data, counts


def redact_message(src, gmail_id, received_at, labels, inbox=None, strict=False):
    """Redact one RFC 822 message. Returns (ASCII CRLF bytes, counts); raises RedactionError."""
    if strict:
        return _redact_strict(src, gmail_id, received_at, labels, inbox)
    msg = BytesParser(policy=policy.default).parsebytes(src)
    if inbox is None:
        inbox = getaddresses(msg.get_all('To', []))[0][1]
    inbox = inbox.lower()
    local = inbox.split('@')[0]
    received = received_at.astimezone(datetime.timezone.utc)

    removed = set()
    counts = {}
    out = EmailMessage(policy=policy.default.clone(linesep='\r\n'))
    for h in ('X-Kmail-Ops', 'X-SG-ID', 'X-SG-EID', 'X-Entity-ID'):
        for v in msg.get_all(h, []):
            removed.update(s for s in re.split(r'[^A-Za-z0-9]', str(v)) if len(s) >= 10)

    lu = msg.get('List-Unsubscribe')
    lu_new = None
    if lu:
        https = [u for u in re.findall(r'<([^>]+)>', str(lu)) if u.lower().startswith('http')]
        if https:
            lu_new = ', '.join(f'<{redact_text(u, removed)[0]}>' for u in https)

    counts = {'tracking': 0, 'manage': 0}
    plain = html = None
    plain_cs = html_cs = 'utf-8'
    for part in msg.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        txt = part.get_content()
        if ct == 'text/plain' and plain is None:
            plain, plain_cs = txt, part.get_content_charset() or 'utf-8'
        elif ct == 'text/html' and html is None:
            html, html_cs = txt, part.get_content_charset() or 'utf-8'
        else:
            raise RedactionError(f'unexpected part {ct}', ' in ')
    if plain is None or html is None:
        raise RedactionError('missing text part', ' in ')
    plain, n1 = redact_text(plain, removed)
    html, n2 = redact_text(html, removed)
    for k in counts:
        counts[k] = n1[k] + n2[k]

    # headers are written after the body pass so every removed token is known
    header_hits = []
    for h in KEEP:
        for v in msg.get_all(h, []):
            v = str(v)
            for tok in sorted(removed, key=len, reverse=True):
                if tok in v:
                    v = v.replace(tok, 'REDACTED')
                    header_hits.append(h)
            out[h] = v
    counts['header_tokens'] = sorted(set(header_hits))
    redaction = (
        'Receiving-path headers dropped; To replaced; per-recipient tracking tokens '
        f'replaced ({counts["tracking"]} tracking, {counts["manage"]} unsubscribe/manage'
        f'{", also in " + "/".join(counts["header_tokens"]) if counts["header_tokens"] else ""}). '
        'Body text otherwise unchanged; parts re-encoded as quoted-printable.')

    out['To'] = 'TRIAL_INBOX <trial_inbox@redacted.invalid>'
    if lu_new:
        out['List-Unsubscribe'] = lu_new
    out['X-Trial-Gmail-Id'] = gmail_id
    out['X-Trial-Received-At'] = received.strftime('%Y-%m-%dT%H:%M:%SZ')
    out['X-Trial-Gmail-Labels'] = ', '.join(labels)

    if plain is not None and html is not None:
        out.set_content(plain, subtype='plain', charset=plain_cs, cte='quoted-printable')
        out.add_alternative(html, subtype='html', charset=html_cs, cte='quoted-printable')
    elif plain is not None:
        out.set_content(plain, subtype='plain', charset=plain_cs, cte='quoted-printable')
    else:
        out.set_content(html, subtype='html', charset=html_cs, cte='quoted-printable')
    out['X-Trial-Redaction'] = redaction

    data = out.as_bytes()
    check = data.decode('latin-1')
    for part in out.walk():
        if not part.is_multipart():
            check += part.get_content()
    if inbox in check.lower() or local in check.lower():
        raise RedactionError('inbox address still present', ' for ', '; nothing written')
    if LEFTOVER_RE.search(check):
        raise RedactionError('tracking token still present', ' for ', '; nothing written')
    leaked = sorted(t for t in removed if t in check)
    if leaked:
        raise RedactionError(f'{len(leaked)} removed token(s) still present', ' for ',
                             ' (e.g. in Message-ID); nothing written')
    return data, counts


def convert(path, out_dir):
    d = json.load(open(path))
    raw = d['raw']
    src = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
    received = datetime.datetime.fromtimestamp(int(d['internalDate']) / 1000, datetime.UTC)
    try:
        data, counts = redact_message(src, d['id'], received, d.get('labelIds', []), strict=False)
    except RedactionError as e:
        raise SystemExit(f'{e.before}{e.joiner}{path}{e.after}')
    msg = BytesParser(policy=policy.default).parsebytes(src)
    name = f'{slug(msg["From"])}_{received.strftime("%Y%m%dT%H%M%SZ")}_{d["id"]}.eml'
    with open(f'{out_dir}/{name}', 'wb') as f:
        f.write(data)
    return name, counts, len(src), len(data)


if __name__ == '__main__':
    out_dir = sys.argv[1]
    for p in sys.argv[2:]:
        name, counts, a, b = convert(p, out_dir)
        print(f'{name}: {counts} | source {a} bytes -> eml {b} bytes')
