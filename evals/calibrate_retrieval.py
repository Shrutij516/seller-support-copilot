"""Calibrate the RAG relevance floor (rag_min_score) against a labeled question set.

Calls the live Bedrock Knowledge Base (costs a little; run by hand via `make eval-retrieval`)
through the same BedrockKnowledgeBaseRetriever the chat route uses, so scores and chunk
sources are exactly what production would see. For every question in retrieval_golden.jsonl
it records the top score, hit@1 / hit@5 (expected_source among the top 1 / top 5 chunks),
and each chunk's source and approximate size, then:

- prints hit@1 and hit@5 over in-scope questions,
- prints the top-score distribution (min / median / max) for in-scope vs out-of-scope,
- recommends the highest threshold that still keeps >= 95% of in-scope questions answerable
  (top score >= threshold), and reports how many out-of-scope questions it would refuse,
- prints per-source distinct chunk counts and the largest chunk seen,
- writes everything to evals/results/retrieval-<date>.json.

Token counts are approximate: whitespace-separated words x 1.33, not a real tokenizer.

The route refuses when no chunk clears the floor, i.e. when the TOP score is below it, so the
threshold is chosen on top scores.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from matching import contains_all_terms

from copilot_api.config import Settings
from copilot_api.rag.bedrock import (
    BedrockKnowledgeBaseRetriever,
    create_bedrock_agent_runtime_client,
)
from copilot_api.rag.types import RetrievedChunk

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_GOLDEN = EVALS_DIR / "retrieval_golden.jsonl"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"
WORDS_TO_TOKENS = 1.33
IN_SCOPE_KEEP_TARGET = 0.95


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    question: str
    in_scope: bool
    slice: str
    expected_source: str | None
    expected_fact: str | None
    # Machine-checkable form of expected_fact, used by answer_eval.py (all must appear;
    # "a|b" means either). None for out-of-scope questions.
    key_terms: list[str] | None = None


@dataclass
class ChunkRecord:
    source: str
    score: float
    approx_tokens: int
    text_sha1: str
    # Start of the chunk text, so a results file shows where a chunk begins (boundary splits).
    excerpt: str = ""
    # Whether this chunk alone contains every key term of the question (None: out-of-scope).
    has_fact: bool | None = None


@dataclass
class QuestionResult:
    id: str
    question: str
    in_scope: bool
    slice: str
    expected_source: str | None
    top_score: float | None
    hit_at_1: bool | None
    hit_at_5: bool | None
    # Passage level: a chunk from expected_source that itself contains every key term.
    fact_hit_at_1: bool | None = None
    fact_hit_at_5: bool | None = None
    chunks: list[ChunkRecord] = field(default_factory=list)


def write_new_results(results_dir: Path, prefix: str, day: date, payload: dict[str, Any]) -> Path:
    """Write `payload` to a results file that never replaces an existing one: the first run of
    a day is `<prefix>-<date>.json`, later runs `<prefix>-<date>-02.json`, `-03`, ... Opened
    with exclusive create, so even a race can't overwrite a baseline.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    base = f"{prefix}-{day.isoformat()}"
    candidates = [results_dir / f"{base}.json"] + [
        results_dir / f"{base}-{n:02d}.json" for n in range(2, 100)
    ]
    text = json.dumps(payload, indent=2) + "\n"
    for path in candidates:
        try:
            with path.open("x") as fh:
                fh.write(text)
        except FileExistsError:
            continue
        return path
    raise RuntimeError(f"more than 99 {prefix} results for {day.isoformat()} in {results_dir}")


def load_golden(path: Path) -> list[GoldenQuestion]:
    questions = [
        GoldenQuestion(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()
    ]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate ids in {path}")
    for q in questions:
        if q.in_scope != (q.expected_source is not None):
            raise ValueError(f"{q.id}: in_scope must match whether expected_source is set")
        if q.in_scope != bool(q.key_terms):
            raise ValueError(f"{q.id}: in-scope questions (only) need key_terms")
    return questions


def approx_tokens(text: str) -> int:
    return round(len(text.split()) * WORDS_TO_TOKENS)


def chunk_has_fact(question: GoldenQuestion, chunk: RetrievedChunk) -> bool:
    """The chunk comes from the expected doc AND contains every key term. Requiring the source
    stops a generic number (e.g. "14") in an unrelated doc from counting as the fact.
    """
    return (
        question.expected_source is not None
        and chunk.source == question.expected_source
        and contains_all_terms(question.key_terms or [], chunk.text)
    )


def score_question(question: GoldenQuestion, chunks: list[RetrievedChunk]) -> QuestionResult:
    """Chunks are assumed to be in the retriever's order (best first). Source-level hit@k asks
    "did any chunk come from the right doc?"; fact-level asks "did a chunk contain the answer?",
    which is the one that matters once docs are split into several chunks.
    """
    sources = [c.source for c in chunks]
    expected = question.expected_source
    facts = [chunk_has_fact(question, c) for c in chunks] if expected else []
    return QuestionResult(
        id=question.id,
        question=question.question,
        in_scope=question.in_scope,
        slice=question.slice,
        expected_source=expected,
        top_score=max((c.score for c in chunks), default=None),
        hit_at_1=None if expected is None else sources[:1] == [expected],
        hit_at_5=None if expected is None else expected in sources[:5],
        fact_hit_at_1=None if expected is None else any(facts[:1]),
        fact_hit_at_5=None if expected is None else any(facts[:5]),
        chunks=[
            ChunkRecord(
                source=c.source,
                score=c.score,
                approx_tokens=approx_tokens(c.text),
                text_sha1=hashlib.sha1(c.text.encode(), usedforsecurity=False).hexdigest(),
                excerpt=" ".join(c.text.split())[:120],
                has_fact=chunk_has_fact(question, c) if expected else None,
            )
            for c in chunks
        ],
    )


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {
        "n": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def pick_threshold(
    in_scope_top: list[float], out_of_scope_top: list[float], keep: float = IN_SCOPE_KEEP_TARGET
) -> dict[str, Any]:
    """Highest threshold t (taken from the observed in-scope top scores) such that at least
    `keep` of in-scope questions have top score >= t. Raising t only ever refuses more, so
    the highest qualifying t is also the one that refuses the most out-of-scope questions.
    """
    if not in_scope_top:
        raise ValueError("need at least one in-scope score")
    n_in = len(in_scope_top)
    best: float | None = None
    for t in sorted(set(in_scope_top)):
        if sum(s >= t for s in in_scope_top) / n_in >= keep:
            best = t
    if best is None:  # unreachable: the minimum in-scope score always keeps 100%
        raise AssertionError("no threshold kept the target share of in-scope questions")
    kept = sum(s >= best for s in in_scope_top)
    refused = sum(s < best for s in out_of_scope_top)
    return {
        "threshold": best,
        "keep_target": keep,
        "in_scope_kept": kept,
        "in_scope_total": n_in,
        "out_of_scope_refused": refused,
        "out_of_scope_total": len(out_of_scope_top),
        # Out-of-scope top scores this threshold would still let through (class overlap).
        "out_of_scope_at_or_above": sorted(s for s in out_of_scope_top if s >= best),
    }


def chunk_stats(results: list[QuestionResult]) -> dict[str, Any]:
    """Distinct chunks (by text hash) per source, and the largest chunk overall."""
    seen: dict[str, ChunkRecord] = {}
    for r in results:
        for c in r.chunks:
            seen.setdefault(c.text_sha1, c)
    per_source: dict[str, dict[str, int]] = {}
    for c in seen.values():
        entry = per_source.setdefault(c.source, {"distinct_chunks": 0, "max_approx_tokens": 0})
        entry["distinct_chunks"] += 1
        entry["max_approx_tokens"] = max(entry["max_approx_tokens"], c.approx_tokens)
    largest = max(seen.values(), key=lambda c: c.approx_tokens, default=None)
    return {
        "per_source": dict(sorted(per_source.items())),
        "max_chunk_approx_tokens": largest.approx_tokens if largest else None,
        "max_chunk_source": largest.source if largest else None,
        "token_estimate": f"whitespace words x {WORDS_TO_TOKENS} (approximate)",
    }


def summarize(results: list[QuestionResult]) -> dict[str, Any]:
    in_scope = [r for r in results if r.in_scope]
    out_scope = [r for r in results if not r.in_scope]
    in_top = [r.top_score for r in in_scope if r.top_score is not None]
    out_top = [r.top_score for r in out_scope if r.top_score is not None]
    by_slice: dict[str, dict[str, Any]] = {}
    for r in in_scope:
        s = by_slice.setdefault(
            r.slice, {"n": 0, "hit_at_1": 0, "hit_at_5": 0, "fact_hit_at_1": 0, "fact_hit_at_5": 0}
        )
        s["n"] += 1
        for key in ("hit_at_1", "hit_at_5", "fact_hit_at_1", "fact_hit_at_5"):
            s[key] += bool(getattr(r, key))

    def rate(key: str) -> float | None:
        return sum(bool(getattr(r, key)) for r in in_scope) / len(in_scope) if in_scope else None

    return {
        "hit_at_1": rate("hit_at_1"),
        "hit_at_5": rate("hit_at_5"),
        "fact_hit_at_1": rate("fact_hit_at_1"),
        "fact_hit_at_5": rate("fact_hit_at_5"),
        # In-scope questions whose doc was retrieved but no top-5 chunk contains the fact.
        "fact_misses_at_5": [r.id for r in in_scope if r.hit_at_5 and not r.fact_hit_at_5],
        "hits_by_slice": by_slice,
        "top_score_in_scope": distribution(in_top),
        "top_score_out_of_scope": distribution(out_top),
        # Questions with no chunks at all would be refused at any threshold.
        "no_chunks": [r.id for r in results if r.top_score is None],
        "threshold": pick_threshold(in_top, out_top) if in_top else None,
        "chunks": chunk_stats(results),
    }


def _fmt(d: dict[str, Any]) -> str:
    vals = {k: (f"{v:.3f}" if isinstance(v, float) else v) for k, v in d.items()}
    return f"n={vals['n']} min={vals['min']} median={vals['median']} max={vals['max']}"


def print_report(summary: dict[str, Any], out_path: Path) -> None:
    print(
        f"source hit@1 {summary['hit_at_1']:.2%}  hit@5 {summary['hit_at_5']:.2%}   "
        f"fact hit@1 {summary['fact_hit_at_1']:.2%}  hit@5 {summary['fact_hit_at_5']:.2%}"
    )
    for name, s in summary["hits_by_slice"].items():
        print(
            f"  slice {name}: source {s['hit_at_1']}/{s['n']} @1, {s['hit_at_5']}/{s['n']} @5;"
            f" fact {s['fact_hit_at_1']}/{s['n']} @1, {s['fact_hit_at_5']}/{s['n']} @5"
        )
    if summary["fact_misses_at_5"]:
        print(f"  right doc, no fact-bearing chunk in top 5: {summary['fact_misses_at_5']}")
    print(f"top score, in-scope:     {_fmt(summary['top_score_in_scope'])}")
    print(f"top score, out-of-scope: {_fmt(summary['top_score_out_of_scope'])}")
    if summary["no_chunks"]:
        print(f"no chunks returned: {summary['no_chunks']}")
    t = summary["threshold"]
    if t:
        print(
            f"threshold keeping >= {t['keep_target']:.0%} in-scope: {t['threshold']:.4f} "
            f"(keeps {t['in_scope_kept']}/{t['in_scope_total']} in-scope, refuses "
            f"{t['out_of_scope_refused']}/{t['out_of_scope_total']} out-of-scope)"
        )
        if t["out_of_scope_at_or_above"]:
            print(f"  out-of-scope top scores at/above it: {t['out_of_scope_at_or_above']}")
    c = summary["chunks"]
    print(f"chunks per source ({c['token_estimate']}):")
    for source, s in c["per_source"].items():
        print(f"  {source}: {s['distinct_chunks']} distinct, max ~{s['max_approx_tokens']} tokens")
    print(f"largest chunk: ~{c['max_chunk_approx_tokens']} tokens ({c['max_chunk_source']})")
    print(f"wrote {out_path}")


async def retrieve_all(
    questions: list[GoldenQuestion], kb_id: str, region: str, top_k: int
) -> list[QuestionResult]:
    settings = Settings(_env_file=None, aws_region=region)  # type: ignore[call-arg]
    retriever = BedrockKnowledgeBaseRetriever(
        create_bedrock_agent_runtime_client(settings), knowledge_base_id=kb_id, top_k=top_k
    )
    return [score_question(q, await retriever.retrieve(q.question)) for q in questions]


def run(args: argparse.Namespace) -> Path:
    questions = load_golden(args.golden)
    results = asyncio.run(retrieve_all(questions, args.kb_id, args.region, args.top_k))
    summary = summarize(results)

    now = datetime.now(UTC)
    out_path = write_new_results(
        args.results_dir,
        "retrieval",
        now.date(),
        {
            "run_at": now.isoformat(),
            "knowledge_base_id": args.kb_id,
            "region": args.region,
            "top_k": args.top_k,
            "golden_file": args.golden.name,
            "summary": summary,
            "results": [asdict(r) for r in results],
        },
    )
    print_report(summary, out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
