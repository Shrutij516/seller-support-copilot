import pytest

from copilot_api.config import Settings


def test_rag_min_score_default_is_the_calibrated_value(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pinned so a change to the floor is a deliberate, reviewed decision (DECISIONS.md,
    # "Relevance floor is a cost guard, not the refusal mechanism"), not a silent drift.
    monkeypatch.delenv("RAG_MIN_SCORE", raising=False)
    assert Settings(_env_file=None).rag_min_score == 0.55  # type: ignore[call-arg]
