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

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
