"""Independent check of redacted .eml files against the connector RAW sources.
Usage: python3 -I verify.py EML_DIR RAW_JSON [RAW_JSON ...]
Never prints the inbox address or any removed token."""
import base64, glob, json, re, sys, urllib.parse
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

URL = re.compile(r'https?://[^\s"\'<>()\]]+', re.I)


def parts(msg):
    out = {}
    for p in msg.walk():
        if not p.is_multipart():
            out.setdefault(p.get_content_type(), p.get_content())
    return out


def sensitive(msg, texts):
    toks = set()
    for h in ('X-Kmail-Ops', 'X-SG-ID', 'X-SG-EID', 'X-Entity-ID', 'List-Unsubscribe'):
        for v in msg.get_all(h, []):
            toks.update(s for s in re.split(r'[^A-Za-z0-9]', str(v)) if len(s) >= 12)
    for t in texts:
        for u in URL.findall(t):
            u = u.replace('&amp;', '&')
            p = urllib.parse.urlsplit(u)
            if 'kmail-lists' in p.netloc:
                for vals in urllib.parse.parse_qs(p.query).values():
                    toks.update(v for v in vals if len(v) >= 8)
            m = re.match(r'/(?:l|o)/([^/?#]+)', p.path)
            if m and len(m.group(1)) >= 16:
                toks.add(m.group(1))
                toks.update(s for s in re.split(r'[_\-\.]', m.group(1)) if len(s) >= 12)
    # plain lowercase words (e.g. the URL path word "subscriptions") are not tokens
    return {t for t in toks if not (t.isalpha() and t.islower())}


def main():
    eml_dir = sys.argv[1]
    ok_all = True
    for path in sys.argv[2:]:
        d = json.load(open(path))
        raw = d['raw']
        src = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        inbox = getaddresses(src.get_all('To', []))[0][1].lower()
        local = inbox.split('@')[0]
        sp = parts(src)
        toks = sensitive(src, sp.values())
        files = glob.glob(f'{eml_dir}/*_{d["id"]}.eml')
        assert len(files) == 1, files
        data = open(files[0], 'rb').read()
        out = BytesParser(policy=policy.default).parsebytes(data)
        op = parts(out)
        full = data.decode('latin-1') + ''.join(op.values())
        res = {}
        res['addr_absent'] = inbox not in full.lower() and local not in full.lower()
        res['tokens_checked'] = len(toks)
        res['tokens_absent'] = not any(t in full for t in toks)
        res['same_parts'] = sorted(sp) == sorted(op)
        same_text = True
        for ct in sp:
            # set_content appends one line break at the end of each part
            a = URL.sub('<URL>', sp[ct]).rstrip('\r\n')
            b = URL.sub('<URL>', op.get(ct, '')).rstrip('\r\n')
            if a != b:
                same_text = False
        res['text_same_outside_urls'] = same_text
        res['url_count_same'] = all(len(URL.findall(sp[ct])) == len(URL.findall(op.get(ct, ''))) for ct in sp)
        res['redacted_markers'] = full.count('REDACTED')
        for h in ('From', 'Subject', 'Date', 'X-Trial-Received-At', 'X-Trial-Gmail-Labels'):
            res[h] = str(out.get(h))
        res['dropped_headers_absent'] = all(out.get(h) is None for h in (
            'Received', 'Delivered-To', 'Return-Path', 'ARC-Seal', 'DKIM-Signature',
            'Authentication-Results', 'X-Kmail-Ops', 'X-SG-ID', 'X-Entity-ID', 'CFBL-Address'))
        res['header_names'] = [k for k, _ in out.raw_items()]
        codes = [c for c in ('WC-TM5JN7LG', 'DWC20', 'BEANS20') if c in op.get('text/plain', '')]
        res['offer_codes_in_plain'] = codes
        good = all(res[k] for k in ('addr_absent', 'tokens_absent', 'same_parts', 'text_same_outside_urls',
                                     'url_count_same', 'dropped_headers_absent'))
        ok_all &= good
        print('=' * 60)
        print(files[0].split('/')[-1], '->', 'PASS' if good else 'FAIL')
        for k, v in res.items():
            print(f'  {k}: {v}')
    print('ALL PASS' if ok_all else 'SOME FAILED')


if __name__ == '__main__':
    main()
