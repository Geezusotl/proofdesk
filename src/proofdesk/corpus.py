"""Documents and passages.

A document is split into passages (the unit that gets retrieved and cited). Every passage remembers
exactly where it came from: ``document.text[passage.start:passage.end] == passage.text`` always holds,
which is what lets the interface highlight the supporting text in the original document.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .text import sentence_spans

TARGET_CHARS = 500     # passages are grown up to about this size
MAX_CHARS = 900        # a hard ceiling; longer runs are cut at word boundaries
MIN_CHARS = 160        # shorter neighbouring blocks in the same section are merged
MAX_DOC_CHARS = 2_000_000
SUFFIXES = (".md", ".markdown", ".txt")

_HEADING = re.compile(r"^[ \t]*(#{1,6})[ \t]+(.+?)[ \t#]*$")


class CorpusError(Exception):
    """A document could not be loaded."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Passage:
    id: str          # "<doc id>#<n>", n counting from 1 in reading order
    doc_id: str
    title: str       # the document title
    section: str     # nearest heading above the passage ("" if none)
    start: int       # offsets into Document.text
    end: int
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start


def slugify(value: str, fallback: str = "document") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60].strip("-") or fallback


def title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            return m.group(2).strip()
        if line.strip():
            break
    return fallback


def _blocks(text: str) -> list:
    """Paragraph-like blocks as (start, end, section). Heading lines set the section and are not blocks."""
    blocks, section = [], ""
    run_start = run_end = None
    pos = 0

    def close():
        nonlocal run_start, run_end
        if run_start is not None:
            blocks.append((run_start, run_end, section))
        run_start = run_end = None

    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        h = _HEADING.match(body)
        if h:
            close()
            section = h.group(2).strip()
        elif not body.strip():
            close()
        else:
            if run_start is None:
                run_start = pos + (len(body) - len(body.lstrip()))
            run_end = pos + len(body.rstrip())
        pos += len(line)
    close()
    return blocks


def _split_long(text: str, start: int, end: int) -> list:
    """Cut one oversized block into spans of about TARGET_CHARS, at sentence ends where possible."""
    spans = sentence_spans(text[start:end], start)
    out, cur = [], None
    for a, b in spans:
        if cur is not None and b - cur[0] > TARGET_CHARS:
            out.append(cur)
            cur = None
        cur = (a, b) if cur is None else (cur[0], b)
    if cur is not None:
        out.append(cur)
    final = []
    for a, b in out:  # a single sentence can still be huge: cut at whitespace
        while b - a > MAX_CHARS:
            cut = text.rfind(" ", a + MAX_CHARS // 2, a + MAX_CHARS)
            cut = a + MAX_CHARS if cut == -1 else cut
            final.append((a, cut))
            a = cut
            while a < b and text[a].isspace():
                a += 1
        if b > a:
            final.append((a, b))
    return final


def chunk(doc: Document) -> list:
    """Split a document into passages."""
    text = doc.text
    pieces = []  # (start, end, section)
    for start, end, section in _blocks(text):
        if end - start > MAX_CHARS:
            pieces.extend((a, b, section) for a, b in _split_long(text, start, end))
        else:
            pieces.append((start, end, section))
    merged = []
    for start, end, section in pieces:
        if merged:
            ps, pe, psec = merged[-1]
            if psec == section and (pe - ps) < MIN_CHARS and (end - ps) <= MAX_CHARS:
                merged[-1] = (ps, end, section)
                continue
        merged.append((start, end, section))
    return [Passage(f"{doc.id}#{n}", doc.id, doc.title, section, s, e, text[s:e])
            for n, (s, e, section) in enumerate(merged, 1)]


def make_document(title: str, text: str, taken: Optional[set] = None, doc_id: Optional[str] = None) -> Document:
    """Build a document with a unique id. Windows line endings are normalised so offsets stay simple."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_DOC_CHARS:
        raise CorpusError(f"{title!r} is longer than {MAX_DOC_CHARS:,} characters.")
    if not text.strip():
        raise CorpusError(f"{title!r} is empty.")
    base = doc_id or slugify(title)
    taken = taken if taken is not None else set()
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    taken.add(candidate)
    return Document(candidate, title.strip() or candidate, text)


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise CorpusError(f"{path.name} looks like a binary file, not text.")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def load_folder(folder, taken: Optional[set] = None) -> list:
    """Load every .md/.markdown/.txt file in a folder (not recursive), in name order."""
    folder = Path(folder)
    if not folder.is_dir():
        raise CorpusError(f"{folder} is not a folder.")
    docs = []
    taken = taken if taken is not None else set()
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES):
        text = read_text_file(path).replace("\r\n", "\n").replace("\r", "\n")
        title = title_from_text(text, path.stem.replace("-", " ").replace("_", " ").title())
        docs.append(make_document(title, text, taken, slugify(path.stem)))
    if not docs:
        raise CorpusError(f"No .md, .markdown or .txt files found in {folder}.")
    return docs
