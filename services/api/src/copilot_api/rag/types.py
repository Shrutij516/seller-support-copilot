from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    text: str
    source: str
    score: float


@dataclass(frozen=True, slots=True)
class Generation:
    """One model call's output and its token usage (from Converse's `usage`), returned per
    call so callers can sum it without shared mutable state on the app-wide generator.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class RagBackendError(Exception):
    """A retriever or generator backend failed (throttled, timed out, misconfigured, ...).
    `stage` and `reason` are safe to log; neither is ever shown to the caller.
    """

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage} failed: {reason}")
        self.stage = stage
        self.reason = reason


class Retriever(Protocol):
    async def retrieve(self, query: str) -> list[RetrievedChunk]: ...


class Generator(Protocol):
    async def generate(self, system_prompt: str, user_message: str) -> Generation: ...
