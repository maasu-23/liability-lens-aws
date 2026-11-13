"""Lambda entry point for extract_transactions. The bucket comes from the environment, never from the caller."""

import logging
import os

import boto3

from liability_lens.extract_tool import MAX_BYTES, extract_transactions

log = logging.getLogger()
log.setLevel(logging.INFO)

_s3 = boto3.client("s3")
_BUCKET = os.environ["EXTRACT_BUCKET"]


def _fetch(key: str) -> bytes:
    head = _s3.head_object(Bucket=_BUCKET, Key=key)
    if head["ContentLength"] > MAX_BYTES:
        raise ValueError("file too large")
    return _s3.get_object(Bucket=_BUCKET, Key=key)["Body"].read()


def handler(event, context):
    # Log the number of keys only: file names and extracted fields are personal data.
    log.info("extract_transactions keys=%s", len((event or {}).get("keys") or []))
    try:
        return extract_transactions(event, _fetch)
    except Exception:
        log.exception("extract_transactions failed")
        return {"error": "extract_transactions failed unexpectedly; please try again"}
