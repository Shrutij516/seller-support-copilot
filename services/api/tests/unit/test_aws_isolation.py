import os
from pathlib import Path

import boto3

from tests.conftest import DUMMY_AWS_ACCESS_KEY_ID


def test_tests_cannot_see_real_aws_credentials() -> None:
    # Guards tests/conftest.py: if this fails, a test run could sign requests as whoever is
    # logged in to AWS on this machine.
    credentials = boto3.Session().get_credentials()

    assert credentials is not None
    assert credentials.method == "env"
    assert credentials.access_key == DUMMY_AWS_ACCESS_KEY_ID
    assert "AWS_PROFILE" not in os.environ
    for var in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        assert var in os.environ
        assert not Path(os.environ[var]).exists()
