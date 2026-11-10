import contextlib
import hashlib
import io
import json
import os
from types import SimpleNamespace
from unittest import mock

import support
from support import DbTestCase

import angles


class AngleBase(DbTestCase):
    def ad(self, key, headline, body, brand="b", channel="meta"):
        self.conn.execute(
            "INSERT INTO ads (source, brand, kind, key, scope, fetched_at, first_seen_at, last_seen_at, last_run_id, raw, "
            "channel, headline, body) VALUES ('fake', %s, 'ad', %s, 'all', now(), now(), now(), 'r', '{}', %s, %s, %s)",
            (brand, key, channel, headline, body))
        self.conn.commit()

    def line(self, text, **over):
        base = {"text_sha256": angles.text_hash(text), "list_version": 1, "labeled_by": "test",
                "labeled_at": "2026-11-11T00:00:00Z", "angle_offer": "none", "offer_evidence": None,
                "angle_message": "none", "message_evidence": None, "angle_voice": "brand", "voice_evidence": None}
        return {**base, **over}

    def write_labels(self, lines):
        self.labels = self.dir / "labels.jsonl"
        self.labels.write_text("".join(json.dumps(x) + "\n" for x in lines))

    def write_raw(self, lines):
        self.labels = self.dir / "labels.jsonl"
        self.labels.write_text("\n".join(lines) + "\n")


class AnglesTest(AngleBase):
    def test_ad_text_and_hash(self):
        self.assertEqual(angles.ad_text("  Save   20%\n", " Bundled for\tthe busy "), "Save 20%\nBundled for the busy")
        self.assertEqual(angles.ad_text(None, "x"), "\nx")
        self.assertEqual(angles.ad_text(" ", None), "")
        self.assertEqual(angles.text_hash("a"), hashlib.sha256(b"a").hexdigest())

    def test_check_label_reasons(self):
        good = self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%")
        self.assertIsNone(angles.check_label(good))
        for change, reason in [({"angle_offer": "sale"}, "angle_offer not in list"),
                               ({"offer_evidence": None}, "offer_evidence missing"),
                               ({"angle_offer": "none"}, "offer_evidence not expected"),
                               ({"offer_evidence": "ask @someone"}, "offer_evidence has a handle"),
                               ({"offer_evidence": " ".join(["w"] * 13)}, "offer_evidence longer than 12 words"),
                               ({"voice_evidence": "x"}, "voice_evidence not expected"),
                               ({"list_version": 2}, "list_version is not 1"),
                               ({"text_sha256": "ABC"}, "text_sha256 is not 64 lower-case hex"),
                               ({"angle_message": "brand", "message_evidence": ""}, "message_evidence missing"),
                               ({"angle_voice": "creator"}, "voice_evidence missing"),
                               ({"angle_voice": "robot"}, "angle_voice not in list")]:
            self.assertEqual(angles.check_label({**good, **change}), reason, change)
        missing = dict(good); del missing["labeled_by"]
        self.assertEqual(angles.check_label(missing), "labeled_by missing")
        for value in (None, "", 7):
            self.assertEqual(angles.check_label({**good, "labeled_by": value}),
                             "labeled_by is not a non-empty string", value)
        for value in (None, "yesterday", 5):
            self.assertEqual(angles.check_label({**good, "labeled_at": value}), "labeled_at is not a time", value)
        self.assertIsNone(angles.check_label({**good, "labeled_at": "2026-11-11T00:00:00+00:00"}))

    def test_non_ascii_labels_round_trip(self):
        text = "Save 20% \u2122 \U0001F600\nfor the busy"
        self.ad("1", "Save 20% \u2122 \U0001F600", "for the busy")
        label = self.line(text, angle_offer="discount", offer_evidence="Save 20% \u2122 \U0001F600")
        self.labels = self.dir / "labels.jsonl"
        self.labels.write_text(json.dumps(label, ensure_ascii=False) + "\n", encoding="utf-8")
        with mock.patch("locale.getpreferredencoding", return_value="ascii"), \
                mock.patch.dict(os.environ, {"PYTHONUTF8": "0"}):
            self.assertEqual(angles.read_labels(self.labels)[angles.text_hash(text)]["offer_evidence"],
                             "Save 20% \u2122 \U0001F600")
            self.assertEqual(angles.apply_labels(self.conn, self.labels), (1, 0, 0))

    def test_main_pending_hides_the_password(self):
        self.labels = self.dir / "labels.jsonl"
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:secret@localhost:1/nope"}), \
                contextlib.redirect_stdout(buffer):
            code = angles.main(["--pending", "--labels", str(self.labels)])
        self.assertEqual(code, 1)
        self.assertIn("cannot connect to postgresql://u@localhost:1/nope", buffer.getvalue())
        self.assertNotIn("secret", buffer.getvalue())

    def test_check_evidence(self):
        text = "Save 20%\nfor the busy"
        self.assertIsNone(angles.check_evidence(self.line(text, angle_offer="discount", offer_evidence="Save  20%"), text))
        self.assertEqual(angles.check_evidence(self.line(text, angle_offer="discount", offer_evidence="Half price"), text),
                         "offer_evidence not in the ad text")

    def test_apply_counts_and_rows(self):
        self.ad("1", "Save 20%", "for the busy"); self.ad("2", "Save 20%", "for the busy")
        self.ad("3", "Other", "words"); self.ad("4", None, " ")
        self.write_labels([self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Save 20%",
                                     angle_message="convenience", message_evidence="for the busy")])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))
        rows = self.table("ad_angles")
        self.assertEqual([(r["key"], r["angle_offer"], r["offer_evidence"], r["angle_message"], r["angle_voice"],
                           r["voice_evidence"]) for r in rows],
                         [("1", "discount", "Save 20%", "convenience", "brand", None),
                          ("2", "discount", "Save 20%", "convenience", "brand", None)])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (2, 1, 1))
        self.assertEqual(len(self.table("ad_angles")), 2)

    def test_apply_rejects_evidence_that_is_not_in_the_text(self):
        self.ad("1", "Save 20%", "for the busy")
        self.write_labels([self.line("Save 20%\nfor the busy", angle_offer="discount", offer_evidence="Half price")])
        with self.assertRaises(angles.LabelError) as e:
            angles.apply_labels(self.conn, self.labels)
        self.assertEqual(str(e.exception), "line 1: offer_evidence not in the ad text")

    def test_failed_apply_leaves_rows_as_they_were(self):
        self.ad("1", "A", "b")
        self.write_labels([self.line("A\nb")])
        angles.apply_labels(self.conn, self.labels); self.conn.commit()
        self.write_labels([self.line("A\nb", angle_offer="sale")])
        with self.assertRaises(angles.LabelError):
            angles.apply_labels(self.conn, self.labels)
        self.conn.rollback()
        self.assertEqual(len(self.table("ad_angles")), 1)

    def test_read_labels_names_the_line(self):
        good = json.dumps(self.line("one"))
        bad = json.dumps(self.line("two", angle_offer="sale"))
        for lines, n, reason in [([good, "not json"], 2, "not JSON"),
                                 ([good, good], 2, "duplicate text_sha256"),
                                 ([good, good.replace('"test"', '"x"'), bad], 2, "duplicate text_sha256"),
                                 ([good, bad], 2, "angle_offer not in list"),
                                 ([good, "[1]"], 2, "not a JSON object")]:
            self.write_raw(lines)
            with self.assertRaises(angles.LabelError) as e:
                angles.read_labels(self.labels)
            self.assertEqual(e.exception.line, n)
            self.assertEqual(str(e.exception), f"line {n}: {reason}")
        self.write_raw([good, "", bad.replace("sale", "discount")])
        with self.assertRaises(angles.LabelError) as e:
            angles.read_labels(self.labels)
        self.assertTrue(str(e.exception).startswith("line 3: "))

    def test_unknown_hash_and_missing_file_are_fine(self):
        self.ad("1", "A", "b")
        self.write_labels([self.line("no such ad\nat all")])
        self.assertEqual(angles.apply_labels(self.conn, self.labels), (0, 1, 0))
        self.assertEqual(angles.apply_labels(self.conn, self.dir / "none.jsonl"), (0, 1, 0))
        self.assertEqual(angles.read_labels(self.dir / "none.jsonl"), {})

    def test_pending(self):
        self.ad("1", "Save 20%", "x", brand="b1", channel="meta"); self.ad("2", "Save 20%", "x", brand="b2", channel="site")
        self.ad("3", "Solo", "y"); self.ad("4", None, None); self.ad("5", "Done", "z")
        self.write_labels([self.line("Done\nz")])
        self.assertEqual(angles.pending(self.conn, self.labels), [
            {"text_sha256": angles.text_hash("Save 20%\nx"), "text": "Save 20%\nx", "brands": ["b1", "b2"],
             "channels": ["meta", "site"], "kinds": ["ad"], "ads": 2},
            {"text_sha256": angles.text_hash("Solo\ny"), "text": "Solo\ny", "brands": ["b"], "channels": ["meta"],
             "kinds": ["ad"], "ads": 1}])

    def test_main_pending_prints_json_lines(self):
        self.ad("3", "Solo", "y")
        self.write_labels([])
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), contextlib.redirect_stdout(buffer):
            code = angles.main(["--pending", "--labels", str(self.labels)])
        self.assertEqual(code, 0)
        out = [json.loads(x) for x in buffer.getvalue().splitlines()]
        self.assertEqual(out, [{"text_sha256": angles.text_hash("Solo\ny"), "text": "Solo\ny", "brands": ["b"],
                                "channels": ["meta"], "kinds": ["ad"], "ads": 1}])

    def test_committed_labels_file_is_valid(self):
        angles.read_labels(angles.LABELS_FILE)


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: self._create("beta", kw)))
        self.messages = SimpleNamespace(create=lambda **kw: self._create("plain", kw))

    def _create(self, which, kwargs):
        self.calls.append((which, kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def reply(payload, stop_reason="end_turn", **extra):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="thinking", thinking="x"),
                                                             SimpleNamespace(type="text", text=text)], **extra)


def answer(**over):
    base = {"angle_offer": "none", "offer_evidence": "", "angle_message": "none", "message_evidence": "",
            "angle_voice": "brand", "voice_evidence": ""}
    return {**base, **over}


class LabelTest(AngleBase):
    NOW = "2026-11-11T03:04:05Z"

    def setUp(self):
        super().setUp()
        self.ad("1", "Save 20%", "for the busy")
        self.write_labels([])

    def lines(self):
        return [json.loads(x) for x in self.labels.read_text(encoding="utf-8").splitlines() if x.strip()]

    def run_label(self, client, model=angles.DEFAULT_MODEL):
        return angles.label_pending(self.conn, self.labels, client, model, self.NOW)

    def test_valid_answer_is_appended(self):
        client = FakeClient([reply(answer(angle_offer="discount", offer_evidence="Save 20%"))])
        self.assertEqual(self.run_label(client), (1, 0))
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["labeled_by"], "claude-opus-5-5/prompt-v1")
        self.assertEqual(lines[0]["labeled_at"], self.NOW)
        self.assertEqual(lines[0]["list_version"], 1)
        self.assertEqual(lines[0]["text_sha256"], angles.text_hash("Save 20%\nfor the busy"))
        self.assertEqual(lines[0]["offer_evidence"], "Save 20%")
        self.assertIsNone(lines[0]["message_evidence"])
        self.assertIsNone(lines[0]["voice_evidence"])
        self.assertEqual(len(angles.read_labels(self.labels)), 1)
        (which, kw), = client.calls
        self.assertEqual(which, "beta")
        self.assertEqual(kw["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(kw["fallbacks"], "default")
        self.assertEqual(kw["max_tokens"], 4000)
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertEqual(kw["messages"], [{"role": "user", "content": "Save 20%\nfor the busy"}])
        self.assertEqual(kw["system"], angles.SYSTEM_PROMPT)
        self.assertEqual(kw["output_config"]["effort"], "low")
        fmt = kw["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        props = fmt["schema"]["properties"]
        self.assertEqual(props["angle_offer"]["enum"], list(angles.OFFER))
        self.assertEqual(props["angle_message"]["enum"], list(angles.MESSAGE))
        self.assertEqual(props["angle_voice"]["enum"], list(angles.VOICE))
        for banned in ("thinking", "temperature", "top_p"):
            self.assertNotIn(banned, kw)

    def test_labeled_by_names_the_model_that_answered(self):
        client = FakeClient([reply(answer(), model="claude-opus-4-8")])
        self.assertEqual(self.run_label(client), (1, 0))
        line = self.lines()[0]
        self.assertEqual(line["labeled_by"], "claude-opus-4-8/prompt-v1")
        self.assertEqual(set(line), set(angles.KEYS))
        self.assertIsNone(angles.check_label(line))

    def test_labeled_by_falls_back_to_the_requested_model(self):
        for extra in ({}, {"model": ""}, {"model": None}):
            self.write_labels([])
            self.assertEqual(self.run_label(FakeClient([reply(answer(), **extra)])), (1, 0))
            self.assertEqual(self.lines()[0]["labeled_by"], "claude-opus-5-5/prompt-v1", extra)

    def test_append_after_a_file_without_a_final_newline(self):
        other = self.line("Other\ntext")
        self.labels.write_text(json.dumps(other), encoding="utf-8")
        self.assertEqual(self.run_label(FakeClient([reply(answer())])), (1, 0))
        self.assertEqual(len(angles.read_labels(self.labels)), 2)

    def test_other_model_uses_the_plain_endpoint(self):
        client = FakeClient([reply(answer())])
        self.assertEqual(self.run_label(client, "claude-haiku-5-5"), (1, 0))
        (which, kw), = client.calls
        self.assertEqual(which, "plain")
        self.assertNotIn("betas", kw)
        self.assertNotIn("fallbacks", kw)
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(self.lines()[0]["labeled_by"], "claude-haiku-5-5/prompt-v1")

    def test_bad_answers_write_nothing(self):
        import anthropic
        request = mock.Mock()
        bad = [reply(answer(angle_offer="discount", offer_evidence="Half price")),
               reply(answer(angle_voice="creator", voice_evidence="ask @someone")),
               reply(answer(), stop_reason="refusal"),
               reply(answer(), stop_reason="max_tokens"),
               reply("not json at all"),
               reply(answer(angle_offer="discount", offer_evidence="")),
               anthropic.APIConnectionError(request=request)]
        for item in bad:
            client = FakeClient([item])
            self.assertEqual(self.run_label(client), (0, 1), item)
            self.assertEqual(self.labels.read_text(), "")

    def test_failure_reasons(self):
        import anthropic
        response = mock.Mock(status_code=429, headers={})
        cases = [(reply(answer(), stop_reason="refusal"), "refusal"),
                 (reply(answer(), stop_reason="max_tokens"), "max_tokens"),
                 (reply("nope"), "not_json"),
                 (anthropic.RateLimitError("x", response=response, body=None), "api: RateLimitError"),
                 (anthropic.APIConnectionError(request=mock.Mock()), "api: APIConnectionError")]
        for item, reason in cases:
            with self.assertRaises(angles.LabelFailure) as e:
                angles.ask_model(FakeClient([item]), angles.DEFAULT_MODEL, "t")
            self.assertEqual(e.exception.reason, reason)

    def test_auth_errors_are_not_caught_by_ask_model(self):
        import anthropic
        response = mock.Mock(status_code=401, headers={})
        client = FakeClient([anthropic.AuthenticationError("x", response=response, body=None)])
        with self.assertRaises(anthropic.AuthenticationError):
            angles.ask_model(client, angles.DEFAULT_MODEL, "t")

    def bad_request(self):
        import anthropic
        import httpx2 as httpx
        response = httpx.Response(400, request=httpx.Request("POST", "https://example.test"))
        body = {"type": "error", "error": {"type": "invalid_request_error",
                                           "message": "Your credit   balance is too low\nto access the API."}}
        return anthropic.BadRequestError("x", response=response, body=body)

    def test_ask_model_lets_a_bad_request_through(self):
        import anthropic
        client = FakeClient([self.bad_request()])
        with self.assertRaises(anthropic.BadRequestError):
            angles.ask_model(client, angles.DEFAULT_MODEL, "t")

    def test_bad_request_stops_the_run(self):
        import anthropic
        self.ad("2", "Other", "words")
        client = FakeClient([reply(answer()), self.bad_request()])
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), \
                mock.patch.object(angles, "read_key", return_value="k"), \
                mock.patch.object(anthropic, "Anthropic", return_value=client), \
                contextlib.redirect_stdout(buffer):
            code = angles.main(["--label", "--labels", str(self.labels)])
        self.assertEqual(code, 1)
        self.assertEqual(buffer.getvalue().splitlines()[-1],
                         "label: could not look: bad_request: Your credit balance is too low to access the API.")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(self.lines()), 1)

    def test_empty_evidence_becomes_none(self):
        got = angles.ask_model(FakeClient([reply(answer())]), angles.DEFAULT_MODEL, "t")
        self.assertEqual(set(got), {"angle_offer", "offer_evidence", "angle_message", "message_evidence",
                                    "angle_voice", "voice_evidence", "model"})
        self.assertIsNone(got["offer_evidence"])
        self.assertIsNone(got["message_evidence"])
        self.assertIsNone(got["voice_evidence"])

    def test_labeled_text_is_not_asked_again(self):
        self.write_labels([self.line("Save 20%\nfor the busy")])
        client = FakeClient([])
        self.assertEqual(self.run_label(client), (0, 0))
        self.assertEqual(client.calls, [])

    def test_failed_text_does_not_stop_the_others(self):
        self.ad("2", "Other", "words")
        client = FakeClient([reply("nope"), reply(answer())])
        self.assertEqual(self.run_label(client), (1, 1))
        self.assertEqual(len(self.lines()), 1)

    def test_main_without_key(self):
        before = self.labels.read_text()
        buffer = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["DATABASE_URL"] = self.url
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(angles, "read_key", return_value=None), \
                contextlib.redirect_stdout(buffer):
            code = angles.main(["--label", "--labels", str(self.labels)])
        self.assertEqual(code, 1)
        self.assertEqual(buffer.getvalue().strip(), "label: could not look: missing_key")
        self.assertEqual(self.labels.read_text(), before)

    def test_main_label_reports_and_exit_code(self):
        self.ad("2", "Other", "words")
        client = FakeClient([reply("nope"), reply(answer())])
        buffer = io.StringIO()
        fake_module = mock.Mock()
        fake_module.Anthropic.return_value = client
        import anthropic
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), \
                mock.patch.object(angles, "read_key", return_value="k"), \
                mock.patch.object(anthropic, "Anthropic", fake_module.Anthropic), \
                contextlib.redirect_stdout(buffer):
            code = angles.main(["--label", "--labels", str(self.labels)])
        out = buffer.getvalue().splitlines()
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 2)
        self.assertRegex(out[0], r"^label: failed [0-9a-f]{12}: not_json$")
        self.assertEqual(out[1], "label: labeled=1 failed=1 pending=1")
        fake_module.Anthropic.assert_called_once_with(api_key="k", max_retries=0)

    def test_main_label_auth_error(self):
        import anthropic
        response = mock.Mock(status_code=401, headers={})
        client = FakeClient([anthropic.AuthenticationError("x", response=response, body=None)])
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": self.url}), \
                mock.patch.object(angles, "read_key", return_value="k"), \
                mock.patch.object(anthropic, "Anthropic", return_value=client), \
                contextlib.redirect_stdout(buffer):
            code = angles.main(["--label", "--labels", str(self.labels)])
        self.assertEqual(code, 1)
        self.assertEqual(buffer.getvalue().strip(), "label: could not look: auth")
        self.assertEqual(self.labels.read_text(), "")

    def test_main_label_and_pending_are_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            angles.main(["--label", "--pending"])

    def test_read_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "from-env"}):
            self.assertEqual(angles.read_key(), "from-env")
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            env_file = self.dir / ".env"
            env_file.write_text('OTHER=1\nANTHROPIC_API_KEY="quoted"\n')
            with mock.patch.object(angles, "ENV_FILE", env_file):
                self.assertEqual(angles.read_key(), "quoted")
            env_file.write_text("ANTHROPIC_API_KEY=\n")
            with mock.patch.object(angles, "ENV_FILE", env_file):
                self.assertIsNone(angles.read_key())
            with mock.patch.object(angles, "ENV_FILE", self.dir / "missing"):
                self.assertIsNone(angles.read_key())

    def test_answer_schema(self):
        s = angles.answer_schema()
        self.assertEqual(s["required"], ["angle_offer", "offer_evidence", "angle_message", "message_evidence",
                                         "angle_voice", "voice_evidence"])
        self.assertIs(s["additionalProperties"], False)
        self.assertEqual(s["type"], "object")
        self.assertEqual(s["properties"]["angle_offer"]["enum"], list(angles.OFFER))
        self.assertEqual(s["properties"]["angle_message"]["enum"], list(angles.MESSAGE))
        self.assertEqual(s["properties"]["angle_voice"]["enum"], list(angles.VOICE))
        self.assertEqual(s["properties"]["voice_evidence"], {"type": "string"})

    def test_system_prompt_carries_the_rules(self):
        p = angles.SYSTEM_PROMPT
        for value in angles.OFFER + angles.MESSAGE + angles.VOICE:
            self.assertIn(value, p)
        for phrase in ("12 words", "@", "exactly"):
            self.assertIn(phrase, p)


if __name__ == "__main__":
    import unittest
    unittest.main()
