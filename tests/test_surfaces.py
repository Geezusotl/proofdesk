import contextlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from proofdesk import AnthropicModel, Index, MockModel, ModelError, answer, get_model, load_folder
from proofdesk import cli, evaluate as ev
from proofdesk.server import App, create_server
from tests.helpers import QUESTIONS, ROOT, SAMPLE, sample_index


class StubAPI:
    """A local stand-in for the Messages API."""
    def __init__(self, status=200, body=None, raw=None):
        outer = self
        self.requests = []
        self.status, self.body, self.raw = status, body, raw

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                outer.requests.append((dict(self.headers), json.loads(self.rfile.read(n))))
                payload = outer.raw if outer.raw is not None else json.dumps(outer.body).encode()
                self.send_response(outer.status)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1/messages"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class AnthropicModelTests(unittest.TestCase):
    def run_model(self, **stub):
        s = StubAPI(**stub)
        self.addCleanup(s.close)
        m = AnthropicModel(api_key="k", url=s.url, timeout=5)
        hits = sample_index().search("What is the company mascot?", 5)
        return s, m, lambda: m.generate("What is the company mascot?", hits, sample_index())

    def test_success_and_request_shape(self):
        s, m, go = self.run_model(body={"content": [{"type": "text", "text": "A purple otter [1]."}]})
        self.assertEqual(go(), "A purple otter [1].")
        headers, body = s.requests[0]
        headers = {k.lower(): v for k, v in headers.items()}
        self.assertEqual(headers["x-api-key"], "k")
        self.assertIn("anthropic-version", headers)
        self.assertIn("untrusted", body["system"].lower())
        self.assertIn("[1]", body["messages"][0]["content"])

    def test_pipeline_rejects_fabricated_api_answer(self):
        s, m, _ = self.run_model(body={"content": [{"type": "text", "text": "The mascot is a dragon [1]."}]})
        self.assertTrue(answer("What is the company mascot?", sample_index(), m).abstained)

    def test_http_errors(self):
        for status in (401, 500):
            _, _, go = self.run_model(status=status, body={"error": {"message": "nope"}})
            with self.assertRaises(ModelError) as cm:
                go()
            self.assertIn(str(status), str(cm.exception))

    def test_bad_json_and_no_content(self):
        _, _, go = self.run_model(raw=b"<html>")
        self.assertRaises(ModelError, go)
        _, _, go = self.run_model(body={"nothing": 1})
        self.assertRaises(ModelError, go)

    def test_unreachable(self):
        m = AnthropicModel(api_key="k", url="http://127.0.0.1:1/x", timeout=2)
        with self.assertRaises(ModelError):
            m.generate("q", sample_index().search("mascot", 3), sample_index())

    def test_missing_key(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(ModelError):
                AnthropicModel()
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old

    def test_get_model(self):
        self.assertIsInstance(get_model("offline"), MockModel)
        self.assertRaises(ModelError, get_model, "nonsense")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(load_folder(SAMPLE), MockModel(), sample=True)
        cls.srv = create_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def call(self, method, path, body=None, headers=None, raw=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_page_assets_and_csp(self):
        for path in ("/", "/static/app.js", "/static/app.css"):
            status, _, headers = self.call("GET", path)
            self.assertEqual(status, 200, path)
        self.assertIn("default-src 'none'", headers.get("Content-Security-Policy") or self.call("GET", "/")[2]["Content-Security-Policy"])

    def test_static_whitelist(self):
        self.assertEqual(self.call("GET", "/static/../server.py")[0], 404)
        self.assertEqual(self.call("GET", "/static/index.html")[0], 404)

    def test_ask_roundtrip(self):
        status, body, _ = self.call("POST", "/api/ask", {"question": "What is the company mascot?"})
        self.assertEqual(status, 200)
        self.assertIn("purple otter", json.loads(body)["text"])

    def test_bad_requests(self):
        self.assertEqual(self.call("POST", "/api/ask", raw=b"{nope")[0], 400)
        self.assertEqual(self.call("POST", "/api/ask", {"question": 5})[0], 400)
        self.assertEqual(self.call("POST", "/api/ask", headers={"Content-Type": "text/plain"}, raw=b"{}")[0], 415)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)  # announce a huge body, send none
        conn.putrequest("POST", "/api/ask")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "1600000")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)

    def test_host_and_origin_guards(self):
        self.assertEqual(self.call("GET", "/api/docs", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.call("POST", "/api/ask", {"question": "mascot"},
                                   headers={"Origin": "http://evil.example"})[0], 403)

    def test_add_ask_delete_document(self):
        status, body, _ = self.call("POST", "/api/docs", {"title": "Pets", "text": "# Pets\n\nThe office cat is called Whiskers and sleeps on the printer."})
        self.assertEqual(status, 201)
        doc_id = json.loads(body)["id"]
        a = json.loads(self.call("POST", "/api/ask", {"question": "What is the office cat called?"})[1])
        self.assertIn("Whiskers", a["text"])
        self.assertEqual(self.call("DELETE", "/api/docs/" + doc_id)[0], 200)
        self.assertEqual(self.call("DELETE", "/api/docs/" + doc_id)[0], 404)
        a = json.loads(self.call("POST", "/api/ask", {"question": "What is the office cat called?"})[1])
        self.assertNotIn("Whiskers", a["text"])

    def test_empty_document_rejected(self):
        self.assertEqual(self.call("POST", "/api/docs", {"title": "x", "text": "  "})[0], 400)


class CliAndEvalTests(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_ask_exit_codes(self):
        self.assertEqual(self.run_cli("ask", "What is the company mascot?")[0], 0)
        self.assertEqual(self.run_cli("ask", "What is the capital of France?")[0], 1)
        self.assertEqual(self.run_cli("ask", "x", "--docs", "/no/such/folder")[0], 2)

    def test_ask_json(self):
        code, out, _ = self.run_cli("ask", "What is the company mascot?", "--json")
        self.assertIn("purple otter", json.loads(out)["text"])

    def test_sample_copy(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_cli("sample", d)[0], 0)
            self.assertEqual(len(list(Path(d).glob("*.md"))), 10)

    def test_eval_floors(self):
        results = ev.run(ev.load_questions(QUESTIONS), sample_index(), MockModel())
        s = ev.summarise(results)
        for split, m in s.items():
            self.assertEqual(m["wrong_answers"], 0, split)
            self.assertEqual(m["citation_problems"], 0, split)
            self.assertGreaterEqual(m["hit@5"], 0.95, split)
            self.assertGreaterEqual(m["answer_correct"], 0.7, split)

    def test_every_question_evidence_exists(self):
        idx = sample_index()
        for q in ev.load_questions(QUESTIONS):
            for e in q.get("evidence", []):
                text = " ".join(idx.documents[e["doc"]].text.split()).lower()
                self.assertIn(" ".join(e["contains"].split()).lower(), text, q["id"])
            if q["answerable"]:
                self.assertTrue(q["answer_contains"], q["id"])

    def test_results_file_is_current(self):
        path = ROOT / "eval" / "RESULTS.md"
        if not path.exists():
            self.skipTest("RESULTS.md not generated yet")
        results = ev.run(ev.load_questions(QUESTIONS), sample_index(), MockModel())
        fresh = ev.format_report(ev.summarise(results), results, MockModel().name)
        self.assertIn(fresh.strip(), path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class DoubleClickTests(unittest.TestCase):
    """The downloadable app is started with no arguments and must open the interface."""

    def routed(self, argv):
        from unittest import mock
        with mock.patch.object(cli, "_cmd_serve", return_value=0) as serve:
            cli.main(argv)
        return serve.call_args[0][0] if serve.called else None

    def test_no_arguments_serves(self):
        self.assertEqual(self.routed([]).command, "serve")

    def test_flags_only_serves(self):
        args = self.routed(["--no-browser", "--port", "0"])
        self.assertEqual((args.command, args.port, args.no_browser), ("serve", 0, True))

    def test_version_still_works(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_busy_port_falls_back(self):
        import socket
        from unittest import mock
        busy = socket.socket(); busy.bind(("127.0.0.1", 0)); busy.listen(1)
        port = busy.getsockname()[1]
        self.addCleanup(busy.close)
        real = cli.__dict__.get("webbrowser")
        with mock.patch("webbrowser.open"), mock.patch("proofdesk.server.ThreadingHTTPServer.serve_forever",
                                                       side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(["serve", "--port", str(port)])
        self.assertEqual(code, 0)
        self.assertIn("busy", out.getvalue())

    def test_launcher_and_scripts_exist(self):
        for name in ("packaging/launcher.py", "Start ProofDesk.bat", "Start ProofDesk.command", "start-proofdesk.sh",
                     "docs/INSTALL.md", ".github/workflows/release.yml"):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertTrue(os.access(ROOT / "Start ProofDesk.command", os.X_OK))
