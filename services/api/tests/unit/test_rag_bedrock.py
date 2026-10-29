"""Bedrock adapters against botocore's Stubber: real clients (so request parameters are
validated against the actual service models) that never touch the network.
"""

from typing import Any

import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from copilot_api.config import Settings
from copilot_api.rag.bedrock import (
    BedrockConverseGenerator,
    BedrockKnowledgeBaseRetriever,
    create_bedrock_agent_runtime_client,
    create_bedrock_runtime_client,
)
from copilot_api.rag.types import RagBackendError

KB_ID = "KBTEST1234"
MODEL_ID = "test-model-id"


class _TimingOutClient:
    def retrieve(self, **_: Any) -> Any:
        raise ReadTimeoutError(endpoint_url="https://bedrock.invalid")

    def converse(self, **_: Any) -> Any:
        raise ReadTimeoutError(endpoint_url="https://bedrock.invalid")


async def test_retriever_sends_kb_id_and_top_k_and_parses_results() -> None:
    client = create_bedrock_agent_runtime_client(Settings())
    retriever = BedrockKnowledgeBaseRetriever(client, knowledge_base_id=KB_ID, top_k=5)
    with Stubber(client) as stubber:
        stubber.add_response(
            "retrieve",
            {
                "retrievalResults": [
                    {
                        "content": {"text": "Refunds take 5 days."},
                        "location": {
                            "type": "S3",
                            "s3Location": {"uri": "s3://bucket/policies/returns.md"},
                        },
                        "score": 0.82,
                    },
                    {"content": {"text": "No location here."}, "score": 0.5},
                ]
            },
            expected_params={
                "knowledgeBaseId": KB_ID,
                "retrievalQuery": {"text": "refund timing"},
                "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 5}},
            },
        )
        chunks = await retriever.retrieve("refund timing")

    assert [(c.text, c.source, c.score) for c in chunks] == [
        ("Refunds take 5 days.", "returns.md", 0.82),
        ("No location here.", "unknown source", 0.5),
    ]


async def test_retriever_client_error_becomes_rag_backend_error() -> None:
    client = create_bedrock_agent_runtime_client(Settings())
    retriever = BedrockKnowledgeBaseRetriever(client, knowledge_base_id=KB_ID, top_k=5)
    with Stubber(client) as stubber:
        stubber.add_client_error("retrieve", service_error_code="ThrottlingException")
        with pytest.raises(RagBackendError) as excinfo:
            await retriever.retrieve("anything")

    assert (excinfo.value.stage, excinfo.value.reason) == ("retrieve", "ThrottlingException")


async def test_generator_sends_system_prompt_and_max_tokens_and_returns_text() -> None:
    client = create_bedrock_runtime_client(Settings())
    generator = BedrockConverseGenerator(client, model_id=MODEL_ID, max_tokens=256)
    with Stubber(client) as stubber:
        stubber.add_response(
            "converse",
            {
                "output": {
                    "message": {"role": "assistant", "content": [{"text": "Five days [1]."}]}
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
                "metrics": {"latencyMs": 100},
            },
            expected_params={
                "modelId": MODEL_ID,
                "system": [{"text": "SYSTEM"}],
                "messages": [{"role": "user", "content": [{"text": "USER"}]}],
                "inferenceConfig": {"maxTokens": 256, "temperature": 0.0},
            },
        )
        answer = await generator.generate("SYSTEM", "USER")

    assert answer == "Five days [1]."
    assert (generator.input_tokens, generator.output_tokens) == (10, 4)


async def test_generator_client_error_becomes_rag_backend_error() -> None:
    client = create_bedrock_runtime_client(Settings())
    generator = BedrockConverseGenerator(client, model_id=MODEL_ID, max_tokens=256)
    with Stubber(client) as stubber:
        stubber.add_client_error("converse", service_error_code="ValidationException")
        with pytest.raises(RagBackendError) as excinfo:
            await generator.generate("SYSTEM", "USER")

    assert (excinfo.value.stage, excinfo.value.reason) == ("converse", "ValidationException")


async def test_generator_empty_response_becomes_rag_backend_error() -> None:
    client = create_bedrock_runtime_client(Settings())
    generator = BedrockConverseGenerator(client, model_id=MODEL_ID, max_tokens=256)
    with Stubber(client) as stubber:
        stubber.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": []}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 0, "totalTokens": 10},
                "metrics": {"latencyMs": 100},
            },
        )
        with pytest.raises(RagBackendError, match="empty response"):
            await generator.generate("SYSTEM", "USER")


async def test_timeouts_become_rag_backend_errors() -> None:
    client: Any = _TimingOutClient()

    with pytest.raises(RagBackendError) as retrieve_exc:
        await BedrockKnowledgeBaseRetriever(client, KB_ID, 5).retrieve("q")
    with pytest.raises(RagBackendError) as converse_exc:
        await BedrockConverseGenerator(client, MODEL_ID, 256).generate("s", "u")

    assert retrieve_exc.value.reason == converse_exc.value.reason == "ReadTimeoutError"
