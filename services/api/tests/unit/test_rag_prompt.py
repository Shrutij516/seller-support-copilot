from copilot_api.rag.prompt import (
    CITATION_SNIPPET_MAX_CHARS,
    SYSTEM_PROMPT,
    build_user_message,
    filter_by_min_score,
    filter_cited,
    make_citations,
)
from copilot_api.rag.types import RetrievedChunk

REFUNDS_TEXT = "Refunds are issued within 5 business days."
SHIPPING_TEXT = "Late shipments count against account health."
CHUNKS = [
    RetrievedChunk(text=REFUNDS_TEXT, source="refunds.md", score=0.9),
    RetrievedChunk(text=SHIPPING_TEXT, source="ship.md", score=0.6),
]


def test_system_prompt_restricts_answers_to_context() -> None:
    assert "ONLY from the numbered context" in SYSTEM_PROMPT
    assert "say you don't know" in SYSTEM_PROMPT
    assert "[1]" in SYSTEM_PROMPT  # tells the model the citation format


def test_user_message_numbers_context_from_one_in_order() -> None:
    message = build_user_message("How fast are refunds?", CHUNKS)

    first = message.index(f"[1] (source: refunds.md)\n{REFUNDS_TEXT}")
    second = message.index(f"[2] (source: ship.md)\n{SHIPPING_TEXT}")
    question = message.index("Question: How fast are refunds?")
    assert first < second < question
    assert "[3]" not in message


def test_filter_by_min_score_keeps_only_chunks_at_or_above_threshold() -> None:
    assert filter_by_min_score(CHUNKS, 0.6) == CHUNKS
    assert filter_by_min_score(CHUNKS, 0.61) == [CHUNKS[0]]
    assert filter_by_min_score(CHUNKS, 0.95) == []


def test_citations_match_context_numbers_and_truncate_snippets() -> None:
    long_chunk = RetrievedChunk(text="x" * 1000, source="fees.md", score=0.8)

    citations = make_citations([CHUNKS[0], long_chunk])

    assert [(c.index, c.source) for c in citations] == [(1, "refunds.md"), (2, "fees.md")]
    assert citations[0].snippet == CHUNKS[0].text
    assert len(citations[1].snippet) == CITATION_SNIPPET_MAX_CHARS == 300


THREE = make_citations(
    [
        RetrievedChunk(text="a", source="a.md", score=0.9),
        RetrievedChunk(text="b", source="b.md", score=0.8),
        RetrievedChunk(text="c", source="c.md", score=0.7),
    ]
)


def test_filter_cited_keeps_only_cited_with_original_numbers() -> None:
    cited = filter_cited("Refunds take 30 days [3]. Fees are separate [1].", THREE)
    assert [(c.index, c.source) for c in cited] == [(1, "a.md"), (3, "c.md")]


def test_filter_cited_handles_adjacent_and_comma_markers() -> None:
    assert [c.index for c in filter_cited("Both apply [2][3].", THREE)] == [2, 3]
    assert [c.index for c in filter_cited("Both apply [1, 3].", THREE)] == [1, 3]


def test_filter_cited_no_markers_means_no_citations() -> None:
    assert filter_cited("I don't know based on the marketplace policies.", THREE) == ()


def test_filter_cited_ignores_out_of_range_numbers() -> None:
    assert [c.index for c in filter_cited("See [0], [4] and [99], also [2].", THREE)] == [2]


def test_filter_cited_dedupes_repeated_markers() -> None:
    assert [c.index for c in filter_cited("[2] says so. Again, [2]. And [2][2].", THREE)] == [2]
