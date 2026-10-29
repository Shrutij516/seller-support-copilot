from dataclasses import dataclass, field

from copilot_api.rag.pipeline import answer_question
from copilot_api.rag.prompt import REFUSAL_MESSAGE, SYSTEM_PROMPT
from copilot_api.rag.types import RetrievedChunk

CHUNKS = [
    RetrievedChunk(text="Fees are charged at sale.", source="fees.md", score=0.9),
    RetrievedChunk(text="Refunds within 30 days of delivery.", source="returns.md", score=0.8),
    RetrievedChunk(text="Late shipments hurt health.", source="ship.md", score=0.7),
    RetrievedChunk(text="Barely related.", source="disputes.md", score=0.2),
]


@dataclass
class FakeRetriever:
    chunks: list[RetrievedChunk]

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        return self.chunks


@dataclass
class FakeGenerator:
    answer: str
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def generate(self, system_prompt: str, user_message: str) -> str:
        self.calls.append((system_prompt, user_message))
        return self.answer


async def test_returns_only_cited_sources_with_prompt_numbering() -> None:
    generator = FakeGenerator("You have 30 days from delivery [2].")

    answer = await answer_question("refund window?", FakeRetriever(CHUNKS), generator, 0.5)

    assert answer.refused is False
    assert [(c.index, c.source) for c in answer.citations] == [(2, "returns.md")]
    assert [c.source for c in answer.kept] == ["fees.md", "returns.md", "ship.md"]
    system_prompt, user_message = generator.calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert "[2] (source: returns.md)" in user_message
    assert "Barely related." not in user_message
    assert set(answer.timings_ms) == {"retrieve", "generate"}


async def test_model_refusal_without_markers_has_no_citations() -> None:
    generator = FakeGenerator("I don't know based on the marketplace policies.")

    answer = await answer_question("capital of France?", FakeRetriever(CHUNKS), generator, 0.5)

    assert answer.refused is False  # the model answered; it just declined
    assert answer.citations == ()


async def test_nothing_above_floor_refuses_without_calling_model() -> None:
    generator = FakeGenerator("should not be used [1]")

    answer = await answer_question("anything", FakeRetriever(CHUNKS), generator, 0.95)

    assert (answer.refused, answer.text, answer.citations) == (True, REFUSAL_MESSAGE, ())
    assert generator.calls == []
    assert set(answer.timings_ms) == {"retrieve"}
