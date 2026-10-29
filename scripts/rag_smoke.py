"""One live RAG answer through the same pieces POST /v1/chat/sessions/{id}/messages uses.

Retrieve (BedrockKnowledgeBaseRetriever) -> filter_by_min_score -> refusal if nothing is
left (no model call, same as the route) -> build_user_message + SYSTEM_PROMPT ->
BedrockConverseGenerator -> make_citations. Prints the answer, citations, and per-stage
latency. Calls real Bedrock with your own AWS session (costs a little); run by hand via
`make rag-smoke Q="..."`. Nothing is stored: no DynamoDB, no Postgres, no HTTP layer.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from copilot_api.config import Settings
from copilot_api.rag.bedrock import (
    BedrockConverseGenerator,
    BedrockKnowledgeBaseRetriever,
    create_bedrock_agent_runtime_client,
    create_bedrock_runtime_client,
)
from copilot_api.rag.prompt import (
    REFUSAL_MESSAGE,
    SYSTEM_PROMPT,
    build_user_message,
    filter_by_min_score,
    make_citations,
)

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.0f} ms"


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

    t = time.perf_counter()
    chunks = await retriever.retrieve(args.question)
    print(f"\n[retrieve] {_ms(t)}: {len(chunks)} chunks")
    for c in chunks:
        print(f"  {c.score:.4f}  {c.source}")

    t = time.perf_counter()
    kept = filter_by_min_score(chunks, min_score)
    print(f"[filter]   {_ms(t)}: {len(kept)} kept at >= {min_score}")

    if not kept:
        print(f"\n[refusal, model not called]\n{REFUSAL_MESSAGE}")
        return

    t = time.perf_counter()
    user_message = build_user_message(args.question, kept)
    print(f"[prompt]   {_ms(t)}: {len(user_message)} chars of user message")

    t = time.perf_counter()
    answer = await generator.generate(SYSTEM_PROMPT, user_message)
    print(f"[converse] {_ms(t)}")

    print(f"\nanswer:\n{answer}\n\ncitations:")
    for citation in make_citations(kept):
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
