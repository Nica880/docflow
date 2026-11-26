"""SQS job queue (LocalStack locally, real SQS in AWS) — same boto3 code path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from core.config import get_settings


@dataclass(frozen=True)
class Message:
    body: dict[str, Any]
    receipt_handle: str
    receive_count: int


@lru_cache
def sqs_client() -> Any:
    s = get_settings()
    return boto3.client(
        "sqs",
        endpoint_url=s.sqs_endpoint_url,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        region_name=s.s3_region,
        config=Config(connect_timeout=2, read_timeout=30, retries={"max_attempts": 2}),
    )


@lru_cache
def queue_url(name: str | None = None) -> str:
    s = get_settings()
    qname = name or s.sqs_queue_name
    client = sqs_client()
    try:
        return client.get_queue_url(QueueName=qname)["QueueUrl"]
    except client.exceptions.QueueDoesNotExist:
        dlq = client.create_queue(QueueName=f"{qname}-dlq")["QueueUrl"]
        dlq_arn = client.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        return client.create_queue(
            QueueName=qname,
            Attributes={
                "VisibilityTimeout": "900",
                "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}),
            },
        )["QueueUrl"]


def send_batch(bodies: list[dict[str, Any]]) -> int:
    url = queue_url()
    sent = 0
    for i in range(0, len(bodies), 10):
        entries = [
            {"Id": str(j), "MessageBody": json.dumps(b)} for j, b in enumerate(bodies[i : i + 10])
        ]
        if entries:
            sqs_client().send_message_batch(QueueUrl=url, Entries=entries)
            sent += len(entries)
    return sent


def receive(max_messages: int = 1, wait_s: int = 10) -> list[Message]:
    resp = sqs_client().receive_message(
        QueueUrl=queue_url(),
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_s,
        AttributeNames=["ApproximateReceiveCount"],
    )
    return [
        Message(
            body=json.loads(m["Body"]),
            receipt_handle=m["ReceiptHandle"],
            receive_count=int(m.get("Attributes", {}).get("ApproximateReceiveCount", "1")),
        )
        for m in resp.get("Messages", [])
    ]


def delete(msg: Message) -> None:
    sqs_client().delete_message(QueueUrl=queue_url(), ReceiptHandle=msg.receipt_handle)


def depth() -> dict[str, int]:
    attrs = sqs_client().get_queue_attributes(
        QueueUrl=queue_url(),
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return {
        "visible": int(attrs["ApproximateNumberOfMessages"]),
        "in_flight": int(attrs["ApproximateNumberOfMessagesNotVisible"]),
    }
