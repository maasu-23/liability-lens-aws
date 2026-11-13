"""extract_transactions tool: screenshots in S3 -> transaction fields, using Tesseract only.

The caller passes S3 keys, never image bytes (a Gateway tool call is capped at 6 MB). Keys must sit
under uploads/ and the bucket is fixed by the Lambda's environment, so a caller cannot point the tool
at another bucket or object. Raw images never go to a model; the returned text is already redacted.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict

from liability_lens.extract import extract_best

MAX_KEYS = 6
MAX_BYTES = 5_000_000
MAX_TEXT = 1_200
KEY_RE = re.compile(r"^uploads/[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
REQUIRED = ("amount", "txn_date", "direction", "utr")
NOTE = ("Read by OCR from the screenshot. Confirm every value with the user before using it. "
        "A screenshot cannot show when the fraud was reported to the bank; ask for that separately.")


def _bad_key(key) -> str | None:
    if not isinstance(key, str) or not KEY_RE.match(key) or ".." in key or key.endswith("/"):
        return "key must look like uploads/<case-id>/<file> using letters, digits, . _ - /"
    if not key.lower().endswith(EXTENSIONS):
        return f"unsupported file type; use one of {', '.join(EXTENSIONS)}"
    return None


def _one(key: str, fetch: Callable[[str], bytes]) -> dict:
    problem = _bad_key(key)
    if problem:
        return {"key": key if isinstance(key, str) else None, "error": problem}
    try:
        data = fetch(key)
    except Exception as e:  # missing object, too large, no permission: say so, do not guess
        return {"key": key, "error": f"could not read the file ({type(e).__name__})"}
    suffix = os.path.splitext(key)[1].lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "upload" + suffix)
        with open(path, "wb") as f:
            f.write(data)
        try:
            txn, text = extract_best(path)
        except Exception:
            return {"key": key, "error": "could not read this image; ask for a clearer screenshot"}
    fields = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in asdict(txn).items()}
    return {
        "key": key,
        "fields": fields,
        "missing": [k for k in REQUIRED if fields[k] is None],
        "secrets_removed": "[SECRET REMOVED]" in text or "[AADHAAR REMOVED]" in text,
        "text": text[:MAX_TEXT],
    }


def extract_transactions(event: dict, fetch: Callable[[str], bytes]) -> dict:
    keys = (event or {}).get("keys")
    if not isinstance(keys, list) or not keys:
        return {"error": "keys must be a non-empty list of S3 keys returned by the upload step"}
    if len(keys) > MAX_KEYS:
        return {"error": f"at most {MAX_KEYS} screenshots per call"}
    return {"images": [_one(k, fetch) for k in keys], "notes": [NOTE]}
