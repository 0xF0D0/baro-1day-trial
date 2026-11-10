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
"""
import base64, datetime, json, re, sys
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses

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

STRICT_KEEP = ['From', 'Reply-To', 'Subject', 'Date', 'MIME-Version']
URL_RE = re.compile(r'https?://[^\s"\'<>()\]]+', re.I)


class RedactionError(Exception):
    """The message cannot be written. `convert` turns it into the old SystemExit text:
    before + joiner + path + after."""

    def __init__(self, before, joiner='', after=''):
        super().__init__(before + after)
        self.before, self.joiner, self.after = before, joiner, after


def cut_urls(t):
    """Cut every URL to scheme://host/REDACTED. A URL that is only scheme and host is left alone."""
    n = [0]

    def cut(m):
        url = m.group(0)
        scheme, rest = url.split('://', 1)
        i = min((rest.find(c) for c in '/?#' if c in rest), default=len(rest))
        host, tail = rest[:i], rest[i:]
        if tail in ('', '/'):
            return url
        n[0] += 1
        return f'{scheme}://{host.rsplit("@", 1)[-1]}/REDACTED'

    return URL_RE.sub(cut, t), n[0]


def _strict_body(t, inbox, local):
    t, n = cut_urls(t)
    t = re.sub(re.escape(inbox), 'TRIAL_INBOX', t, flags=re.I)
    t = re.sub(re.escape(local), 'TRIAL_INBOX', t, flags=re.I)
    return t, n


def redact_message(src, gmail_id, received_at, labels, inbox=None, strict=False):
    """Redact one RFC 822 message. Returns (ASCII CRLF bytes, counts); raises RedactionError."""
    msg = BytesParser(policy=policy.default).parsebytes(src)
    if inbox is None:
        inbox = getaddresses(msg.get_all('To', []))[0][1]
    inbox = inbox.lower()
    local = inbox.split('@')[0]
    received = received_at.astimezone(datetime.timezone.utc)

    removed = set()
    counts = {}
    out = EmailMessage(policy=policy.default.clone(linesep='\r\n'))
    if strict:
        bodies = {}
        parsed = {}
        counts = {'urls': 0, 'parts_dropped': 0}
        for part in msg.walk():
            if part.is_multipart():
                continue
            ct = part.get_content_type()
            if ct in ('text/plain', 'text/html') and ct not in bodies \
                    and part.get_content_disposition() != 'attachment':
                bodies[ct] = part.get_content()
                parsed[ct] = part.get_content_charset() or 'utf-8'
            else:
                counts['parts_dropped'] += 1
        if not bodies:
            raise RedactionError('missing text part')
        for ct in bodies:
            bodies[ct], n = _strict_body(bodies[ct], inbox, local)
            counts['urls'] += n
        for h in STRICT_KEEP:
            for v in msg.get_all(h, []):
                out[h] = str(v)
        plain, html = bodies.get('text/plain'), bodies.get('text/html')
        plain_cs, html_cs = parsed.get('text/plain'), parsed.get('text/html')
        redaction = (f'strict: headers reduced; To replaced; {counts["urls"]} URL(s) cut to host; '
                     f'{counts["parts_dropped"]} part(s) dropped.')
        lu_new = None
    else:
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
