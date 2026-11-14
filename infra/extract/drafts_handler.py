"""Lambda entry point for draft_documents. Writes PDFs under drafts/ in the case bucket and returns presigned links."""

import logging
import os

import boto3
from botocore.config import Config

from liability_lens.drafts_tool import draft_documents

log = logging.getLogger()
log.setLevel(logging.INFO)

_s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION"), config=Config(signature_version="s3v4"))
_BUCKET = os.environ["EXTRACT_BUCKET"]
LINK_SECONDS = 3600


def _store(key: str, data: bytes) -> str:
    _s3.put_object(Bucket=_BUCKET, Key=key, Body=data, ContentType="application/pdf")
    # The file name travels in the signed URL, so a phone saves "bank-notice.pdf" rather than a random name.
    name = key.rsplit("/", 1)[-1]
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key, "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": f'inline; filename="{name}"'},
        ExpiresIn=LINK_SECONDS)


def handler(event, context):
    # Log argument names only: the case facts are personal data.
    log.info("draft_documents keys=%s", sorted(event or {}))
    try:
        return draft_documents(event, _store)
    except Exception:
        log.exception("draft_documents failed")
        return {"error": "draft_documents failed unexpectedly; please try again"}
