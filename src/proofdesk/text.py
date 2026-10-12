"""Tokenising and sentence splitting. Everything here is deterministic and stdlib-only."""
from __future__ import annotations

import re

STOPWORDS = frozenset("""
a an and are as at be been being but by for from had has have he her his how i if in into is it its
of on or our she so than that the their them then there these they this to us was we were what when
where which who whom why will with you your do does did can could should would may might must not no
about any all also am both each more most other some such only own same too very just over under
again further once up down out off while during before after above below between through those
get gets got per""".split())

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")


def stem(word: str) -> str:
    """A deliberately light stemmer: plurals and -ing/-ed only, so unrelated words are not merged."""
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses"):
        word = word[:-2]
    elif word.endswith(("xes", "zes", "ches", "shes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    for suffix in ("ing", "ed", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "lsz":
                word = word[:-1]  # "planning" -> "plann" -> "plan"
            break
    if word.endswith("e") and len(word) > 4:
        word = word[:-1]  # "approve" and "approved" both become "approv"
    return word


def tokens(text: str) -> list:
    """Lower-cased word tokens. Numbers keep decimals; thousands separators are removed (1,200 -> 1200)."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    out = []
    for tok in _TOKEN.findall(text):
        if tok[0].isdigit():
            tok = tok.replace(",", "")
        out.append(tok.strip(".,"))
    return [t for t in out if t]


def terms(text: str) -> list:
    """Searchable terms: stemmed, with stopwords removed. Repeats are kept (BM25 needs them)."""
    return [stem(t) for t in tokens(text) if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


# -- sentences ------------------------------------------------------------------

_ABBREVIATIONS = frozenset({"e.g", "i.e", "etc", "vs", "dr", "mr", "mrs", "ms", "no", "approx", "inc", "ltd",
                            "st", "fig", "eq", "al", "est", "min", "max", "dept"})
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*•]|\d{1,3}[.)])[ \t]+", re.M)
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_END = re.compile(r"[.!?][\"')\]]*[ \t]*\n?[ \t]*")


def sentence_spans(text: str, base: int = 0) -> list:
    """Return [(start, end)] of each sentence. Offsets are exact: text[start:end] is the sentence.

    Boundaries are placed after ., ! or ? when the next character starts a new sentence, at the start
    of every list item or heading, and at blank lines. Common abbreviations and initials do not split.
    """
    cuts = {0, len(text)}
    for m in _LIST_ITEM.finditer(text):
        cuts.add(m.start())
    for m in _HEADING.finditer(text):
        cuts.add(m.start())
        end_of_line = text.find("\n", m.end())
        cuts.add(len(text) if end_of_line == -1 else end_of_line)
    for m in re.finditer(r"\n[ \t]*\n", text):
        cuts.add(m.start())
        cuts.add(m.end())
    for m in _END.finditer(text):
        nxt = text[m.end(): m.end() + 1]
        if not nxt or not (nxt.isupper() or nxt.isdigit() or nxt in "\"'([#-*"):
            continue
        word_match = re.search(r"([A-Za-z.]+)[.!?][\"')\]]*$", text[max(0, m.start() - 20): m.start() + 1])
        word = word_match.group(1).lower().strip(".") if word_match else ""
        if text[m.start()] == "." and word in _ABBREVIATIONS:
            continue
        cuts.add(m.end())
    points = sorted(cuts)
    spans = []
    for a, b in zip(points, points[1:]):
        chunk = text[a:b]
        stripped = chunk.strip()
        if not stripped:
            continue
        lead = len(chunk) - len(chunk.lstrip())
        spans.append((base + a + lead, base + a + lead + len(stripped)))
    return spans


# -- query expansion ------------------------------------------------------------
# A small, general-purpose table of abbreviations and everyday synonyms, applied to the QUESTION only.
# Each alternative is a tuple of words that must all appear together (they are stemmed when the module loads).
# It is deliberately short: it bridges common gaps ("vacation" vs "paid time off", "CEO" vs "chief executive
# officer") and nothing more. Questions phrased with other words will still miss.
_RAW_SYNONYMS = {
    "vacation": [("holiday",), ("paid", "time"), ("leave",)],
    "pto": [("paid", "time")],
    "ceo": [("chief", "executive", "officer")],
    "cto": [("chief", "technology", "officer")],
    "cfo": [("chief", "financial", "officer")],
    "wfh": [("home",), ("remote",)],
    "laptop": [("computer",)],
    "fired": [("terminat",), ("end", "contract")],
    "salary": [("pay",), ("salaries",)],
    "refund": [("reimburs",), ("money", "back")],
    "insurance": [("coverage",)],
    "sick": [("illness",)],
    "bonus": [("referral", "bonus")],
}

SYNONYMS = {stem(key): [tuple(stem(w) for w in alt) for alt in alts] for key, alts in _RAW_SYNONYMS.items()}
