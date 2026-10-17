"""
Offline tests for evaluate.py and score.py -- the endpoint evaluation.

    python -m unittest preparation/test_evaluate.py -v

No GPU, no RunPod: a local HTTP server stands in for vLLM's OpenAI API, streaming
replies as server-sent events the way vLLM does.
"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_request as app  # noqa: E402
import evaluate  # noqa: E402
import score  # noqa: E402

EIGHT = "satu dua tiga empat lima enam tujuh delapan"
LABELS = json.dumps({"clauses": [
    {"pasal": "1", "topic": "a", "clause_text": f"{EIGHT} sembilan"},
    {"pasal": "2", "topic": "b", "clause_text": f"{EIGHT} sepuluh sebelas"},
    {"pasal": "3", "topic": "c", "clause_text": "pengguna wajib menjaga kerahasiaan pin dan kata sandi akun"},
]})
ROW = {"messages": [
    {"role": "system", "content": "SYS"},
    {"role": "user", "content": "DOCUMENT:\nISI"},
    {"role": "assistant", "content": LABELS},
]}

# model name -> (reply text, finish_reason)
REPLIES = {
    "perfect": (LABELS, "stop"),
    "cut": (LABELS[:40], "length"),
    "prose": ("Berikut klausa-klausanya: tidak ada.", "stop"),
    "one-short": (json.dumps({"clauses": json.loads(LABELS)["clauses"][:2]}), "stop"),
}
SEEN: list[dict] = []
# model name -> 429s still to send before replying as "perfect"; "no-credit" never stops
RATE_LIMITED = {"busy": 1, "no-credit": 99}


class FakeVLLM(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self) -> bool:
        if self.headers.get("Authorization") != "Bearer k":
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        body = json.dumps({"data": [{"id": m} for m in REPLIES]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            return
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(req)
        if RATE_LIMITED.get(req["model"], 0) > 0:
            RATE_LIMITED[req["model"]] -= 1
            code = "insufficient_quota" if req["model"] == "no-credit" else "rate_limit_exceeded"
            body = json.dumps({"error": {"code": code}}).encode()
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        text, finish = REPLIES.get(req["model"], REPLIES["perfect"])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        pieces = [text[i:i + 7] for i in range(0, len(text), 7)]
        for p in pieces:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n".encode())
        self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]})}\n\n".encode())
        usage = {"choices": [], "usage": {"completion_tokens": len(pieces)}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())


class Endpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeVLLM)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_model(self, model):
        return evaluate.run_one(self.base, "k", model, 0, ROW, 65536)

    def test_lists_served_models(self):
        self.assertEqual(evaluate.list_models(self.base, "k"), list(REPLIES))

    def test_bad_key_is_a_clear_failure(self):
        with self.assertRaises(evaluate.Fail):
            evaluate.list_models(self.base, "wrong")

    def test_request_is_the_apps_plus_stream(self):
        SEEN.clear()
        self.run_model("perfect")
        req = SEEN[-1]
        expected = app.request_body("ISI", "SYS", "perfect")
        for k, v in expected.items():
            self.assertEqual(req[k], v, k)
        self.assertTrue(req["stream"])
        self.assertNotIn("temperature", req)

    def test_temperature_is_sent_only_when_asked(self):
        SEEN.clear()
        evaluate.run_one(self.base, "k", "perfect", 0, ROW, 65536, temperature=0.0)
        self.assertEqual(SEEN[-1]["temperature"], 0.0)

    def test_perfect_reply_scores_everything(self):
        r = self.run_model("perfect")
        self.assertEqual((r["finish"], r["finished"], r["json_valid"]), ("stop", True, True))
        self.assertEqual((r["matched"], r["labelled"], r["predicted"]), (3, 3, 3))
        self.assertGreater(r["output_tokens"], 0)

    def test_reply_cut_at_max_tokens_is_a_failure_like_the_app(self):
        r = self.run_model("cut")
        self.assertEqual(r["finish"], "length")
        self.assertFalse(r["finished"])
        self.assertFalse(r["json_valid"])
        self.assertEqual(r["matched"], 0)

    def test_unparseable_reply_is_invalid_with_zero_clauses(self):
        r = self.run_model("prose")
        self.assertTrue(r["finished"])
        self.assertFalse(r["json_valid"])
        self.assertEqual((r["matched"], r["predicted"]), (0, 0))

    def test_missed_clause_lowers_recall_not_precision(self):
        s = score.summarize([self.run_model("one-short")])
        self.assertAlmostEqual(s["recall"], 2 / 3)
        self.assertEqual(s["precision"], 1.0)

    def test_rate_limit_is_retried(self):
        SEEN.clear()
        r = self.run_model("busy")
        self.assertEqual(len(SEEN), 2)
        self.assertEqual((r["matched"], r["labelled"]), (3, 3))

    def test_out_of_credit_is_not_retried(self):
        SEEN.clear()
        r = self.run_model("no-credit")
        self.assertEqual(len(SEEN), 1)
        self.assertIn("insufficient_quota", r["error"])

    def test_unreachable_endpoint_is_an_error_result_not_a_crash(self):
        r = evaluate.run_one("http://127.0.0.1:9/v1", "k", "perfect", 0, ROW, 65536)
        self.assertIn("error", r)


class Rows(unittest.TestCase):
    def test_row_spec(self):
        self.assertEqual(evaluate.parse_rows(None, 3), [0, 1, 2])
        self.assertEqual(evaluate.parse_rows("0,2-3", 5), [0, 2, 3])
        with self.assertRaises(evaluate.Fail):
            evaluate.parse_rows("4", 3)

    def test_self_check_refuses_a_broken_row(self):
        broken = {"messages": [ROW["messages"][0], ROW["messages"][1],
                               {"role": "assistant", "content": "not json"}]}
        with self.assertRaises(evaluate.Fail):
            evaluate.self_check([broken], [0])
        evaluate.self_check([ROW], [0])

    def test_doc_names_fall_back_without_a_report(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(evaluate.row_docs(Path(d) / "test.jsonl", 2), ["row 0", "row 1"])


if __name__ == "__main__":
    unittest.main()
