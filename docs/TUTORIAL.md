# ProofDesk tutorial

About 10 minutes. You need Python 3.10 or newer. Nothing else to install and no account.

## 1. Start it

Not comfortable with a terminal? Use the download in [INSTALL.md](INSTALL.md) and skip to step 2.

For developers:

```
git clone https://github.com/Geezusotl/proofdesk
cd proofdesk
PYTHONPATH=src python3 -m proofdesk serve
```

On Windows PowerShell: `$env:PYTHONPATH="src"; python -m proofdesk serve`.
(`pip install .` should also give you a `proofdesk` command, but that path is untested. The `PYTHONPATH` way above is the tested one.)

Your browser opens at http://127.0.0.1:8765. The first time, a short **Guide** card appears at the bottom left. Reopen it any time with the **Guide** button.

The page only listens on your own computer. Nothing is sent anywhere unless you choose the Anthropic model (step 7).

## 2. Ask a question

The sample documents are a handbook for a made-up company, Brindle Labs. Click **What is the company mascot?** and then **Ask**.

You get one sentence ending in a small numbered circle. That number is the source.

## 3. Check the source

Click the number. The document opens on the right, scrolled to the exact sentence the answer relies on, highlighted in yellow. The rest of the passage is lightly shaded.

This is the point of ProofDesk: you never have to take the answer on trust. Before showing a claim, ProofDesk checks that the cited passage really contains it. A claim that fails the check is dropped.

## 4. Ask something the documents don't cover

Click **What is the capital of France?**. ProofDesk says it can't find that in the documents instead of guessing. Open **Closest passages** to see what it did find.

## 5. See how an answer was found

Ask **How many vacation days do full-time employees get?** and open **How this was found**. You see the passages searched, their scores and the matching words. "Vacation" finds "paid time off" through a short built-in synonym list.

## 6. Use your own documents

- **One document:** click **Add document**, paste text or choose a `.txt` / `.md` file. It lasts until you stop the server.
- **A folder:** `proofdesk serve --docs path/to/folder` loads every `.md`, `.markdown` and `.txt` file in it.
- **Sample files to edit:** `proofdesk sample my-docs` copies the handbook so you can change it.

Tips: use headings (`# Title`, `## Section`) so answers can show where they came from, and keep one topic per document.

## 7. Use a real language model (optional)

The default **offline model** quotes the best matching sentence. It runs without a key but cannot rephrase or combine facts. For fuller answers:

```
export ANTHROPIC_API_KEY=your-key
proofdesk serve --model anthropic
```

Passages are sent to the Anthropic API with your question. The same checks apply: a claim not supported by its cited passage is removed. Pick a model with `--model-name`.

## 8. Command line

```
proofdesk ask "How soon must a SEV1 incident get a response?"   # exit 0 answered, 1 refused, 2 error
proofdesk ask "..." --json                                       # full details
proofdesk eval                                                    # run the 82 test questions
```

## What ProofDesk won't do

- It searches by words, not meaning. A question phrased very differently from the document can come back as "not found".
- The offline model sometimes refuses questions the documents do answer. It would rather say nothing than something wrong.
- It checks that a claim is **in** the cited passage. It does not check that the document itself is true.

## Troubleshooting

- *Port in use:* add `--port 9000`.
- *Browser didn't open:* go to the printed address.
- *"No API key":* set `ANTHROPIC_API_KEY` in the same terminal.
