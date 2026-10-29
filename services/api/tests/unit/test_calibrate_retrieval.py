"""Offline tests for evals/calibrate_retrieval.py: the golden set's shape and the metric /
threshold math. No Bedrock calls; the live run is `make eval-retrieval`.
"""

import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from copilot_api.rag.types import RetrievedChunk

REPO_ROOT = Path(__file__).resolve().parents[4]
POLICIES_DIR = REPO_ROOT / "data" / "policies"


def _load_calibration_module() -> ModuleType:
    evals_dir = str(REPO_ROOT / "evals")
    if evals_dir not in sys.path:
        sys.path.insert(0, evals_dir)  # the script imports its sibling `matching` module
    path = REPO_ROOT / "evals" / "calibrate_retrieval.py"
    spec = importlib.util.spec_from_file_location("calibrate_retrieval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


cal = _load_calibration_module()


def _chunk(source: str, score: float, words: int = 30) -> RetrievedChunk:
    return RetrievedChunk(text=" ".join(["w"] * words), source=source, score=score)


def test_golden_set_shape_and_sources_exist() -> None:
    questions = cal.load_golden(cal.DEFAULT_GOLDEN)
    in_scope = [q for q in questions if q.in_scope]
    out_scope = [q for q in questions if not q.in_scope]

    assert len(in_scope) == 20
    assert len(out_scope) == 10
    policy_files = {p.name for p in POLICIES_DIR.glob("*.md")}
    assert {q.expected_source for q in in_scope} == policy_files  # every doc is covered
    assert all(q.expected_fact for q in in_scope)


def test_load_golden_rejects_mismatched_scope(tmp_path: Path) -> None:
    bad = tmp_path / "golden.jsonl"
    bad.write_text(
        '{"id": "x", "in_scope": true, "slice": "direct", "question": "q?", '
        '"expected_source": null, "expected_fact": null}\n'
    )
    with pytest.raises(ValueError, match="in_scope must match"):
        cal.load_golden(bad)


def test_approx_tokens_is_words_times_1_33() -> None:
    assert cal.approx_tokens("one two three") == 4  # round(3 * 1.33)
    assert cal.approx_tokens(" ".join(["w"] * 300)) == 399


def test_score_question_hits_and_top_score() -> None:
    question = cal.GoldenQuestion(
        id="q",
        question="?",
        in_scope=True,
        slice="direct",
        expected_source="fees.md",
        expected_fact="8%",
    )
    chunks = [_chunk("returns.md", 0.7), _chunk("fees.md", 0.6)]

    result = cal.score_question(question, chunks)

    assert result.top_score == 0.7
    assert result.hit_at_1 is False
    assert result.hit_at_5 is True
    assert [c.source for c in result.chunks] == ["returns.md", "fees.md"]


def test_out_of_scope_question_has_no_hit_values() -> None:
    question = cal.GoldenQuestion(
        id="o",
        question="?",
        in_scope=False,
        slice="nonsense",
        expected_source=None,
        expected_fact=None,
    )
    result = cal.score_question(question, [_chunk("fees.md", 0.5)])

    assert (result.hit_at_1, result.hit_at_5, result.top_score) == (None, None, 0.5)


def test_pick_threshold_keeps_95_percent_and_refuses_most_out_of_scope() -> None:
    in_top = [0.60 + i * 0.01 for i in range(20)]  # 0.60 .. 0.79
    out_top = [0.40, 0.50, 0.52, 0.61, 0.65]

    picked = cal.pick_threshold(in_top, out_top)

    # 19/20 = 95% kept means dropping only the lowest in-scope score (0.60).
    assert picked["threshold"] == pytest.approx(0.61)
    assert (picked["in_scope_kept"], picked["in_scope_total"]) == (19, 20)
    assert picked["out_of_scope_refused"] == 3
    assert picked["out_of_scope_at_or_above"] == pytest.approx([0.61, 0.65])


def test_pick_threshold_with_one_question_keeps_it() -> None:
    assert cal.pick_threshold([0.5], [0.9])["threshold"] == 0.5


def test_chunk_stats_dedupes_by_text_and_tracks_max_size() -> None:
    question = cal.GoldenQuestion(
        id="q",
        question="?",
        in_scope=True,
        slice="direct",
        expected_source="ship.md",
        expected_fact="x",
    )
    big = _chunk("ship.md", 0.6, words=525)
    small = _chunk("fees.md", 0.5, words=200)
    results = [cal.score_question(question, [big, small]), cal.score_question(question, [big])]

    stats = cal.chunk_stats(results)

    assert stats["per_source"] == {
        "fees.md": {"distinct_chunks": 1, "max_approx_tokens": 266},
        "ship.md": {"distinct_chunks": 1, "max_approx_tokens": 698},
    }
    assert (stats["max_chunk_approx_tokens"], stats["max_chunk_source"]) == (698, "ship.md")


def test_summarize_reports_hits_distributions_and_threshold() -> None:
    def q(id_: str, in_scope: bool, source: str | None) -> object:
        return cal.GoldenQuestion(
            id=id_,
            question="?",
            in_scope=in_scope,
            slice="direct" if in_scope else "nonsense",
            expected_source=source,
            expected_fact="f" if in_scope else None,
        )

    results = [
        cal.score_question(q("a", True, "fees.md"), [_chunk("fees.md", 0.7)]),
        cal.score_question(
            q("b", True, "ship.md"), [_chunk("fees.md", 0.6), _chunk("ship.md", 0.5)]
        ),
        cal.score_question(q("c", False, None), [_chunk("fees.md", 0.5)]),
        cal.score_question(q("d", False, None), []),
    ]

    summary = cal.summarize(results)

    assert summary["hit_at_1"] == 0.5
    assert summary["hit_at_5"] == 1.0
    assert summary["top_score_in_scope"] == pytest.approx(
        {"n": 2, "min": 0.6, "median": 0.65, "max": 0.7}
    )
    assert summary["top_score_out_of_scope"]["n"] == 1
    assert summary["no_chunks"] == ["d"]
    assert summary["threshold"]["threshold"] == 0.6


def test_run_writes_results_file_without_calling_bedrock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_retrieve_all(questions: list[Any], *_: object) -> list[Any]:
        return [
            cal.score_question(
                q, [_chunk(q.expected_source or "fees.md", 0.7 if q.in_scope else 0.4)]
            )
            for q in questions
        ]

    monkeypatch.setattr(cal, "retrieve_all", fake_retrieve_all)
    args = argparse.Namespace(
        golden=cal.DEFAULT_GOLDEN,
        kb_id="KBTEST",
        region="us-east-1",
        top_k=5,
        results_dir=tmp_path,
    )

    out_path = cal.run(args)

    written = json.loads(out_path.read_text())
    assert out_path.parent == tmp_path and out_path.name.startswith("retrieval-")
    assert written["summary"]["hit_at_1"] == 1.0
    assert written["summary"]["threshold"]["out_of_scope_refused"] == 10
    assert len(written["results"]) == 30
    assert "source hit@1 100.00%" in capsys.readouterr().out


def test_write_new_results_never_overwrites(tmp_path: Path) -> None:
    day = date(2026, 10, 29)
    baseline = tmp_path / "answers-2026-10-29.json"
    baseline.write_text('{"baseline": true}\n')

    second = cal.write_new_results(tmp_path, "answers", day, {"run": 2})
    third = cal.write_new_results(tmp_path, "answers", day, {"run": 3})
    other_prefix = cal.write_new_results(tmp_path, "retrieval", day, {"run": 1})

    assert baseline.read_text() == '{"baseline": true}\n'
    assert second.name == "answers-2026-10-29-02.json"
    assert third.name == "answers-2026-10-29-03.json"
    assert json.loads(third.read_text()) == {"run": 3}
    assert other_prefix.name == "retrieval-2026-10-29.json"


def test_run_twice_same_day_keeps_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_retrieve_all(questions: list[Any], *_: object) -> list[Any]:
        return [cal.score_question(q, [_chunk("fees.md", 0.7)]) for q in questions]

    monkeypatch.setattr(cal, "retrieve_all", fake_retrieve_all)
    args = argparse.Namespace(
        golden=cal.DEFAULT_GOLDEN,
        kb_id="KBTEST",
        region="us-east-1",
        top_k=5,
        results_dir=tmp_path,
    )

    first, second = cal.run(args), cal.run(args)

    assert first != second
    assert first.exists() and second.exists()
    assert second.name.endswith("-02.json")


def _fees_question() -> Any:
    return cal.GoldenQuestion(
        id="in-09",
        question="When an order gets refunded, do I get my commission back?",
        in_scope=True,
        slice="paraphrase",
        expected_source="fees.md",
        expected_fact="The referral fee is returned",
        key_terms=["referral fee", "returns|returned"],
    )


def _text_chunk(source: str, text: str, score: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk(text=text, source=source, score=score)


def test_fact_hit_requires_a_chunk_containing_every_key_term() -> None:
    # The in-09 failure shape: the right doc is retrieved, but the chunk starts after the fact.
    split = _text_chunk(
        "fees.md", "The per-item fee (Standard plan) is not refunded, as it covers..."
    )
    whole = _text_chunk(
        "fees.md", "Kestrel Market returns the referral fee for that item to the seller."
    )

    missed = cal.score_question(_fees_question(), [split])
    found_second = cal.score_question(_fees_question(), [split, whole])

    assert (missed.hit_at_5, missed.fact_hit_at_5) == (True, False)
    assert (found_second.fact_hit_at_1, found_second.fact_hit_at_5) == (False, True)
    assert [c.has_fact for c in found_second.chunks] == [False, True]
    assert found_second.chunks[0].excerpt.startswith("The per-item fee (Standard plan)")


def test_fact_hit_requires_the_expected_source() -> None:
    wrong_doc = _text_chunk("disputes.md", "We returns the referral fee... (wrong document)")

    result = cal.score_question(_fees_question(), [wrong_doc])

    assert (result.hit_at_5, result.fact_hit_at_5) == (False, False)


def test_out_of_scope_has_no_fact_values() -> None:
    q = cal.GoldenQuestion(
        id="o",
        question="?",
        in_scope=False,
        slice="nonsense",
        expected_source=None,
        expected_fact=None,
    )
    result = cal.score_question(q, [_text_chunk("fees.md", "referral fee returns")])

    assert (result.fact_hit_at_1, result.fact_hit_at_5) == (None, None)
    assert result.chunks[0].has_fact is None


def test_summary_separates_source_hits_from_fact_hits() -> None:
    q = _fees_question()
    split = _text_chunk("fees.md", "The per-item fee (Standard plan) is not refunded.")
    whole = _text_chunk("fees.md", "Kestrel Market returns the referral fee.")

    summary = cal.summarize([cal.score_question(q, [split]), cal.score_question(q, [whole])])

    assert (summary["hit_at_5"], summary["fact_hit_at_5"]) == (1.0, 0.5)
    assert summary["fact_misses_at_5"] == ["in-09"]
    assert summary["hits_by_slice"]["paraphrase"]["fact_hit_at_5"] == 1
