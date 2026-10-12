# Evaluation results

Regenerate with `python -m proofdesk eval`. A test fails if the table below goes out of date.

## How to read this

- The 82 questions in `questions.json` were written by the same assistant that wrote the sample documents and the checker. That makes this a **regression and plumbing check, not an independent benchmark.** It says little about how ProofDesk does on your documents.
- **dev** (52 questions) was used while building and to pick thresholds. **held_out** (30) was written afterwards and not used for tuning.
- Late change, disclosed: after the first held-out run I added "many" and "much" as stopwords because of a manual test. Metrics did not change, but held_out had already been seen once, so treat it as lightly contaminated.
- The offline model is a simple extractive stand-in. It proves the pipeline (retrieve, quote, cite, verify, refuse). It does not show how well a real language model answers. Run with `--model anthropic` and your own key to see that.
- What matters most here: **"Wrong answer shown" is 0%** and **"Citation problems" is 0**. The offline model prefers refusing to guessing, so the cost shows up as "Refused wrongly" (about 21%).
- Known failures: lexical search cannot bridge some paraphrases ("second parent"), and h22/h27 are near-miss questions where related sentences share words with the question.

## Latest run

```
Model: offline-extractive

                                   all         dev    held_out
Questions                           82          52          30
Retrieval hit@1                  96.8%       95.2%      100.0%
Retrieval hit@3                 100.0%      100.0%      100.0%
Retrieval hit@5                 100.0%      100.0%      100.0%
Answered correctly               79.0%       76.2%       85.0%
Refused wrongly                  21.0%       23.8%       15.0%
Wrong answer shown                0.0%        0.0%        0.0%
Unanswerable refused             90.0%      100.0%       80.0%
Citation problems                    0           0           0
Correct: direct                  87.5%       88.2%       85.7%
Correct: paraphrase              50.0%       25.0%       83.3%
Correct: unanswerable            90.0%      100.0%       80.0%

Failures:
  - d10 (direct) How much is the monthly co-working space allowance? -> refused to answer; correct passage ranked 1
  - d14 (direct) What is the mileage rate for a personal car? -> refused to answer; correct passage ranked 1
  - d15 (direct) How far ahead must travel be booked? -> refused to answer; correct passage ranked 1
  - d23 (direct) How much is the on-call stipend? -> refused to answer; correct passage ranked 1
  - d35 (paraphrase) How many vacation days do new full-time staff receive each year? -> refused to answer; correct passage ranked 2
  - d37 (paraphrase) What is the maximum nightly rate for a hotel in Singapore? -> refused to answer; correct passage ranked 1
  - d39 (paraphrase) Is a doctor's note needed for a short illness? -> refused to answer; correct passage ranked 1
  - d40 (paraphrase) Can I expense an alcoholic drink at a team lunch? -> refused to answer; correct passage ranked 1
  - d41 (paraphrase) What is the hotel limit in Tokyo? -> refused to answer; correct passage ranked 1
  - d42 (paraphrase) Which software is required for storing work passwords? -> refused to answer; correct passage ranked 1
  - h01 (paraphrase) How many weeks of parental leave does the second parent get? -> refused to answer; correct passage ranked 1
  - h03 (direct) Who has to approve spending of more than $5,000? -> refused to answer; correct passage ranked 1
  - h08 (direct) What uptime does the service target? -> refused to answer; correct passage ranked 1
  - h22 (unanswerable) Does Brindle Labs have a gym in the office? -> answered: Brindle Labs also reimburses internet costs up to $40 per month [1].
  - h27 (unanswerable) What is the notice period for resigning after the probation period? -> answered: The first 90 days of employment are a probationary period [1]. Either side can end the contract with one week's notice d
```
