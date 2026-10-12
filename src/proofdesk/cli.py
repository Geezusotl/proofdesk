"""Command line: ``proofdesk serve``, ``ask``, ``eval`` and ``sample``."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .answer import answer
from .corpus import CorpusError, load_folder
from .models import ModelError, get_model
from .retrieve import Index

SAMPLE_DIR = Path(__file__).parent / "sample"


def _documents(args):
    if args.docs:
        return load_folder(args.docs), False
    return load_folder(SAMPLE_DIR), True


def _model(args):
    kwargs = {"model": args.model_name} if args.model_name else {}
    return get_model(args.model, **kwargs)


def _common(p, docs=True):
    if docs:
        p.add_argument("--docs", metavar="FOLDER", help="folder of .md/.markdown/.txt files (default: the bundled sample handbook)")
    p.add_argument("--model", default="offline", choices=("offline", "anthropic"),
                   help="'offline' needs no key; 'anthropic' uses the ANTHROPIC_API_KEY environment variable")
    p.add_argument("--model-name", metavar="NAME", help="model id for --model anthropic (or set PROOFDESK_MODEL)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proofdesk", description="Ask questions about your documents and check every answer against its source.")
    parser.add_argument("--version", action="version", version=f"proofdesk {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="open the web interface")
    _common(serve)
    serve.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765; 0 picks a free one)")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1, this computer only)")
    serve.add_argument("--no-browser", action="store_true", help="do not open a browser tab")

    ask = sub.add_parser("ask", help="answer one question in the terminal")
    ask.add_argument("question")
    _common(ask)
    ask.add_argument("-k", type=int, default=5, help="passages to retrieve (default 5)")
    ask.add_argument("--show-unverified", action="store_true", help="also show claims that failed verification")
    ask.add_argument("--json", action="store_true", help="print the full answer as JSON")

    ev = sub.add_parser("eval", help="measure retrieval and answer quality on a question set")
    _common(ev)
    ev.add_argument("--questions", metavar="FILE", help="question file (default: eval/questions.json next to the code, if present)")
    ev.add_argument("--write", metavar="FILE", help="also write the report to this file")

    smp = sub.add_parser("sample", help="copy the sample handbook to a folder so you can read or edit it")
    smp.add_argument("folder", help="destination folder (created if needed)")
    return parser


def _cmd_serve(args) -> int:
    from .server import App, create_server  # imported late so 'ask' stays fast
    docs, sample = _documents(args)
    app = App(docs, _model(args), sample=sample)
    try:
        server = create_server(app, args.host, args.port)
    except OSError:
        if args.port == 0:
            raise
        print(f"Port {args.port} is busy (is ProofDesk already open?). Picking another one.")
        server = create_server(app, args.host, 0)
    port = server.server_address[1]
    url = f"http://{'127.0.0.1' if args.host in ('127.0.0.1', 'localhost') else args.host}:{port}/"
    print(f"ProofDesk {__version__} is running at {url}")
    print(f"  documents: {len(docs)} ({'bundled sample handbook' if sample else args.docs}), model: {app.model.name}")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("  WARNING: this address is reachable from other computers and there is no login.")
    print("  Keep this window open while you use ProofDesk. Close it (or press Ctrl+C) to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def _cmd_ask(args) -> int:
    docs, _ = _documents(args)
    index = Index(docs)
    ans = answer(args.question, index, _model(args), k=args.k, strict=not args.show_unverified)
    if args.json:
        print(json.dumps(ans.to_dict(), indent=2, ensure_ascii=False))
        return 1 if ans.abstained else 0
    if ans.abstained:
        print(ans.message)
        for r in ans.retrieved[:3]:
            print(f"  closest: {r['passage_id']}  {r['preview'][:90]!r}")
        for problem in ans.problems:
            print(f"  problem: {problem}")
        return 1
    print(ans.text)
    print()
    for c in ans.citations:
        flag = "" if c["verified"] else "  (NOT VERIFIED)"
        where = c["title"] + (f" > {c['section']}" if c["section"] else "")
        print(f"[{c['n']}] {where}  ({c['passage_id']}){flag}")
        print(f"    \"{c['quote']}\"")
    for problem in ans.problems:
        print(f"note: {problem}")
    return 0


def _cmd_eval(args) -> int:
    from . import evaluate as ev
    path = Path(args.questions) if args.questions else Path(__file__).resolve().parents[2] / "eval" / "questions.json"
    if not path.is_file():
        raise CorpusError(f"Question file not found: {path}. Pass one with --questions.")
    docs, _ = _documents(args)
    model = _model(args)
    results = ev.run(ev.load_questions(path), Index(docs), model)
    report = ev.format_report(ev.summarise(results), results, model.name)
    print(report)
    if args.write:
        Path(args.write).write_text(report + "\n", encoding="utf-8")
    return 0


def _cmd_sample(args) -> int:
    dest = Path(args.folder)
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(SAMPLE_DIR.glob("*.md")):
        shutil.copyfile(f, dest / f.name)
    print(f"Copied {len(list(SAMPLE_DIR.glob('*.md')))} documents to {dest}")
    print(f"Try: proofdesk serve --docs {dest}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("--") and argv[0] not in ("--version", "-h", "--help"):
        argv = ["serve"] + argv  # double-clicking the app (no arguments) opens the interface
    args = build_parser().parse_args(argv)
    try:
        return {"serve": _cmd_serve, "ask": _cmd_ask, "eval": _cmd_eval, "sample": _cmd_sample}[args.command](args)
    except (CorpusError, ModelError, OSError) as exc:
        print(f"proofdesk: error: {exc}", file=sys.stderr)
        return 2
