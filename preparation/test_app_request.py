"""
Offline tests for app_request.py -- the local copy of the app's extraction call.

    python -m unittest preparation/test_app_request.py -v

No network, no GPU, no PDF: every case is a string. Each one pins a behaviour
read off perjanjian-baku-bi (sys-prompt @ e028187), so a change in the app
shows up here as a failing expectation rather than as a quietly mismatched
training set.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_request as app  # noqa: E402


def clause(pasal, text, topic="t"):
    return {"pasal": pasal, "topic": topic, "clause_text": text}


EIGHT = "satu dua tiga empat lima enam tujuh delapan"


class Request(unittest.TestCase):
    def test_body_is_exactly_what_postChatCompletion_marshals(self):
        body = app.request_body("ISI", "SYS")
        self.assertEqual(list(body), ["model", "messages", "max_tokens", "response_format"])
        self.assertEqual(body["model"], "scalejade/qwen-sea-lion-v4.5-27b-it")
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "DOCUMENT:\nISI"},
        ])
        self.assertEqual(body["max_tokens"], 65536)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        for absent in ("temperature", "max_completion_tokens", "chat_template_kwargs"):
            self.assertNotIn(absent, body)

    def test_system_prompt_is_sent_unstripped(self):
        raw = app.SYSTEM_PROMPT.read_bytes().decode("utf-8")
        self.assertEqual(app.system_prompt(), raw)
        self.assertTrue(raw.startswith("# Peran dan Konteks"))


class Fits(unittest.TestCase):
    def test_estimate_is_utf8_bytes_over_four(self):
        self.assertEqual(app.estimate_tokens("abcd" * 10), 10)
        self.assertEqual(app.estimate_tokens("é" * 4), 2)       # 8 bytes

    def test_boundary(self):
        system = "x" * 4000                                     # 1,000 tokens
        available = 262_144 - 1000 - 65_536 - 1000
        doc, avail = app.check_fits("y" * (available * 4), system)
        self.assertEqual((doc, avail), (available, available))
        with self.assertRaises(app.AppError):
            app.check_fits("y" * (available * 4 + 4), system)


class ExtractJSON(unittest.TestCase):
    def test_fences(self):
        self.assertEqual(app.extract_json_value('```json\n{"a":1}\n```'), '{"a":1}')
        self.assertEqual(app.extract_json_value('```\n[1]\n```'), "[1]")

    def test_text_around_and_think_block(self):
        self.assertEqual(app.extract_json_value('<think>\n\n</think>\n\n{"clauses":[]}'),
                         '{"clauses":[]}')
        self.assertEqual(app.extract_json_value('Berikut hasilnya: {"a":1} selesai.'), '{"a":1}')

    def test_array_wins_only_when_it_comes_first(self):
        self.assertEqual(app.extract_json_value('[{"a":1}]'), '[{"a":1}]')
        self.assertEqual(app.extract_json_value('{"clauses":[1]}'), '{"clauses":[1]}')

    def test_first_opener_to_last_closer(self):
        # Not a balanced-brace parser: two objects become one invalid span.
        self.assertEqual(app.extract_json_value('{"a":1} {"b":2}'), '{"a":1} {"b":2}')


class ParseReply(unittest.TestCase):
    def test_envelope(self):
        got = app.parse_reply(json.dumps({"clauses": [clause("1. A|1", EIGHT)]}))
        self.assertEqual(got, [app.Clause("1. A|1", "t", EIGHT)])

    def test_bare_array_fallback(self):
        got = app.parse_reply(json.dumps([clause("1", EIGHT)]))
        self.assertEqual([c.pasal for c in got], ["1"])

    def test_empty_envelope_is_a_failed_attempt(self):
        # len(envelope.Clauses) == 0 falls through to the array parse, which
        # cannot take an object.
        for reply in ('{"clauses":[]}', '{"other":1}'):
            with self.assertRaises(app.AppError):
                app.parse_reply(reply)

    def test_keys_match_case_insensitively_like_encoding_json(self):
        got = app.parse_reply('{"Clauses":[{"PASAL":"1","Topic":"x","Clause_Text":"y"}]}')
        self.assertEqual(got, [app.Clause("1", "x", "y")])

    def test_null_field_is_empty_wrong_type_fails(self):
        got = app.parse_reply('{"clauses":[{"pasal":"1","topic":null,"clause_text":"y"}]}')
        self.assertEqual(got[0].topic, "")
        with self.assertRaises(app.AppError):
            app.parse_reply('{"clauses":[{"pasal":1,"topic":"x","clause_text":"y"}]}')

    def test_not_json(self):
        with self.assertRaises(app.AppError):
            app.parse_reply("maaf, saya tidak bisa")


class ReplyContent(unittest.TestCase):
    def resp(self, content, finish="stop"):
        return json.dumps({"choices": [{"message": {"content": content},
                                        "finish_reason": finish}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 65536}})

    def test_full_response_unwrapped(self):
        self.assertEqual(app.reply_content(self.resp('{"clauses":[]}')), '{"clauses":[]}')

    def test_truncated_reply_is_an_error(self):
        with self.assertRaises(app.AppError):
            app.reply_content(self.resp('{"clauses":[{"pasal":"1"', "length"))

    def test_plain_model_text_passes_through(self):
        self.assertEqual(app.reply_content('{"clauses":[]}'), '{"clauses":[]}')


class Finalize(unittest.TestCase):
    def test_short_clauses_dropped(self):
        kept, dropped = app.finalize([
            app.Clause("1", "t", EIGHT),
            app.Clause("2", "t", "Nasabah adalah perorangan pemilik Rekening di Bank."),  # 7
        ])
        self.assertEqual([c.pasal for c in kept], ["1"])
        self.assertIn("under 8 words", dropped[0][1])

    def test_repeated_pasal_dropped_after_normalising(self):
        kept, dropped = app.finalize([
            app.Clause("1. Definisi|2", "t", EIGHT),
            app.Clause("1. DEFINISI|2", "t", EIGHT),
        ])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped[0][1], "pasal already seen")

    def test_normalisation_deletes_separators(self):
        # '|', '.', '-' are removed with no space put back, so distinct pasal
        # values can collide. Pinned because it is the app's behaviour.
        self.assertEqual(app.normalize_clause_name("1. Definisi|3-8"), "1 definisi38")
        self.assertEqual(app.normalize_clause_name("2.1|1"), app.normalize_clause_name("21|1"))


if __name__ == "__main__":
    unittest.main()
