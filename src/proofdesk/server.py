"""A small local web server for ProofDesk, using only the standard library.

It binds to 127.0.0.1 by default and rejects requests whose Host or Origin header is not the server itself, which
stops other websites from talking to it through your browser. Documents you add in the browser live in memory
until you stop the server.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__
from .answer import MAX_QUESTION_CHARS, answer
from .corpus import MAX_DOC_CHARS, CorpusError, make_document
from .retrieve import Index

UI_DIR = Path(__file__).parent / "ui"
STATIC = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
MAX_BODY = 1_500_000
MAX_DOCS = 200
LOOPBACK = {"127.0.0.1", "localhost", "[::1]", "::1"}


class App:
    """The documents, the search index and the model, shared by all requests."""

    def __init__(self, documents, model, sample: bool = False):
        self.model, self.sample = model, sample
        self._lock = threading.Lock()
        self._docs = {d.id: d for d in documents}
        self._index = Index(list(self._docs.values()))

    @property
    def index(self) -> Index:
        return self._index

    def _rebuild(self) -> None:
        self._index = Index(list(self._docs.values()))

    def list_docs(self) -> list:
        counts = {}
        for p in self._index.passages:
            counts[p.doc_id] = counts.get(p.doc_id, 0) + 1
        return [{"id": d.id, "title": d.title, "chars": len(d.text), "passages": counts.get(d.id, 0)}
                for d in self._docs.values()]

    def get_doc(self, doc_id: str):
        doc = self._docs.get(doc_id)
        if doc is None:
            return None
        passages = [{"id": p.id, "start": p.start, "end": p.end, "section": p.section}
                    for p in self._index.passages if p.doc_id == doc_id]
        return {"id": doc.id, "title": doc.title, "text": doc.text, "passages": passages}

    def add_doc(self, title: str, text: str) -> dict:
        with self._lock:
            if len(self._docs) >= MAX_DOCS:
                raise CorpusError(f"A maximum of {MAX_DOCS} documents can be open at once.")
            doc = make_document(title, text, set(self._docs))
            self._docs[doc.id] = doc
            self._rebuild()
            return {"id": doc.id, "title": doc.title}

    def remove_doc(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._docs:
                return False
            del self._docs[doc_id]
            self._rebuild()
            return True

    def ask(self, question: str, k: int = 5, strict: bool = True) -> dict:
        return answer(question, self._index, self.model, k=k, strict=strict).to_dict()

    def config(self) -> dict:
        return {"version": __version__, "model": self.model.name, "model_description": self.model.description,
                "sample": self.sample, "limits": {"question": MAX_QUESTION_CHARS, "document": MAX_DOC_CHARS}}


class BadRequest(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def make_handler(app: App, port: int, check_host: bool):
    allowed_hosts = {f"{h}:{port}" for h in LOOPBACK} | LOOPBACK

    class Handler(BaseHTTPRequestHandler):
        server_version = f"ProofDesk/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        # -- helpers -----------------------------------------------------------
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                             "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        def _guard(self) -> None:
            host = (self.headers.get("Host") or "").lower()
            if check_host and host not in allowed_hosts:
                raise BadRequest("This server only answers requests addressed to localhost.", 403)
            if self.command in ("POST", "DELETE", "PUT", "PATCH"):
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).netloc.lower() != host:
                    raise BadRequest("Cross-site requests are not allowed.", 403)

        def _body_json(self) -> dict:
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise BadRequest("Send the request body as application/json.", 415)
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                raise BadRequest("Bad Content-Length.") from None
            if length > MAX_BODY:
                raise BadRequest(f"The request is larger than {MAX_BODY // 1000} KB.", 413)
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8") or "null")
            except (ValueError, UnicodeDecodeError):
                raise BadRequest("The request body is not valid JSON.") from None
            if not isinstance(data, dict):
                raise BadRequest("The request body must be a JSON object.")
            return data

        def _dispatch(self, handler) -> None:
            try:
                self._guard()
                handler()
            except BadRequest as exc:
                self._error(exc.status, str(exc))
            except CorpusError as exc:
                self._error(400, str(exc))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:  # noqa: BLE001 - never leak a traceback to the browser
                self._error(500, "Something went wrong on the server.")

        # -- routes ------------------------------------------------------------
        def do_GET(self):
            self._dispatch(self._get)

        do_HEAD = do_GET

        def do_POST(self):
            self._dispatch(self._post)

        def do_DELETE(self):
            self._dispatch(self._delete)

        def _get(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                return self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/static/") and path[8:] in STATIC:
                return self._send(200, (UI_DIR / path[8:]).read_bytes(), STATIC[path[8:]])
            if path == "/api/config":
                return self._json(200, app.config())
            if path == "/api/docs":
                return self._json(200, app.list_docs())
            if path.startswith("/api/docs/"):
                doc = app.get_doc(path[len("/api/docs/"):])
                return self._json(200, doc) if doc else self._error(404, "No such document.")
            self._error(404, "Not found.")

        def _post(self):
            path = urlparse(self.path).path
            data = self._body_json()
            if path == "/api/ask":
                question = data.get("question")
                if not isinstance(question, str):
                    raise BadRequest('"question" must be a string.')
                k = data.get("k", 5)
                if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 10:
                    raise BadRequest('"k" must be a whole number from 1 to 10.')
                return self._json(200, app.ask(question, k, strict=data.get("strict", True) is not False))
            if path == "/api/docs":
                title, text = data.get("title"), data.get("text")
                if not isinstance(title, str) or not isinstance(text, str):
                    raise BadRequest('"title" and "text" must be strings.')
                return self._json(201, app.add_doc(title or "Untitled", text))
            self._error(404, "Not found.")

        def _delete(self):
            path = urlparse(self.path).path
            if path.startswith("/api/docs/") and app.remove_doc(unquote(path[len("/api/docs/"):])):
                return self._json(200, {"deleted": True})
            self._error(404, "No such document.")

    return Handler


def create_server(app: App, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build (but do not start) the server. Port 0 picks a free port."""
    holder = {}

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = Server((host, port), lambda *a, **kw: holder["handler"](*a, **kw))
    holder["handler"] = make_handler(app, server.server_address[1], check_host=host in LOOPBACK or host == "localhost")
    return server
