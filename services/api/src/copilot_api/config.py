from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "postgresql://copilot:copilot@localhost:5432/copilot"
    # Set only for local dev, where it points at DynamoDB Local; unset (None) in AWS so
    # boto3 talks to the real DynamoDB endpoint for aws_region.
    dynamodb_endpoint_url: str | None = None
    aws_region: str = "us-east-1"
    readiness_timeout_seconds: float = 2.0
    # Comma-separated list of browser origins allowed to call the API.
    cors_allow_origins: str = "http://localhost:3000"

    # Auth (phase 2). No defaults: a real issuer/client id must be configured before the API
    # can verify anything. Tests override all three with a locally generated key and fake JWKS.
    cognito_issuer: str = ""
    cognito_jwks_url: str = ""
    cognito_app_client_id: str = ""

    # RAG chat (phase 4). Per-environment config, not secrets. No defaults for the KB or
    # model id: either must be set explicitly, never baked into code. Until they are, every
    # chat answer fails as a 503 (Bedrock rejects the empty id), not with a guessed model.
    bedrock_knowledge_base_id: str = ""
    bedrock_model_id: str = ""
    rag_top_k: int = 5
    # Relevance floor for retrieved chunks: a cost guard that skips the model call when nothing
    # is even loosely relevant. Chosen from evals/results/retrieval-2026-10-29-02.json: keeps
    # 20/20 in-scope questions (lowest in-scope top score 0.584). Refusing off-topic questions
    # is the prompt's job, not this floor's (DECISIONS.md, "Relevance floor is a cost guard").
    rag_min_score: float = 0.55
    # Output cap per answer: the main per-request cost lever on the model side.
    rag_max_tokens: int = 1024

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
