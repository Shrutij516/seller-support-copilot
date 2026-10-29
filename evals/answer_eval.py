"""End-to-end answer eval: every golden question through the production RAG path.

Uses copilot_api.rag.pipeline.answer_question, the function the chat route calls: retrieve
(top_k from settings) -> filter at rag_min_score -> refusal without a model call if nothing
clears it -> numbered prompt -> Converse -> keep only citations the answer marks with [n].
Calls real Bedrock with your own AWS session (costs a little); run by hand via
`make eval-answers`.

Scoring is deterministic (no LLM judge):

- In-scope passes when (a) every `key_terms` entry from the golden set appears in the answer
  and (b) at least one returned citation is from `expected_source`. Matching ignores case,
  whitespace, curly-vs-straight quotes and dash style; citation markers like [2] are removed
  first so they can't satisfy a number. A purely numeric term (e.g. "30", "2.40") matches
  only as a whole number: "30" matches "30 days" and "30-day", not "300" or "3.0". A term
  "a|b" passes if either alternative matches.
- Out-of-scope passes when the answer has zero citations AND matches REFUSAL_PATTERN below
  (the pipeline's own refusal text matches it too).

Prints pass rates per slice, every failure (question, first 200 chars of the answer,
citations, reasons), total Converse input/output tokens, and an ESTIMATED cost; writes
evals/results/answers-<date>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from calibrate_retrieval import (
    DEFAULT_GOLDEN,
    DEFAULT_RESULTS_DIR,
    GoldenQuestion,
    load_golden,
    write_new_results,
)

from copilot_api.config import Settings
from copilot_api.rag.bedrock import (
    BedrockConverseGenerator,
    BedrockKnowledgeBaseRetriever,
    create_bedrock_agent_runtime_client,
    create_bedrock_runtime_client,
)
from copilot_api.rag.pipeline import RagAnswer, answer_question
from copilot_api.rag.prompt import CITATION_MARKER
from copilot_api.rag.types import RagBackendError

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Answers that decline instead of answering. Matched case-insensitively on the normalized
# answer. Covers the system prompt's instructed wording ("I don't know based on the
# marketplace policies"), common paraphrases, and the pipeline's own REFUSAL_MESSAGE
# ("I couldn't find that in the marketplace policies ...").
REFUSAL_PATTERN = re.compile(
    r"\b("
    r"i (?:don't|do not) know"
    r"|(?:couldn't|could not|can't|cannot|can not) find"
    r"|(?:can't|cannot|can not|am unable to|i'm unable to) answer"
    r"|(?:don't|do not) (?:have|contain|include|cover) (?:any )?(?:information|details)"
    r"|(?:no|not enough) information"
    r"|(?:isn't|is not|aren't|are not|not) (?:covered|mentioned|addressed|included|described)"
    r"|(?:doesn't|does not|don't|do not) (?:cover|mention|address|include|describe)"
    r")\b",
    re.IGNORECASE,
)

# ESTIMATE ONLY. Amazon Bedrock on-demand pricing for "Claude 4.5 Haiku", Geo and In-region
# Cross-region Inference table (the pricing that applies to the `us.` inference profile),
# region US East (N. Virginia), as shown on https://aws.amazon.com/bedrock/pricing/ on
# 2026-10-29: $1.10 per 1M input tokens, $5.50 per 1M output tokens. Excludes Retrieve
# (query embedding, S3 Vectors queries); prices change, so re-check before quoting.
PRICE_PER_M_INPUT_USD = 1.10
PRICE_PER_M_OUTPUT_USD = 5.50
PRICING_SOURCE = (
    "https://aws.amazon.com/bedrock/pricing/ (Anthropic, On-Demand, Geo and In-region "
    "Cross-region Inference, US East (N. Virginia), Claude 4.5 Haiku; viewed 2026-10-29)"
)

_NUMBER_TERM = re.compile(r"\d+(?:\.\d+)?")


# Curly quotes and en/em dashes -> ASCII, so a curly "can't" matches "can't" (code points, not
# literals, to keep them visible in review).
_ASCII_PUNCTUATION = str.maketrans(
    {
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x201C): '"',
        chr(0x201D): '"',
        chr(0x2013): "-",
        chr(0x2014): "-",
    }
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ASCII_PUNCTUATION)).strip().lower()


def strip_citation_markers(text: str) -> str:
    return CITATION_MARKER.sub(" ", text)


def term_matches(term: str, answer: str) -> bool:
    """`answer` should already be normalized and marker-free."""
    for alternative in (normalize(a) for a in term.split("|")):
        if _NUMBER_TERM.fullmatch(alternative):
            digits = answer.replace(",", "")
            if re.search(rf"(?<![\d.]){re.escape(alternative)}(?![\d]|\.\d)", digits):
                return True
        elif alternative and alternative in answer:
            return True
    return False


def missing_terms(key_terms: list[str], answer_text: str) -> list[str]:
    answer = normalize(strip_citation_markers(answer_text))
    return [t for t in key_terms if not term_matches(t, answer)]


def is_refusal(answer_text: str) -> bool:
    return bool(REFUSAL_PATTERN.search(normalize(answer_text)))


@dataclass
class AnswerResult:
    id: str
    slice: str
    in_scope: bool
    question: str
    expected_source: str | None
    answer: str
    refused_without_model: bool
    citations: list[dict[str, Any]]
    kept_sources: list[str]
    passed: bool
    reasons: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)


def score(question: GoldenQuestion, answer: RagAnswer) -> tuple[bool, list[str]]:
    sources = [c.source for c in answer.citations]
    reasons: list[str] = []
    if question.in_scope:
        missing = missing_terms(question.key_terms or [], answer.text)
        if missing:
            reasons.append(f"key terms not found: {missing}")
        if question.expected_source not in sources:
            reasons.append(f"no citation from {question.expected_source} (cited: {sources})")
    else:
        if sources:
            reasons.append(f"out-of-scope answer has citations: {sources}")
        if not is_refusal(answer.text):
            reasons.append("answer doesn't match the refusal pattern")
    return not reasons, reasons


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRICE_PER_M_INPUT_USD
        + output_tokens / 1_000_000 * PRICE_PER_M_OUTPUT_USD
    )


def summarize(results: list[AnswerResult]) -> dict[str, Any]:
    by_slice: dict[str, dict[str, int]] = {}
    for r in results:
        key = f"{'in' if r.in_scope else 'out'}:{r.slice}"
        s = by_slice.setdefault(key, {"passed": 0, "total": 0})
        s["total"] += 1
        s["passed"] += r.passed
    in_scope = [r for r in results if r.in_scope]
    out_scope = [r for r in results if not r.in_scope]
    input_tokens = sum(r.input_tokens for r in results)
    output_tokens = sum(r.output_tokens for r in results)
    return {
        "in_scope": {"passed": sum(r.passed for r in in_scope), "total": len(in_scope)},
        "out_of_scope": {"passed": sum(r.passed for r in out_scope), "total": len(out_scope)},
        "by_slice": dict(sorted(by_slice.items())),
        "failures": [r.id for r in results if not r.passed],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(estimate_cost_usd(input_tokens, output_tokens), 6),
        "pricing_source": PRICING_SOURCE,
    }


def print_report(results: list[AnswerResult], summary: dict[str, Any], out_path: Path) -> None:
    for label, key in (("in-scope pass:    ", "in_scope"), ("out-of-scope pass:", "out_of_scope")):
        print(f"{label} {summary[key]['passed']}/{summary[key]['total']}")
    for name, s in summary["by_slice"].items():
        print(f"  {name}: {s['passed']}/{s['total']}")
    failures = [r for r in results if not r.passed]
    print(f"\nfailures ({len(failures)}):")
    for r in failures:
        cited = [f"[{c['index']}] {c['source']}" for c in r.citations]
        print(f"- {r.id} ({r.slice}): {r.question}")
        print(f"    answer: {r.answer[:200]!r}")
        print(f"    citations: {cited}")
        for reason in r.reasons:
            print(f"    reason: {reason}")
    print(
        f"\nConverse tokens: input {summary['input_tokens']}, output {summary['output_tokens']}"
        f"; estimated cost ${summary['estimated_cost_usd']:.4f} (ESTIMATE; {PRICING_SOURCE})"
    )
    print(f"wrote {out_path}")


async def evaluate(
    questions: list[GoldenQuestion],
    kb_id: str,
    region: str,
    model_id: str,
    min_score: float,
    top_k: int,
    max_tokens: int,
) -> list[AnswerResult]:
    settings = Settings(_env_file=None, aws_region=region)  # type: ignore[call-arg]
    retriever = BedrockKnowledgeBaseRetriever(
        create_bedrock_agent_runtime_client(settings), knowledge_base_id=kb_id, top_k=top_k
    )
    generator = BedrockConverseGenerator(
        create_bedrock_runtime_client(settings), model_id=model_id, max_tokens=max_tokens
    )
    results: list[AnswerResult] = []
    for q in questions:
        try:
            answer = await answer_question(q.question, retriever, generator, min_score)
        except RagBackendError as exc:
            results.append(
                AnswerResult(
                    id=q.id,
                    slice=q.slice,
                    in_scope=q.in_scope,
                    question=q.question,
                    expected_source=q.expected_source,
                    answer="",
                    refused_without_model=False,
                    citations=[],
                    kept_sources=[],
                    passed=False,
                    reasons=[f"backend error at {exc.stage}: {exc.reason}"],
                )
            )
            continue
        passed, reasons = score(q, answer)
        results.append(
            AnswerResult(
                id=q.id,
                slice=q.slice,
                in_scope=q.in_scope,
                question=q.question,
                expected_source=q.expected_source,
                answer=answer.text,
                refused_without_model=answer.refused,
                citations=[{"index": c.index, "source": c.source} for c in answer.citations],
                kept_sources=[c.source for c in answer.kept],
                passed=passed,
                reasons=reasons,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                timings_ms=answer.timings_ms,
            )
        )
    return results


def run(args: argparse.Namespace) -> Path:
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    min_score = defaults.rag_min_score if args.min_score is None else args.min_score
    results = asyncio.run(
        evaluate(
            load_golden(args.golden),
            args.kb_id,
            args.region,
            args.model_id,
            min_score,
            defaults.rag_top_k,
            defaults.rag_max_tokens,
        )
    )
    summary = summarize(results)
    now = datetime.now(UTC)
    out_path = write_new_results(
        args.results_dir,
        "answers",
        now.date(),
        {
            "run_at": now.isoformat(),
            "knowledge_base_id": args.kb_id,
            "region": args.region,
            "model_id": args.model_id,
            "rag_min_score": min_score,
            "top_k": defaults.rag_top_k,
            "max_tokens": defaults.rag_max_tokens,
            "golden_file": args.golden.name,
            "refusal_pattern": REFUSAL_PATTERN.pattern,
            "summary": summary,
            "results": [asdict(r) for r in results],
        },
    )
    print_report(results, summary, out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument(
        "--min-score", type=float, default=None, help="defaults to the app's rag_min_score"
    )
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
