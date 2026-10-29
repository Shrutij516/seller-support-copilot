# evals

Offline and live evaluation for the RAG chat: retrieval calibration and an end-to-end answer eval (phase 4c).
Safety evals come later.

## Retrieval calibration

- **`retrieval_golden.jsonl`:** 30 labeled questions.
  - **20 in-scope:** each has an `expected_source` (a file in `data/policies/`) and the `expected_fact` a correct answer must contain. All six policy docs are covered. `slice` is `direct` (worded close to the policy) or `paraphrase` (reworded, scenario-style).
  - **10 out-of-scope:** `expected_source: null`. Slices are `general-knowledge`, `other-platform` (Amazon, Etsy, eBay), `nonsense`, and `lookalike`: seller-account questions that sound in-domain but that no policy covers (2FA, sales tax).
- **`calibrate_retrieval.py`:** run with `make eval-retrieval` from the repo root. It calls the live Knowledge Base (id read from the `KnowledgeBaseStack` output) through the same `BedrockKnowledgeBaseRetriever` the chat route uses, with `top_k=5`. It prints and saves to `results/retrieval-<date>.json`:
  - hit@1 and hit@5 over in-scope questions, overall and per slice
  - min / median / max of the top score, in-scope vs out-of-scope
  - the highest threshold that keeps at least 95% of in-scope questions answerable, and how many out-of-scope questions it refuses. The route refuses when no chunk clears `rag_min_score`, so this is computed on each question's top score.
  - distinct chunks per source and the largest chunk. Token counts are **approximate**: whitespace words × 1.33, not a real tokenizer.
- **Unit tests:** the metric and threshold math is tested offline in `services/api/tests/unit/test_calibrate_retrieval.py`.

`scripts/rag_smoke.py` (run with `make rag-smoke Q="..."`) is the companion manual check. It produces one full answer through the route's retrieve → filter → prompt → Converse path, with per-stage latency.

## Answer eval

`answer_eval.py` (run with `make eval-answers`) sends every golden question through `copilot_api.rag.pipeline.answer_question`, the exact function the chat route calls. It uses the current `rag_min_score` (override with `--min-score`), the app's `top_k` and `max_tokens`, and model `us.anthropic.claude-haiku-4-5-20251001-v1:0`. Output goes to `results/answers-<date>.json`.

Scoring is deterministic; there's no LLM judge:

- **In-scope passes** when both of these hold:
  - Every entry in the question's `key_terms` appears in the answer. Before matching, answers are lowercased, whitespace is collapsed, curly quotes and en/em dashes become ASCII, and citation markers like `[2]` are removed, so they can't satisfy a number. A numeric term such as `30` or `2.40` matches only as a whole number: `30` matches "30 days" and "30-day", not "300". `a|b` accepts either alternative.
  - At least one returned citation is from `expected_source`. Citations are already filtered to the ones the answer marks with `[n]`.
- **Out-of-scope passes** when the answer has **zero citations** and matches this refusal pattern (case-insensitive): "I don't know" / "I do not know"; "couldn't / could not / can't / cannot find"; "can't / cannot / am unable to answer"; "don't have / contain / include / cover (any) information / details"; "no / not enough information"; "isn't / is not / not covered / mentioned / addressed / included / described"; "doesn't / does not cover / mention / address / include / describe". The exact regex is `REFUSAL_PATTERN` in `answer_eval.py` and is saved in each results file. The pipeline's own refusal (nothing above the floor, so no model call) matches it.

The run prints pass rates per slice, every failure (question, first 200 characters of the answer, citations, reasons), total Converse input/output tokens, and an **estimated** cost. The estimate uses Bedrock on-demand pricing for Claude 4.5 Haiku on the Geo / in-region cross-region table, US East (N. Virginia): $1.10 per 1M input tokens and $5.50 per 1M output, viewed 2026-10-29 at https://aws.amazon.com/bedrock/pricing/. It excludes Retrieve costs. Scoring is unit-tested offline in `services/api/tests/unit/test_answer_eval.py`.

## Known limitations of this set

- **Author bias.** The same person (with AI assistance) wrote the policies in `data/policies/` and these questions. The questions inherit the policies' vocabulary, which likely inflates hit rates and in-scope scores compared with real sellers' wording. The `paraphrase` slice partly counters this. Real seller questions should replace or extend this set once there are any.
- **Small sample.** 20 in-scope questions means "≥95% kept" is "at most one in-scope question lost". The recommended threshold is only as good as the score gap between the classes in this sample. Read the distributions, not just the single number.
- **Clarification requests fail the out-of-scope check.** An answer that asks the user to clarify (as for `out-08`, "asdf qwer zxcv") with zero citations is safe behavior, but it doesn't match the deterministic refusal pattern, so it's scored as a failure. This is deliberate: the pattern isn't widened to chase individual answers, because every widening also risks accepting real non-refusals. Read these failures by hand. If a clarification is what the product should do, decide that explicitly rather than editing the regex to make a number go up.
- **One KB snapshot.** Scores depend on the embedding model, chunking and the indexed docs. Re-run after any of those change.
