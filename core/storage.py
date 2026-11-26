"""S3-compatible object storage (MinIO locally, S3 in AWS) — same boto3 code path."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.config import Config
from botocore.exceptions import ClientError

from core.config import get_settings


@lru_cache
def s3_client() -> Any:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
    )


def ensure_buckets() -> None:
    s = get_settings()
    client = s3_client()
    for bucket in (s.bronze_bucket, s.silver_bucket):
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError:
            client.create_bucket(Bucket=bucket)


def put_bytes(bucket: str, key: str, data: bytes, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    s3_client().put_object(Bucket=bucket, Key=key, Body=data, **extra)


def get_bytes(bucket: str, key: str) -> bytes:
    obj = s3_client().get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


def exists(bucket: str, key: str) -> bool:
    try:
        s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def put_parquet(bucket: str, key: str, table: pa.Table) -> None:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    put_bytes(bucket, key, buf.getvalue(), "application/vnd.apache.parquet")


def get_parquet(bucket: str, key: str) -> pa.Table:
    return pq.read_table(io.BytesIO(get_bytes(bucket, key)))
