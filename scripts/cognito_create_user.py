"""Create an invite-only Cognito user in AuthStack's pool and add them to a group.

Run via `make auth-create-user EMAIL=... GROUP=seller|admin`. Uses your own AWS session
(`aws login`; botocore[crt] is a dev dependency of the API venv this runs in).

The temporary password is read with getpass (no echo, works the same in zsh, bash or sh) and
sent in a single boto3 AdminCreateUser call. It never appears in a process argument list, a
file, a pipe to another program, or the terminal. It is validated BEFORE any AWS call:
non-empty, no leading/trailing whitespace (Cognito's TemporaryPassword pattern), at least the
pool's minimum length, and typed twice.

Why not the AWS CLI: aws-cli v2 reads `--cli-input-json file://...` more than once, so a
one-shot source (stdin, a FIFO) is consumed on the first read and the second read gets nothing
("Invalid JSON received") or blocks. See DECISIONS.md Incidents, "make auth-create-user
failed".
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from collections.abc import Callable
from typing import Any

import boto3

# Cognito AdminCreateUser TemporaryPassword pattern: ^[\S]+.*[\S]+$ (no leading/trailing
# whitespace, at least two characters). AuthStack's password policy requires 12+ characters.
_COGNITO_PASSWORD_PATTERN = re.compile(r"^[\S]+.*[\S]+$")
MIN_PASSWORD_LENGTH = 12
GROUPS = ("seller", "admin")


class PasswordRejectedError(ValueError):
    pass


def validate_password(password: str) -> None:
    if not password:
        raise PasswordRejectedError("empty password")
    if not _COGNITO_PASSWORD_PATTERN.fullmatch(password):
        raise PasswordRejectedError("password must not start or end with whitespace")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordRejectedError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def read_password(prompt: Callable[[str], str] = getpass.getpass) -> str:
    first = prompt("Temporary password (not shown): ")
    validate_password(first)
    if prompt("Repeat it (not shown): ") != first:
        raise PasswordRejectedError("passwords did not match")
    return first


def resolve_user_pool_id(cloudformation: Any, stack_name: str) -> str:
    stacks = cloudformation.describe_stacks(StackName=stack_name)["Stacks"]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stacks[0].get("Outputs", [])}
    pool_id = outputs.get("UserPoolId")
    if not pool_id:
        raise SystemExit(f"No UserPoolId output on stack {stack_name}.")
    return str(pool_id)


def create_user(cognito: Any, pool_id: str, email: str, group: str, password: str) -> str:
    """AdminCreateUser (invitation suppressed, email pre-verified) + AdminAddUserToGroup.
    Returns the new user's `sub`, needed for `make link-user`.
    """
    response = cognito.admin_create_user(
        UserPoolId=pool_id,
        Username=email,
        TemporaryPassword=password,
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
    )
    sub = next(a["Value"] for a in response["User"]["Attributes"] if a["Name"] == "sub")
    cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=email, GroupName=group)
    return str(sub)


def run(args: argparse.Namespace, prompt: Callable[[str], str] = getpass.getpass) -> str:
    password = read_password(prompt)  # validated before any AWS call
    session = boto3.session.Session(region_name=args.region)
    pool_id = resolve_user_pool_id(session.client("cloudformation"), args.stack)
    sub = create_user(session.client("cognito-idp"), pool_id, args.email, args.group, password)
    del password
    print(f"Created {args.email} in group {args.group} (sub {sub}).")
    print("They must set a new password at first sign-in.")
    if args.group == "seller":
        print(f"Link to a seller row: make link-user EMAIL=<seed seller email> SUB={sub}")
    return sub


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--group", required=True, choices=GROUPS)
    parser.add_argument("--stack", default="AuthStack")
    parser.add_argument("--region", default="us-east-1")
    try:
        run(parser.parse_args())
    except PasswordRejectedError as exc:
        print(f"Not created: {exc}. No AWS call was made.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
