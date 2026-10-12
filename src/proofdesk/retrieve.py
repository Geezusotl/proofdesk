"""BM25 retrieval over passages. No dependencies, deterministic, and fast enough for thousands of passages."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .corpus import Document, Passage, chunk
from .text import SYNONYMS, terms

K1, B = 1.5, 0.75


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float
    rank: int           # 1 = best
    matched: tuple      # query terms found in the passage (stemmed)


class Index:
    def __init__(self, documents):
        self.documents = {d.id: d for d in documents}
        self.passages = []
        for d in documents:
            self.passages.extend(chunk(d))
        self._by_id = {p.id: p for p in self.passages}
        self._tf, self._len, self._df = [], [], Counter()
        for p in self.passages:
            # The heading and title are searchable too: a passage under "Parental leave" should match that.
            toks = terms(p.text) + terms(p.section) + terms(p.title)
            tf = Counter(toks)
            self._tf.append(tf)
            self._len.append(len(toks))
            self._df.update(tf.keys())
        n = len(self.passages)
        self._avg = (sum(self._len) / n) if n else 0.0

    def __len__(self) -> int:
        return len(self.passages)

    def passage(self, passage_id: str) -> Passage:
        return self._by_id[passage_id]

    def idf(self, term: str) -> float:
        n, df = len(self.passages), self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def query_terms(self, question: str) -> list:
        """Unique searchable terms of a question, in the order they were written."""
        return list(dict.fromkeys(terms(question)))

    def query_groups(self, question: str) -> list:
        """Each question term as a list of alternatives (the term itself first, then its synonyms)."""
        return [[(t,)] + list(SYNONYMS.get(t, [])) for t in self.query_terms(question)]

    def search(self, question: str, k: int = 5) -> list:
        qterms = list(dict.fromkeys(t for group in self.query_groups(question) for alt in group for t in alt))
        if not qterms or not self.passages:
            return []
        scored = []
        for i, p in enumerate(self.passages):
            tf, norm = self._tf[i], K1 * (1 - B + B * self._len[i] / (self._avg or 1))
            score, matched = 0.0, []
            for t in qterms:
                f = tf.get(t, 0)
                if f:
                    score += self.idf(t) * f * (K1 + 1) / (f + norm)
                    matched.append(t)
            if score > 0:
                scored.append((score, i, tuple(matched)))
        # ties are broken by reading order so results never depend on dict ordering
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [Hit(self.passages[i], round(s, 4), r, m) for r, (s, i, m) in enumerate(scored[:k], 1)]
