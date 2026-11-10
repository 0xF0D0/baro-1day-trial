import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import psycopg

import db

OFFER = ("discount", "free_gift", "bundle", "subscription", "giveaway", "free_shipping", "none")
MESSAGE = ("benefit", "ingredient", "convenience", "proof", "personal_fit", "novelty", "gifting", "availability",
           "brand", "none")
VOICE = ("brand", "creator", "customer", "expert", "celebrity_event")
LIST_VERSION = 1
LABELS_FILE = Path(__file__).resolve().parent / "labels" / "ad_angles.jsonl"
KEYS = ("text_sha256", "list_version", "labeled_by", "labeled_at", "angle_offer", "offer_evidence",
        "angle_message", "message_evidence", "angle_voice", "voice_evidence")
MAX_WORDS = 12
KINDS = (("offer", OFFER, "none"), ("message", MESSAGE, "none"), ("voice", VOICE, "brand"))


class LabelError(Exception):
    def __init__(self, line: int, reason: str):
        super().__init__(f"line {line}: {reason}")
        self.line, self.reason = line, reason


def _squash(value) -> str:
    return " ".join((value or "").split())


def ad_text(headline, body) -> str:
    head, tail = _squash(headline), _squash(body)
    return "" if not head and not tail else head + "\n" + tail


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_label(label: dict) -> str | None:
    for key in KEYS:
        if key not in label:
            return f"{key} missing"
    if label["list_version"] != LIST_VERSION or isinstance(label["list_version"], bool):
        return f"list_version is not {LIST_VERSION}"
    sha = label["text_sha256"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return "text_sha256 is not 64 lower-case hex"
    for kind, values, bare in KINDS:
        value, evidence = label[f"angle_{kind}"], label[f"{kind}_evidence"]
        name = f"{kind}_evidence"
        if value not in values:
            return f"angle_{kind} not in list"
        if value == bare:
            if evidence is not None:
                return f"{name} not expected"
        elif not isinstance(evidence, str) or not evidence.strip():
            return f"{name} missing"
        elif "@" in evidence:
            return f"{name} has a handle"
        elif len(evidence.split()) > MAX_WORDS:
            return f"{name} longer than {MAX_WORDS} words"
    return None


def check_evidence(label: dict, text: str) -> str | None:
    for kind, _, _ in KINDS:
        evidence = label[f"{kind}_evidence"]
        if evidence is not None and _squash(evidence) not in text:
            return f"{kind}_evidence not in the ad text"
    return None


def _read(path: Path) -> dict[str, tuple[int, dict]]:
    found = {}
    if not Path(path).is_file():
        return found
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            label = json.loads(line)
        except ValueError:
            raise LabelError(number, "not JSON") from None
        if not isinstance(label, dict):
            raise LabelError(number, "not a JSON object")
        reason = check_label(label)
        if reason:
            raise LabelError(number, reason)
        if label["text_sha256"] in found:
            raise LabelError(number, "duplicate text_sha256")
        found[label["text_sha256"]] = (number, label)
    return found


def read_labels(path: Path) -> dict[str, dict]:
    return {h: label for h, (_, label) in _read(path).items()}


def _ads(conn):
    return conn.execute("SELECT source, brand, kind, key, channel, headline, body FROM ads "
                        "ORDER BY source, brand, kind, key").fetchall()


def apply_labels(conn, path: Path = LABELS_FILE) -> tuple[int, int, int]:
    labels = _read(path)
    labeled = not_labeled = no_text = 0
    rows = []
    for source, brand, kind, key, _, headline, body in _ads(conn):
        text = ad_text(headline, body)
        if not text:
            no_text += 1
            continue
        found = labels.get(text_hash(text))
        if found is None:
            not_labeled += 1
            continue
        number, label = found
        reason = check_evidence(label, text)
        if reason:
            raise LabelError(number, reason)
        labeled += 1
        rows.append((source, brand, kind, key, label["angle_offer"], label["offer_evidence"], label["angle_message"],
                     label["message_evidence"], label["angle_voice"], label["voice_evidence"], label["text_sha256"],
                     label["list_version"], label["labeled_by"], label["labeled_at"]))
    conn.execute("DELETE FROM ad_angles")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO ad_angles (source, brand, kind, key, angle_offer, offer_evidence, angle_message, "
                        "message_evidence, angle_voice, voice_evidence, text_sha256, list_version, labeled_by, "
                        "labeled_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", rows)
    return labeled, not_labeled, no_text


def pending(conn, path: Path = LABELS_FILE) -> list[dict]:
    labels = _read(path)
    texts = {}
    for _, brand, kind, _, channel, headline, body in _ads(conn):
        text = ad_text(headline, body)
        if not text or text_hash(text) in labels:
            continue
        entry = texts.setdefault(text, {"brands": set(), "channels": set(), "kinds": set(), "ads": 0})
        entry["brands"].add(brand); entry["channels"].add(channel); entry["kinds"].add(kind); entry["ads"] += 1
    out = [{"text_sha256": text_hash(t), "text": t, "brands": sorted(e["brands"]), "channels": sorted(e["channels"]),
            "kinds": sorted(e["kinds"]), "ads": e["ads"]} for t, e in texts.items()]
    return sorted(out, key=lambda o: (-o["ads"], o["text_sha256"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Work with the ad angle labels.")
    parser.add_argument("--pending", action="store_true", help="print the ad texts that have no label yet")
    parser.add_argument("--labels", type=Path, default=LABELS_FILE)
    args = parser.parse_args(argv)
    if not args.pending:
        parser.error("nothing to do: pass --pending")
    try:
        conn = db.connect(db.database_url())
    except psycopg.OperationalError as e:
        print(f"cannot connect: {str(e).strip()}")
        return 1
    try:
        db.ensure_schema(conn)
        items = pending(conn, args.labels)
    except LabelError as e:
        print(f"labels: {e}")
        return 1
    finally:
        conn.close()
    for item in items:
        print(json.dumps(item, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
