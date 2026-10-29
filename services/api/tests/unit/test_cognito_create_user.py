"""scripts/cognito_create_user.py against botocore's Stubber: real clients, request params
validated against the service models, no network.
"""

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "cognito_create_user.py"
POOL = "us-east-1_TESTPOOL"
EMAIL = "seller@example.com"
GOOD_PASSWORD = "Correct-Horse-9"  # noqa: S105 (deliberately fake; 15 chars, policy-shaped)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cognito_create_user", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccu = _load()


def _prompts(*answers: str) -> Any:
    it = iter(answers)
    return lambda _prompt: next(it)


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("", "empty password"),
        (" Correct-Horse-9", "whitespace"),
        ("Correct-Horse-9 ", "whitespace"),
        ("Short-1!", "at least 12"),
    ],
)
def test_validate_password_rejects_bad_input(password: str, reason: str) -> None:
    with pytest.raises(ccu.PasswordRejectedError, match=reason):
        ccu.validate_password(password)


def test_read_password_requires_matching_confirmation() -> None:
    assert ccu.read_password(_prompts(GOOD_PASSWORD, GOOD_PASSWORD)) == GOOD_PASSWORD
    with pytest.raises(ccu.PasswordRejectedError, match="did not match"):
        ccu.read_password(_prompts(GOOD_PASSWORD, "Something-Else-1"))


def test_create_user_sends_exact_request_and_returns_sub() -> None:
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    with Stubber(cognito) as stub:
        stub.add_response(
            "admin_create_user",
            {"User": {"Username": EMAIL, "Attributes": [{"Name": "sub", "Value": "sub-123"}]}},
            expected_params={
                "UserPoolId": POOL,
                "Username": EMAIL,
                "TemporaryPassword": GOOD_PASSWORD,
                "MessageAction": "SUPPRESS",
                "UserAttributes": [
                    {"Name": "email", "Value": EMAIL},
                    {"Name": "email_verified", "Value": "true"},
                ],
            },
        )
        stub.add_response(
            "admin_add_user_to_group",
            {},
            expected_params={"UserPoolId": POOL, "Username": EMAIL, "GroupName": "seller"},
        )
        sub = ccu.create_user(cognito, POOL, EMAIL, "seller", GOOD_PASSWORD)
        stub.assert_no_pending_responses()

    assert sub == "sub-123"


def test_resolve_user_pool_id_reads_stack_output() -> None:
    cfn = boto3.client("cloudformation", region_name="us-east-1")
    with Stubber(cfn) as stub:
        stub.add_response(
            "describe_stacks",
            {
                "Stacks": [
                    {
                        "StackName": "AuthStack",
                        "CreationTime": "2026-10-29T00:00:00Z",
                        "StackStatus": "CREATE_COMPLETE",
                        "Outputs": [{"OutputKey": "UserPoolId", "OutputValue": POOL}],
                    }
                ]
            },
            expected_params={"StackName": "AuthStack"},
        )
        assert ccu.resolve_user_pool_id(cfn, "AuthStack") == POOL


def test_bad_password_is_rejected_before_any_aws_client_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_aws(*_: Any, **__: Any) -> None:
        raise AssertionError("an AWS session was created for a rejected password")

    monkeypatch.setattr(ccu.boto3.session, "Session", no_aws)
    args = argparse.Namespace(email=EMAIL, group="seller", stack="AuthStack", region="us-east-1")

    with pytest.raises(ccu.PasswordRejectedError, match="empty password"):
        ccu.run(args, prompt=_prompts(""))
