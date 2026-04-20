"""S3 / MinIO helpers.

Thin wrapper around boto3. All operations are synchronous (boto3 is sync);
call from a thread or executor if you need async.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import Config


@dataclass
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_raw: str = "inzohra-raw"
    bucket_raster: str = "inzohra-raster"
    bucket_crops: str = "inzohra-crops"
    bucket_output: str = "inzohra-output"


def make_s3_client(cfg: S3Config) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def upload_bytes(
    client: Any,
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload raw bytes; return the S3 URI ``s3://{bucket}/{key}``."""
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"s3://{bucket}/{key}"


def upload_file(
    client: Any,
    bucket: str,
    key: str,
    path: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a file from disk; return the S3 URI."""
    client.upload_file(
        Filename=path,
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"s3://{bucket}/{key}"


def download_bytes(client: Any, bucket: str, key: str) -> bytes:
    buf = io.BytesIO()
    client.download_fileobj(bucket, key, buf)
    return buf.getvalue()


def public_url(endpoint: str, bucket: str, key: str) -> str:
    """Return the public HTTP URL for a publicly-readable object."""
    return f"{endpoint.rstrip('/')}/{bucket}/{key}"
