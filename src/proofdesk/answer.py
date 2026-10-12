"""Answer a question and check the answer against the documents.

The model's text is split into claims. Every claim must cite a passage that was really retrieved, and the
cited passage must contain the claim's words and numbers. Anything that fails is removed (strict mode, the
default) and listed under ``problems``. If nothing survives, the answer is withheld instead of shown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .models import ModelError
from .text import sentence_spans, terms

SUPPORT_MIN = 0.6   # share of a claim's words that must appear in a cited passage
MAX_QUESTION_CHARS = 1000

ABSTAIN_MESSAGES = {
    "empty_question": "Type a question to get started.",
    "no_match": "I couldn't find this in the documents. None of them share words with the question.",
    "not_found": "I couldn't find this in the documents. The closest passages are listed below.",
    "unverified": "A draft answer was produced, but it could not be checked against the documents, "
                  "so it isn't shown.",
    "model_error": "The language model could not be used.",
}

_MARKS = re.compile(r"((?:\s*\[\d+\])+)\s*([.!?])?")


@dataclass
class Claim:
    text: str
    cites: list = field(default_factory=list)   # passage numbers as the model wrote them (1-based)


def parse_claims(text: str) -> list:
    """Split model text into claims. A claim ends at its citation marks; text with none is an uncited claim."""
    claims, pos = [], 0
    for m in _MARKS.finditer(text):
        body = text[pos:m.start()].strip(" \n\t.")
        cites = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if body:
            claims.append(Claim(body, cites))
        elif claims and cites:  # "[1] [2]" after an earlier claim adds to it
            claims[-1].cites.extend(cites)
        pos = m.end()
    tail = text[pos:].strip(" \n\t.")
    if tail:
        claims.append(Claim(tail, []))
    return claims


def support(claim: str, passage) -> float:
    """Share of the claim's words found in the passage (heading and title count). Numbers must all match."""
    wanted = set(terms(claim))
    if not wanted:
        return 1.0
    have = set(terms(passage.text)) | set(terms(passage.section)) | set(terms(passage.title))
    if any(t.isdigit() or t[0].isdigit() for t in wanted - have):
        return 0.0
    return len(wanted & have) / len(wanted)


def locate(claim: str, passage) -> tuple:
    """The sentence of the passage that best matches the claim, as absolute offsets into the document."""
    wanted = set(terms(claim))
    best, best_score = (passage.start, passage.end), -1
    for a, b in sentence_spans(passage.text, passage.start):
        score = len(wanted & set(terms(passage.text[a - passage.start:b - passage.start])))
        if score > best_score:
            best, best_score = (a, b), score
    return best


@dataclass
class Answer:
    question: str
    abstained: bool
    reason: Optional[str]
    message: str
    text: str = ""
    claims: list = field(default_factory=list)
    citations: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    retrieved: list = field(default_factory=list)
    model: str = ""

    def to_dict(self) -> dict:
        return {"question": self.question, "abstained": self.abstained, "reason": self.reason,
                "message": self.message, "text": self.text, "claims": self.claims,
                "citations": self.citations, "problems": self.problems, "retrieved": self.retrieved,
                "model": self.model}


def _retrieved(hits, used: set) -> list:
    return [{"passage_id": h.passage.id, "doc_id": h.passage.doc_id, "title": h.passage.title,
             "section": h.passage.section, "score": h.score, "rank": h.rank, "used": h.passage.id in used,
             "matched": list(h.matched), "preview": h.passage.text[:220]} for h in hits]


def _abstain(question, reason, hits, model, problems=(), message=None) -> Answer:
    return Answer(question, True, reason, message or ABSTAIN_MESSAGES[reason], problems=list(problems),
                  retrieved=_retrieved(hits, set()), model=getattr(model, "name", ""))


def answer(question: str, index, model, k: int = 5, strict: bool = True) -> Answer:
    question = (question or "").strip()
    if not question:
        return _abstain(question, "empty_question", [], model)
    question = question[:MAX_QUESTION_CHARS]
    hits = index.search(question, k)
    if not hits:
        return _abstain(question, "no_match", [], model)
    try:
        raw = model.generate(question, hits, index)
    except ModelError as exc:
        return _abstain(question, "model_error", hits, model, [str(exc)],
                        f"{ABSTAIN_MESSAGES['model_error']} {exc}")
    if raw is None or re.fullmatch(r"\W*NOT_FOUND\W*", raw, re.I):
        return _abstain(question, "not_found", hits, model)

    problems, kept = [], []
    for claim in parse_claims(raw):
        good, bad = [], []
        for n in dict.fromkeys(claim.cites):
            if not 1 <= n <= len(hits):
                problems.append(f"Cites passage [{n}] but only {len(hits)} were provided: {claim.text!r}")
                continue
            score = support(claim.text, hits[n - 1].passage)
            (good if score >= SUPPORT_MIN else bad).append((n, score))
        for n, score in bad:
            problems.append(f"Cited passage [{n}] ({hits[n - 1].passage.id}) does not contain this claim "
                            f"(support {score:.0%}): {claim.text!r}")
        if not claim.cites:
            problems.append(f"Claim has no citation: {claim.text!r}")
        if good or not strict:
            kept.append((claim, good or [(n, support(claim.text, hits[n - 1].passage))
                                         for n in dict.fromkeys(claim.cites) if 1 <= n <= len(hits)]))
        # in strict mode a claim with no valid, supporting citation is dropped

    if not kept:
        return _abstain(question, "unverified", hits, model, problems)

    renumber, citations, out_claims = {}, [], []
    for claim, cites in kept:
        marks = []
        for n, score in cites:
            passage = hits[n - 1].passage
            if n not in renumber:
                renumber[n] = len(renumber) + 1
                a, b = locate(claim.text, passage)
                doc_text = index.documents[passage.doc_id].text
                citations.append({"n": renumber[n], "passage_id": passage.id, "doc_id": passage.doc_id,
                                  "title": passage.title, "section": passage.section,
                                  "passage_start": passage.start, "passage_end": passage.end,
                                  "span_start": a, "span_end": b, "quote": doc_text[a:b],
                                  "support": round(score, 3), "verified": score >= SUPPORT_MIN})
            marks.append(renumber[n])
        out_claims.append({"text": claim.text, "cites": marks})
    text = " ".join(c["text"].rstrip(". ") + " " + "".join(f"[{n}]" for n in c["cites"]) + "." for c in out_claims)
    used = {c["passage_id"] for c in citations}
    return Answer(question, False, None, "", text, out_claims, citations, problems,
                  _retrieved(hits, used), getattr(model, "name", ""))
