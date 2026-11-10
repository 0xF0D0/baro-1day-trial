import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
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
LABEL_WORKERS = 8
DEFAULT_MODEL = "claude-opus-5-5"
PROMPT_VERSION = "prompt-v1"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SYSTEM_PROMPT = """You read one ad text and say how the ad sells. Give exactly one value for each of three kinds, and a short evidence phrase for each.

The ad text is a headline and a body joined by a newline. Signup forms carry the brand's internal name of the form, not what a visitor reads; read their angles from that name (usually an offer such as giveaway or discount, or a message such as novelty or availability, often none).

Kind 1, angle_offer: what does the ad give for acting now. Values:
- discount: money or a percentage off, a code
- free_gift: a free item with purchase: samples, minis, a bag
- bundle: a set or a build-your-own bundle at a lower price
- subscription: a lower price or perk for subscribing
- giveaway: a draw, a contest, an entry to win
- free_shipping: free delivery
- none: the ad gives nothing for acting now

Kind 2, angle_message: what does the ad put forward about the product. Values:
- benefit: what the product does for the buyer: result, taste, strength, with or without numbers
- ingredient: an ingredient, a technology, a formula, nutrition
- convenience: saving time or effort, portability, fast delivery
- proof: units sold, awards, "No. 1", ratings, a quoted review, a professional's recommendation
- personal_fit: several products for different needs, a quiz, where to start, build your own
- novelty: a new product, a limited edition, a new scent or flavour, a return
- gifting: a holiday, a season, giving it as a gift
- availability: now sold at a named retailer, an exclusive, back in stock
- brand: who the brand is or stands for, belonging, a cause
- none: the ad puts nothing forward about the product

Kind 3, angle_voice: who is speaking. Values:
- brand: the brand speaks (the default)
- creator: a creator or partner speaking in first person
- customer: a customer's words quoted
- expert: a professional speaking or cited (stylist, vet, barista)
- celebrity_event: a named celebrity, athlete, band, or event tie-in

Choosing one value per kind: take the value the headline or the first sentence leads with; when the ad leads with nothing of that kind, take the kind that takes most of the words. An ad that only states a deal has angle_message none. angle_voice is brand unless the words are clearly someone else's.

Evidence rules, for offer_evidence, message_evidence and voice_evidence:
- An evidence is a phrase of at most 12 words copied exactly from the ad text, character for character, from a single place in it.
- It must not contain an @ handle. If the only supporting words contain a handle, pick other words from the text.
- Give an evidence only when the value is not none (offer, message) and not brand (voice). Otherwise the evidence is an empty string.

Answer only with the JSON object of the six fields."""
KINDS = (("offer", OFFER, "none"), ("message", MESSAGE, "none"), ("voice", VOICE, "brand"))


class LabelFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
    if not isinstance(label["labeled_by"], str) or not label["labeled_by"].strip():
        return "labeled_by is not a non-empty string"
    at = label["labeled_at"]
    try:
        if not isinstance(at, str):
            raise ValueError
        datetime.datetime.fromisoformat(at[:-1] + "+00:00" if at.endswith("Z") else at)
    except ValueError:
        return "labeled_at is not a time"
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
    pieces = Path(path).read_text(encoding="utf-8").split("\n")
    if pieces and pieces[-1] == "":
        pieces.pop()
    for number, line in enumerate(pieces, 1):
        line = line.removesuffix("\r")
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


def read_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        lines = Path(ENV_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == "ANTHROPIC_API_KEY":
            value = value.strip().strip("\"'").strip()
            return value or None
    return None


def answer_schema() -> dict:
    props = {}
    for kind, values, _ in KINDS:
        props[f"angle_{kind}"] = {"type": "string", "enum": list(values)}
        props[f"{kind}_evidence"] = {"type": "string"}
    return {"type": "object", "properties": props,
            "required": ["angle_offer", "offer_evidence", "angle_message", "message_evidence", "angle_voice",
                         "voice_evidence"],
            "additionalProperties": False}


def ask_model(client, model: str, text: str) -> dict:
    import anthropic
    kwargs = dict(
        model=model, max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": answer_schema()}})
    try:
        if model == DEFAULT_MODEL:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            response = client.beta.messages.create(**kwargs)
        else:
            response = client.messages.create(**kwargs)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.BadRequestError):
        raise
    except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        raise LabelFailure(f"api: {type(e).__name__}") from None
    if response.stop_reason in ("refusal", "max_tokens"):
        raise LabelFailure(response.stop_reason)
    block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
    try:
        data = json.loads(block.text)
    except (AttributeError, TypeError, ValueError):
        raise LabelFailure("not_json") from None
    if not isinstance(data, dict):
        raise LabelFailure("not_json")
    out = {}
    for key in ("angle_offer", "offer_evidence", "angle_message", "message_evidence", "angle_voice",
                "voice_evidence"):
        value = data.get(key)
        out[key] = None if key.endswith("_evidence") and value == "" else value
    answered = getattr(response, "model", None)
    out["model"] = answered if isinstance(answered, str) and answered else model
    return out


def label_pending(conn, path: Path, client, model: str, now: str, on_failure=None) -> tuple[int, int]:
    labeled = failed = 0
    items = pending(conn, path)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=LABEL_WORKERS)
    try:
        futures = [pool.submit(ask_model, client, model, item["text"]) for item in items]
        for item, future in zip(items, futures):
            reason = None
            try:
                got = future.result()
            except LabelFailure as e:
                reason = e.reason
            else:
                answered = got.pop("model", model)
                line = {"text_sha256": item["text_sha256"], "list_version": LIST_VERSION,
                        "labeled_by": f"{answered}/{PROMPT_VERSION}", "labeled_at": now, **got}
                reason = check_label(line) or check_evidence(line, item["text"])
            if reason:
                failed += 1
                if on_failure:
                    on_failure(item["text_sha256"], reason)
                continue
            with open(path, "a+b") as f:
                f.seek(0, os.SEEK_END)
                if f.tell():
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        f.write(b"\n")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                f.flush()
            labeled += 1
    finally:
        pool.shutdown(wait=True, cancel_futures=True)  # requests not yet started are dropped; running ones finish
    return labeled, failed


def _without_password(url: str) -> str:
    from load import _without_password as hide  # load imports this module, so import it late
    return hide(url)


def _api_message(e) -> str:
    body = getattr(e, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    if not isinstance(message, str):
        message = str(e)
    return " ".join(message.split())[:200]


def run_label(path: Path) -> int:
    key = read_key()
    if not key:
        print("label: could not look: missing_key")
        return 1
    import anthropic
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    model = os.environ.get("ANGLE_MODEL", DEFAULT_MODEL)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = db.database_url()
    try:
        conn = db.connect(url)
    except psycopg.OperationalError as e:
        print(f"cannot connect to {_without_password(url)}: {str(e).strip()}")
        return 1
    try:
        db.ensure_schema(conn)
        labeled, failed = label_pending(
            conn, path, client, model, now, lambda h, r: print(f"label: failed {h[:12]}: {r}"))
        remaining = len(pending(conn, path))
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        print("label: could not look: auth")
        return 1
    except anthropic.BadRequestError as e:
        print(f"label: could not look: bad_request: {_api_message(e)}")
        return 1
    except LabelError as e:
        print(f"labels: {e}")
        return 1
    finally:
        conn.close()
    print(f"label: labeled={labeled} failed={failed} pending={remaining}")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Work with the ad angle labels.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pending", action="store_true", help="print the ad texts that have no label yet")
    mode.add_argument("--label", action="store_true", help="ask a model for the angles of the pending ad texts")
    parser.add_argument("--labels", type=Path, default=LABELS_FILE)
    args = parser.parse_args(argv)
    if args.label:
        return run_label(args.labels)
    if not args.pending:
        parser.error("nothing to do: pass --pending or --label")
    url = db.database_url()
    try:
        conn = db.connect(url)
    except psycopg.OperationalError as e:
        print(f"cannot connect to {_without_password(url)}: {str(e).strip()}")
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
