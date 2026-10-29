"""Bedrock adapters for the Retriever/Generator interfaces. The only RAG code that talks to
AWS. boto3 is synchronous, so every call runs in a worker thread; clients are created once at
startup (see main.py) and shared, which boto3 clients support across threads.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from copilot_api.config import Settings
from copilot_api.rag.types import Generation, RagBackendError, RetrievedChunk

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agent_runtime import AgentsforBedrockRuntimeClient
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

# Bounded so a hung Bedrock call becomes a 503 instead of holding a request (and a worker
# thread) open indefinitely. Generation gets the longer read timeout.
_RETRIEVE_CONFIG = Config(
    connect_timeout=5, read_timeout=15, retries={"max_attempts": 2, "mode": "standard"}
)
_CONVERSE_CONFIG = Config(
    connect_timeout=5, read_timeout=60, retries={"max_attempts": 2, "mode": "standard"}
)

# Grounded Q&A over policy text: we want the most likely reading, not variety.
_TEMPERATURE = 0.0


def create_bedrock_agent_runtime_client(settings: Settings) -> AgentsforBedrockRuntimeClient:
    return boto3.client(
        "bedrock-agent-runtime", region_name=settings.aws_region, config=_RETRIEVE_CONFIG
    )


def create_bedrock_runtime_client(settings: Settings) -> BedrockRuntimeClient:
    return boto3.client("bedrock-runtime", region_name=settings.aws_region, config=_CONVERSE_CONFIG)


def _reason(exc: ClientError | BotoCoreError) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", "ClientError"))
    return type(exc).__name__


def _source_name(result: Any) -> str:
    """Human-readable document name for a citation: the S3 object's file name when the KB is
    S3-backed (ours is), else whatever the result carries, else a placeholder.
    """
    uri: str | None = result.get("location", {}).get("s3Location", {}).get("uri")
    if uri:
        return urlsplit(uri).path.rsplit("/", 1)[-1] or uri
    return str(result.get("metadata", {}).get("x-amz-bedrock-kb-source-uri", "unknown source"))


class BedrockKnowledgeBaseRetriever:
    def __init__(
        self, client: AgentsforBedrockRuntimeClient, knowledge_base_id: str, top_k: int
    ) -> None:
        self._client = client
        self._knowledge_base_id = knowledge_base_id
        self._top_k = top_k

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        def _call() -> Any:
            return self._client.retrieve(
                knowledgeBaseId=self._knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {"numberOfResults": self._top_k}
                },
            )

        try:
            response = await asyncio.to_thread(_call)
        except (ClientError, BotoCoreError) as exc:
            raise RagBackendError("retrieve", _reason(exc)) from exc

        return [
            RetrievedChunk(
                text=result["content"]["text"],
                source=_source_name(result),
                score=float(result.get("score", 0.0)),
            )
            for result in response.get("retrievalResults", [])
            if result.get("content", {}).get("text")
        ]


class BedrockConverseGenerator:
    def __init__(self, client: BedrockRuntimeClient, model_id: str, max_tokens: int) -> None:
        self._client = client
        self._model_id = model_id
        self._max_tokens = max_tokens

    async def generate(self, system_prompt: str, user_message: str) -> Generation:
        def _call() -> Any:
            return self._client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_message}]}],
                inferenceConfig={"maxTokens": self._max_tokens, "temperature": _TEMPERATURE},
            )

        try:
            response = await asyncio.to_thread(_call)
        except (ClientError, BotoCoreError) as exc:
            raise RagBackendError("converse", _reason(exc)) from exc

        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block["text"] for block in blocks if "text" in block).strip()
        if not text:
            raise RagBackendError("converse", "empty response")
        usage = response.get("usage", {})
        return Generation(
            text=text,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
        )
