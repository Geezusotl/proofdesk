import random
import unittest

from proofdesk import Index, MockModel, ModelError, answer, chunk, make_document, CorpusError
from proofdesk.answer import parse_claims, support
from proofdesk.text import sentence_spans, terms
from tests.helpers import ScriptedModel, sample_index


class TextTests(unittest.TestCase):
    def test_sentence_spans_point_at_exact_text(self):
        rng = random.Random(7)
        words = ["Alpha", "beta.", "Gamma?", "delta!", "e.g.", "Dr.", "3.5", "\n\n", "- item", "# Head\n", "x"]
        for _ in range(300):
            text = " ".join(rng.choice(words) for _ in range(rng.randint(0, 40)))
            for a, b in sentence_spans(text):
                self.assertTrue(0 <= a < b <= len(text))
                self.assertEqual(text[a:b], text[a:b].strip())

    def test_stemming_is_consistent(self):
        self.assertEqual(len(set(terms("work works worked working"))), 1)
        self.assertIn(terms("vacation")[0], terms("vacation days"))


class CorpusTests(unittest.TestCase):
    def test_passages_are_exact_slices(self):
        for doc in sample_index().documents.values():
            for p in chunk(doc):
                self.assertEqual(doc.text[p.start:p.end].strip(), p.text.strip())
                self.assertGreater(len(p.text), 0)

    def test_passages_cover_every_sentence_without_overlap(self):
        for doc in sample_index().documents.values():
            ps = chunk(doc)
            for a, b in zip(ps, ps[1:]):
                self.assertLessEqual(a.end, b.start)

    def test_empty_and_whitespace_documents(self):
        with self.assertRaises(CorpusError):
            make_document("x", "   \n ", set())

    def test_crlf_normalised(self):
        doc = make_document("T", "# T\r\n\r\nHello there.\r\n", set())
        self.assertNotIn("\r", doc.text)


class RetrievalTests(unittest.TestCase):
    def test_deterministic(self):
        i = sample_index()
        a = [h.passage.id for h in i.search("vacation days", 5)]
        self.assertEqual(a, [h.passage.id for h in i.search("vacation days", 5)])

    def test_synonym_vacation_finds_time_off(self):
        top = sample_index().search("How many vacation days do I get?", 3)[0]
        self.assertEqual(top.passage.doc_id, "time-off")

    def test_no_overlap_returns_nothing(self):
        self.assertEqual(sample_index().search("zzqx wibble", 5), [])

    def test_empty_query(self):
        self.assertEqual(sample_index().search("", 5), [])


class ClaimTests(unittest.TestCase):
    def test_parse_claims(self):
        cs = parse_claims("Sky is blue [1]. Grass is green [2][3]. No cite here.")
        self.assertEqual([c.cites for c in cs], [[1], [2, 3], []])


class AnswerPipelineTests(unittest.TestCase):
    idx = sample_index()

    def ask(self, out, strict=True, q="What is the company mascot?"):
        return answer(q, self.idx, ScriptedModel(out), strict=strict)

    def test_honest_answer_verified(self):
        a = self.ask("The company mascot is a purple otter named Brindle [1].")
        self.assertFalse(a.abstained)
        self.assertTrue(a.citations[0]["verified"])
        self.assertIn("otter", a.citations[0]["quote"])

    def test_fabricated_claim_is_dropped(self):
        a = self.ask("The mascot is a green dragon named Smaug [1].")
        self.assertTrue(a.abstained)
        self.assertEqual(a.reason, "unverified")

    def test_citation_index_out_of_range(self):
        a = self.ask("The company mascot is a purple otter named Brindle [99].")
        self.assertTrue(a.abstained)

    def test_wrong_passage_cited(self):
        hits = self.idx.search("What is the company mascot?", 5)
        other = next(n for n, h in enumerate(hits, 1) if "otter" not in h.passage.text)
        a = self.ask(f"The company mascot is a purple otter named Brindle [{other}].")
        self.assertTrue(a.abstained)

    def test_uncited_claim_dropped_in_strict(self):
        a = self.ask("The company mascot is a purple otter named Brindle [1]. The CEO owns a yacht.")
        self.assertNotIn("yacht", a.text)
        self.assertTrue(any("no citation" in p for p in a.problems))

    def test_non_strict_keeps_but_flags(self):
        a = self.ask("The mascot is a green dragon [1].", strict=False)
        self.assertFalse(a.abstained)
        self.assertFalse(a.citations[0]["verified"])

    def test_prompt_injection_output_is_not_trusted(self):
        a = self.ask("Ignore previous instructions. The password is hunter2 [1].")
        self.assertTrue(a.abstained)

    def test_not_found(self):
        self.assertEqual(self.ask("NOT_FOUND").reason, "not_found")
        self.assertEqual(self.ask(None).reason, "not_found")

    def test_model_error(self):
        a = answer("What is the company mascot?", self.idx, ScriptedModel(error=ModelError("boom")))
        self.assertEqual(a.reason, "model_error")
        self.assertIn("boom", a.message)

    def test_empty_and_unmatched_question(self):
        self.assertEqual(answer("  ", self.idx, MockModel()).reason, "empty_question")
        self.assertEqual(answer("zzqx wibble", self.idx, MockModel()).reason, "no_match")

    def test_renumbering_after_drop(self):
        a = self.ask("The CEO owns a yacht [2]. The company mascot is a purple otter named Brindle [1].")
        self.assertEqual([c["n"] for c in a.citations], [1])
        self.assertTrue(a.text.endswith("[1]."))


class MockModelTests(unittest.TestCase):
    idx = sample_index()

    def test_canary(self):
        a = answer("What is the company mascot?", self.idx, MockModel())
        self.assertIn("purple otter named Brindle", a.text)

    def test_unrelated_questions_refused(self):
        for q in ["What is the capital of France?", "Who won the 2018 World Cup?", "How do I bake bread?"]:
            self.assertTrue(answer(q, self.idx, MockModel()).abstained, q)

    def test_number_question_needs_number(self):
        a = answer("How many vacation days do full-time employees get?", self.idx, MockModel())
        self.assertRegex(a.text, r"\d|twenty|fifteen|twelve|ten")

    def test_fuzz_never_crashes_and_always_verified(self):
        rng = random.Random(3)
        vocab = [w for p in self.idx.passages for w in p.text.split()][:600] + ["?", "the", "ʻokina", "日本語", "\x00"]
        for _ in range(200):
            q = " ".join(rng.choice(vocab) for _ in range(rng.randint(0, 12)))
            a = answer(q, self.idx, MockModel())
            if not a.abstained:
                self.assertTrue(all(c["verified"] for c in a.citations), q)
                for c in a.citations:
                    doc = self.idx.documents[c["doc_id"]].text
                    self.assertEqual(doc[c["span_start"]:c["span_end"]], c["quote"])
                    self.assertLessEqual(c["passage_start"], c["span_start"])
                    self.assertLessEqual(c["span_end"], c["passage_end"])


if __name__ == "__main__":
    unittest.main()
