"""Hermetic AWS environment for every test, unit and integration alike.

This runs before any test module (or the app) imports boto3/botocore, so credential
resolution can never fall through to the developer's real ~/.aws config or SSO/login session.
Env-var credentials sit first in botocore's provider chain; forcing dummy values there, and
pointing the config/credentials files at paths that don't exist, means tests behave the same
on a laptop with live AWS access as they do in CI, and can never sign a request as a real
identity. Overwrites (not setdefault) on purpose: a real key exported in the shell must lose.
"""

import os
from pathlib import Path

DUMMY_AWS_ACCESS_KEY_ID = "dummy"
_MISSING_AWS_FILE = Path(__file__).parent / ".no-such-aws-file"

os.environ["AWS_ACCESS_KEY_ID"] = DUMMY_AWS_ACCESS_KEY_ID
os.environ["AWS_SECRET_ACCESS_KEY"] = "dummy"  # noqa: S105 (deliberately fake)
os.environ["AWS_SESSION_TOKEN"] = "dummy"  # noqa: S105 (deliberately fake)
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_CONFIG_FILE"] = str(_MISSING_AWS_FILE)
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(_MISSING_AWS_FILE)
os.environ.pop("AWS_PROFILE", None)
os.environ.pop("AWS_DEFAULT_PROFILE", None)
