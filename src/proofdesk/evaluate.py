"""Measure retrieval and answer quality against questions with a known answer key.

Each answerable question lists the passage that holds the answer (``evidence``: a document id and a snippet that
must appear in the passage) and words the answer must contain. Unanswerable questions must be refused.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .answer import answer


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()


def passage_has(passage, evidence: dict) -> bool:
    return passage.doc_id == evidence["doc"] and norm(evidence["contains"]) in norm(passage.text)


def load_questions(path) -> list:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


@dataclass
class QuestionResult:
    q: dict
    rank: int = 0                 # retrieval rank of the first correct passage (0 = not in the top 10)
    abstained: bool = False
    correct: bool = False         # answerable: right text and a citation to the right passage. unanswerable: refused.
    cited_right: bool = False
    answer_text: str = ""
    citation_problems: list = field(default_factory=list)


def check_citations(index, ans) -> list:
    """Every citation must point at real text that really is in the document."""
    problems = []
    for c in ans.citations:
        doc = index.documents.get(c["doc_id"])
        if doc is None:
            problems.append(f"[{c['n']}] unknown document {c['doc_id']}")
            continue
        if not (0 <= c["passage_start"] <= c["span_start"] < c["span_end"] <= c["passage_end"] <= len(doc.text)):
            problems.append(f"[{c['n']}] span is outside its passage")
        elif doc.text[c["span_start"]:c["span_end"]] != c["quote"]:
            problems.append(f"[{c['n']}] quote is not the text at its offsets")
        if not c["verified"]:
            problems.append(f"[{c['n']}] shown although unverified")
    return problems


def run(questions, index, model, k: int = 5, strict: bool = True) -> list:
    results = []
    for q in questions:
        res = QuestionResult(q)
        ans = answer(q["question"], index, model, k=k, strict=strict)
        res.abstained, res.answer_text = ans.abstained, ans.text
        res.citation_problems = check_citations(index, ans)
        if q["answerable"]:
            for hit in index.search(q["question"], 10):
                if any(passage_has(hit.passage, ev) for ev in q["evidence"]):
                    res.rank = hit.rank
                    break
            cited = [index.passage(c["passage_id"]) for c in ans.citations]
            res.cited_right = any(passage_has(p, ev) for p in cited for ev in q["evidence"])
            has_words = any(norm(w) in norm(ans.text) for w in q["answer_contains"])
            res.correct = (not ans.abstained) and has_words and res.cited_right
        else:
            res.correct = ans.abstained
        results.append(res)
    return results


def summarise(results) -> dict:
    def rate(n, d):
        return round(n / d, 4) if d else None
    out = {}
    groups = defaultdict(list)
    for r in results:
        groups["all"].append(r)
        groups[r.q.get("split", "dev")].append(r)
    for name, rs in groups.items():
        ans = [r for r in rs if r.q["answerable"]]
        una = [r for r in rs if not r.q["answerable"]]
        out[name] = {
            "questions": len(rs), "answerable": len(ans), "unanswerable": len(una),
            "hit@1": rate(sum(1 for r in ans if r.rank == 1), len(ans)),
            "hit@3": rate(sum(1 for r in ans if 0 < r.rank <= 3), len(ans)),
            "hit@5": rate(sum(1 for r in ans if 0 < r.rank <= 5), len(ans)),
            "mrr": round(sum(1 / r.rank for r in ans if r.rank) / len(ans), 4) if ans else None,
            "answer_correct": rate(sum(r.correct for r in ans), len(ans)),
            "false_refusals": rate(sum(r.abstained for r in ans), len(ans)),
            "wrong_answers": rate(sum((not r.abstained) and (not r.correct) for r in ans), len(ans)),
            "refused_correctly": rate(sum(r.correct for r in una), len(una)),
            "citation_problems": sum(len(r.citation_problems) for r in rs),
            "by_kind": {kind: rate(sum(r.correct for r in rs if r.q["kind"] == kind),
                                   sum(1 for r in rs if r.q["kind"] == kind))
                        for kind in sorted({r.q["kind"] for r in rs})},
        }
    return out


def failures(results) -> list:
    out = []
    for r in results:
        if r.q["answerable"] and not r.correct:
            what = ("refused to answer" if r.abstained else
                    "answered, but the text or citation is wrong: " + r.answer_text[:120])
            where = "correct passage not retrieved" if not r.rank else f"correct passage ranked {r.rank}"
            out.append(f"{r.q['id']} ({r.q['kind']}) {r.q['question']} -> {what}; {where}")
        elif not r.q["answerable"] and not r.correct:
            out.append(f"{r.q['id']} (unanswerable) {r.q['question']} -> answered: {r.answer_text[:120]}")
        for p in r.citation_problems:
            out.append(f"{r.q['id']} citation problem: {p}")
    return out


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def format_report(summary: dict, results, model_name: str) -> str:
    lines = [f"Model: {model_name}", ""]
    header = f"{'':26}" + "".join(f"{name:>12}" for name in summary)
    lines.append(header)
    rows = [("Questions", "questions", False), ("Retrieval hit@1", "hit@1", True), ("Retrieval hit@3", "hit@3", True),
            ("Retrieval hit@5", "hit@5", True), ("Answered correctly", "answer_correct", True),
            ("Refused wrongly", "false_refusals", True), ("Wrong answer shown", "wrong_answers", True),
            ("Unanswerable refused", "refused_correctly", True), ("Citation problems", "citation_problems", False)]
    for label, key, is_pct in rows:
        lines.append(f"{label:<26}" + "".join(f"{(pct(s[key]) if is_pct else s[key]):>12}" for s in summary.values()))
    kinds = sorted({k for s in summary.values() for k in s["by_kind"]})
    for kind in kinds:
        lines.append(f"{'Correct: ' + kind:<26}" + "".join(f"{pct(s['by_kind'].get(kind)):>12}" for s in summary.values()))
    problems = failures(results)
    if problems:
        lines += ["", "Failures:"] + [f"  - {p}" for p in problems]
    return "\n".join(lines)
