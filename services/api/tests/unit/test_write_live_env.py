"""scripts/write_live_env.py: generated env content and backup-before-replace behavior."""

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "write_live_env.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("write_live_env", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wle = _load()
ARGS = argparse.Namespace(
    issuer="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EXAMPLE/",
    client_id="exampleclientid",
    domain="https://example-prefix.auth.us-east-1.amazoncognito.com/",
    kb_id="KBEXAMPLE1",
    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
)


def _as_dict(text: str) -> dict[str, str]:
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    return dict(line.split("=", 1) for line in lines)


def test_api_env_has_live_values_and_no_aws_credentials() -> None:
    env = _as_dict(wle.api_env(ARGS))

    assert env["COGNITO_ISSUER"] == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EXAMPLE"
    assert env["COGNITO_JWKS_URL"] == f"{env['COGNITO_ISSUER']}/.well-known/jwks.json"
    assert env["COGNITO_APP_CLIENT_ID"] == "exampleclientid"
    assert env["BEDROCK_KNOWLEDGE_BASE_ID"] == "KBEXAMPLE1"
    assert env["BEDROCK_MODEL_ID"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert env["DYNAMODB_ENDPOINT_URL"] == "http://localhost:8001"
    assert env["CORS_ALLOW_ORIGINS"] == "http://localhost:3000"
    assert not any(k.startswith("AWS_ACCESS") or "SECRET" in k or "TOKEN" in k for k in env)


def test_web_env_points_at_host_api_and_cognito() -> None:
    env = _as_dict(wle.web_env(ARGS))

    assert env["NEXT_PUBLIC_API_BASE_URL"] == "http://localhost:8000"
    assert (
        env["NEXT_PUBLIC_COGNITO_DOMAIN"]
        == "https://example-prefix.auth.us-east-1.amazoncognito.com"
    )
    assert env["NEXT_PUBLIC_COGNITO_REDIRECT_URI"] == "http://localhost:3000/auth/callback"
    assert env["NEXT_PUBLIC_COGNITO_LOGOUT_URI"] == "http://localhost:3000"


def test_existing_file_is_backed_up_before_replacement(tmp_path: Path) -> None:
    target = tmp_path / ".env.local"
    target.write_text("OLD=1\n")

    backup = wle.write_with_backup(target, "NEW=1\n")

    assert target.read_text() == "NEW=1\n"
    assert backup is not None and backup.read_text() == "OLD=1\n"
    assert wle.write_with_backup(target, "NEW=1\n") is None  # identical content: no new backup
