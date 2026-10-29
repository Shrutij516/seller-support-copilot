# evals

Offline and live evaluation for the RAG chat. Started in phase 4c with retrieval calibration.
Answer-quality and safety evals come later.

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

## Known limitations of this set

- **Author bias.** The same person (with AI assistance) wrote the policies in `data/policies/` and these questions. The questions inherit the policies' vocabulary, which likely inflates hit rates and in-scope scores compared with real sellers' wording. The `paraphrase` slice partly counters this. Real seller questions should replace or extend this set once there are any.
- **Small sample.** 20 in-scope questions means "≥95% kept" is "at most one in-scope question lost". The recommended threshold is only as good as the score gap between the classes in this sample. Read the distributions, not just the single number.
- **One KB snapshot.** Scores depend on the embedding model, chunking and the indexed docs. Re-run after any of those change.
