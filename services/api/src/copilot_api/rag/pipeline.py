"""The one RAG answer path: used by the chat route, scripts/rag_smoke.py, and
evals/answer_eval.py, so what's evaluated is exactly what's served.
"""

import time
from dataclasses import dataclass, field

from copilot_api.dynamo.chat_repository import Citation
from copilot_api.rag.prompt import (
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_message,
    filter_by_min_score,
    filter_cited,
    make_citations,
)
from copilot_api.rag.types import Generator, RetrievedChunk, Retriever


@dataclass(frozen=True)
class RagAnswer:
    text: str
    # Only the chunks the answer cites by [n], numbered as they were in the prompt.
    citations: tuple[Citation, ...]
    # True when nothing cleared the relevance floor and the model was never called.
    refused: bool
    retrieved: list[RetrievedChunk]
    kept: list[RetrievedChunk]
    timings_ms: dict[str, float] = field(default_factory=dict)
    # This call's Converse usage (0 when refused without a model call).
    input_tokens: int = 0
    output_tokens: int = 0


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


async def answer_question(
    question: str, retriever: Retriever, generator: Generator, min_score: float
) -> RagAnswer:
    """Retrieve, keep chunks at or above `min_score`, refuse without a model call if none
    are left, otherwise answer from the numbered context and keep only cited sources.
    RagBackendError from either backend propagates to the caller.
    """
    timings: dict[str, float] = {}
    start = time.perf_counter()
    retrieved = await retriever.retrieve(question)
    timings["retrieve"] = _elapsed_ms(start)

    kept = filter_by_min_score(retrieved, min_score)
    if not kept:
        return RagAnswer(REFUSAL_MESSAGE, (), True, retrieved, kept, timings)

    start = time.perf_counter()
    generation = await generator.generate(SYSTEM_PROMPT, build_user_message(question, kept))
    timings["generate"] = _elapsed_ms(start)

    return RagAnswer(
        text=generation.text,
        citations=filter_cited(generation.text, make_citations(kept)),
        refused=False,
        retrieved=retrieved,
        kept=kept,
        timings_ms=timings,
        input_tokens=generation.input_tokens,
        output_tokens=generation.output_tokens,
    )
