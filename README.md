# ProofDesk

Ask questions about your documents. Every answer links to the sentence that supports it, and unsupported claims are removed.

![status](https://img.shields.io/badge/python-3.10%2B-blue) ![deps](https://img.shields.io/badge/dependencies-none-green) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

- **Click a citation, see the proof.** The source document opens with the exact sentence highlighted.
- **Says "I don't know."** If the documents don't cover a question, you get a refusal and the closest passages, not a guess.
- **Checks the model.** Citations are verified in code against the document text. Fabricated or mismatched citations are dropped.
- **Runs offline.** No API key, no packages, no network. Python standard library only.

## Quick start

```
git clone https://github.com/Geezusotl/proofdesk
cd proofdesk
PYTHONPATH=src python3 -m proofdesk serve
```

Open http://127.0.0.1:8765 and follow the Guide card. Full walkthrough: [docs/TUTORIAL.md](docs/TUTORIAL.md).

(The `proofdesk` command from `pip install .` is untested; the `python -m proofdesk` form above is what the tests use.)

Use your own files: `proofdesk serve --docs my-folder` (`.md`, `.txt`).
Use a real model: `ANTHROPIC_API_KEY=... proofdesk serve --model anthropic`.

## How it works

1. **Chunk** documents into passages that keep exact character offsets.
2. **Retrieve** with BM25 plus a small synonym table.
3. **Answer** with a model that must cite passages as `[n]`.
4. **Verify** each claim against the passage it cites; drop what fails; refuse if nothing survives.
5. **Show** the answer with each citation pointing at the exact sentence.

## Tests

```
python -m unittest discover -s tests -t .
python -m proofdesk eval
```

52 tests: unit, adversarial scripted models (fake citations, prompt injection), the Anthropic client against a local stub server, HTTP server security, CLI, fuzzing, and browser tests (skipped without Playwright).

## Honest limits

- The built-in offline model is a simple extractive stand-in. It shows the pipeline works; it does not show how good answers from a real model are. **The Anthropic path is tested only against a local stub, not live.**
- The 82-question evaluation ([eval/RESULTS.md](eval/RESULTS.md)) was written by the same author as the sample documents and the checker, so it is a regression check, not an independent benchmark. Offline results: 0 wrong answers shown, 0 citation problems, about 21% of answerable questions wrongly refused.
- Retrieval is lexical. Heavy paraphrase can miss.
- Verification checks the answer against the document, not whether the document is correct.

## License

MIT
