"""Offline tests for evals/answer_eval.py scoring. No Bedrock calls; the live run is
`make eval-answers`.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from copilot_api.dynamo.chat_repository import Citation
from copilot_api.rag.pipeline import RagAnswer
from copilot_api.rag.prompt import REFUSAL_MESSAGE

EVALS_DIR = Path(__file__).resolve().parents[4] / "evals"
RSQUO = chr(0x2019)  # curly apostrophe, as models often emit


def _load(name: str) -> ModuleType:
    if str(EVALS_DIR) not in sys.path:
        sys.path.insert(0, str(EVALS_DIR))  # answer_eval imports its sibling module
    spec = importlib.util.spec_from_file_location(name, EVALS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ev = _load("answer_eval")


def _question(in_scope: bool, key_terms: list[str] | None = None) -> Any:
    return ev.GoldenQuestion(
        id="q",
        question="?",
        in_scope=in_scope,
        slice="direct" if in_scope else "nonsense",
        expected_source="returns-and-refunds.md" if in_scope else None,
        expected_fact="f" if in_scope else None,
        key_terms=key_terms,
    )


def _answer(text: str, sources: list[str], refused: bool = False) -> RagAnswer:
    citations = tuple(Citation(index=i, source=s, snippet="x") for i, s in enumerate(sources, 1))
    return RagAnswer(text, citations, refused, [], [])


@pytest.mark.parametrize(
    ("term", "answer", "expected"),
    [
        ("30", "you have 30 days from delivery", True),
        ("30", "a 30-day window", True),
        ("30", "within 300 days", False),
        ("3", "it is 3.0 here", False),
        ("2.40", "$2.40 per cubic foot", True),
        ("2.40", "$2.4 per cubic foot", False),
        ("5", "more than 5% of orders", True),
        ("5", "a 1.5 day buffer", False),
        ("34.99", "the pro plan costs $34.99 a month", True),
        ("2-3|2 to 3", "two options: 2 to 3 business days", True),
        ("business day", "within 3 business days", True),
        ("can't", f"you can{RSQUO}t charge return shipping", True),
    ],
)
def test_term_matches(term: str, answer: str, expected: bool) -> None:
    assert ev.term_matches(term, ev.normalize(answer)) is expected


def test_citation_markers_cannot_satisfy_a_number() -> None:
    assert ev.missing_terms(["1%|1 %"], "Keep defects low [1].") == ["1%|1 %"]
    assert ev.missing_terms(["3"], "See the policy [3].") == ["3"]


def test_refusal_pattern_matches_instructed_and_pipeline_refusals() -> None:
    assert ev.is_refusal("I don't know based on the marketplace policies.")
    assert ev.is_refusal("I do not know; the policies don't cover that.")
    assert ev.is_refusal(REFUSAL_MESSAGE)
    assert ev.is_refusal(f"The marketplace policies don{RSQUO}t mention two-factor authentication.")
    assert not ev.is_refusal("Paris is the capital of France.")
    assert not ev.is_refusal("You have 30 days from delivery to request a refund [2].")


def test_in_scope_pass_needs_terms_and_expected_source() -> None:
    q = _question(True, ["30", "deliver"])

    assert ev.score(q, _answer("30 days from delivery [1].", ["returns-and-refunds.md"])) == (
        True,
        [],
    )

    wrong_source = ev.score(q, _answer("30 days from delivery [1].", ["fees.md"]))
    assert wrong_source[0] is False
    assert "no citation from returns-and-refunds.md" in wrong_source[1][0]

    missing = ev.score(q, _answer("A month after purchase [1].", ["returns-and-refunds.md"]))
    assert missing == (False, ["key terms not found: ['30', 'deliver']"])


def test_out_of_scope_pass_needs_refusal_and_no_citations() -> None:
    q = _question(False)

    assert ev.score(q, _answer("I don't know based on the marketplace policies.", [])) == (
        True,
        [],
    )
    assert ev.score(q, _answer(REFUSAL_MESSAGE, [], refused=True))[0] is True

    cited = ev.score(q, _answer("I don't know [1].", ["fees.md"]))
    assert cited == (False, ["out-of-scope answer has citations: ['fees.md']"])

    answered = ev.score(q, _answer("Paris.", []))
    assert answered == (False, ["answer doesn't match the refusal pattern"])


def test_cost_estimate_uses_documented_haiku_45_geo_prices() -> None:
    assert ev.estimate_cost_usd(1_000_000, 0) == pytest.approx(1.10)
    assert ev.estimate_cost_usd(0, 1_000_000) == pytest.approx(5.50)
    assert ev.estimate_cost_usd(20_000, 2_000) == pytest.approx(0.022 + 0.011)
    assert "aws.amazon.com/bedrock/pricing" in ev.PRICING_SOURCE


def test_summarize_counts_slices_tokens_and_failures() -> None:
    def result(id_: str, in_scope: bool, slice_: str, passed: bool) -> Any:
        return ev.AnswerResult(
            id=id_,
            slice=slice_,
            in_scope=in_scope,
            question="?",
            expected_source=None,
            answer="",
            refused_without_model=False,
            citations=[],
            kept_sources=[],
            passed=passed,
            input_tokens=1000,
            output_tokens=100,
        )

    summary = ev.summarize(
        [
            result("a", True, "direct", True),
            result("b", True, "paraphrase", False),
            result("c", False, "nonsense", True),
        ]
    )

    assert summary["in_scope"] == {"passed": 1, "total": 2}
    assert summary["out_of_scope"] == {"passed": 1, "total": 1}
    assert summary["by_slice"]["in:paraphrase"] == {"passed": 0, "total": 1}
    assert summary["failures"] == ["b"]
    assert (summary["input_tokens"], summary["output_tokens"]) == (3000, 300)


def test_golden_in_scope_questions_all_have_key_terms() -> None:
    questions = ev.load_golden(ev.DEFAULT_GOLDEN)
    assert all(q.key_terms for q in questions if q.in_scope)
    assert all(q.key_terms is None for q in questions if not q.in_scope)
