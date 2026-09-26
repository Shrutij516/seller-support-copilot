from __future__ import annotations

from typing import TYPE_CHECKING

import boto3

from copilot_api.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient


def create_dynamodb_client(settings: Settings) -> DynamoDBClient:
    return boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )
