"""One live RAG answer through copilot_api.rag.pipeline.answer_question, the exact function
POST /v1/chat/sessions/{id}/messages calls.

Retrieve -> filter at rag_min_score -> refusal with no model call if nothing is left ->
numbered prompt -> Converse -> keep only the citations the answer marks with [n]. Prints the
answer, citations, and per-stage latency. Calls real Bedrock with your own AWS session
(costs a little); run by hand via `make rag-smoke Q="..."`. Nothing is stored: no DynamoDB,
no Postgres, no HTTP layer.
"""

from __future__ import annotations

import argparse
import asyncio

from copilot_api.config import Settings
from copilot_api.rag.bedrock import (
    BedrockConverseGenerator,
    BedrockKnowledgeBaseRetriever,
    create_bedrock_agent_runtime_client,
    create_bedrock_runtime_client,
)
from copilot_api.rag.pipeline import answer_question

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


async def run(args: argparse.Namespace) -> None:
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    settings = Settings(_env_file=None, aws_region=args.region)  # type: ignore[call-arg]
    min_score = defaults.rag_min_score if args.min_score is None else args.min_score
    retriever = BedrockKnowledgeBaseRetriever(
        create_bedrock_agent_runtime_client(settings),
        knowledge_base_id=args.kb_id,
        top_k=args.top_k,
    )
    generator = BedrockConverseGenerator(
        create_bedrock_runtime_client(settings),
        model_id=args.model_id,
        max_tokens=args.max_tokens,
    )
    print(f"question:  {args.question}")
    print(f"kb:        {args.kb_id}  top_k={args.top_k}  min_score={min_score}")
    print(f"model:     {args.model_id}  max_tokens={args.max_tokens}")

    answer = await answer_question(args.question, retriever, generator, min_score)

    print(f"\n[retrieve] {answer.timings_ms['retrieve']:.0f} ms: {len(answer.retrieved)} chunks")
    for c in answer.retrieved:
        print(f"  {c.score:.4f}  {c.source}")
    print(f"[filter]   {len(answer.kept)} kept at >= {min_score}")
    if answer.refused:
        print(f"\n[refusal, model not called]\n{answer.text}")
        return
    print(f"[converse] {answer.timings_ms['generate']:.0f} ms")
    print(f"tokens:    input {generator.input_tokens}, output {generator.output_tokens}")

    print(f"\nanswer:\n{answer.text}\n")
    print(f"citations (only those marked in the answer): {len(answer.citations)}")
    for citation in answer.citations:
        print(f"  [{citation.index}] {citation.source}: {citation.snippet[:120]!r}")


def main() -> None:
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--top-k", type=int, default=defaults.rag_top_k)
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help=f"defaults to the app's rag_min_score ({defaults.rag_min_score})",
    )
    parser.add_argument("--max-tokens", type=int, default=defaults.rag_max_tokens)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
