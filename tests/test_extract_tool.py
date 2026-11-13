"""extract_transactions: key validation, error containment, and real OCR on the synthetic fixtures."""

import json
import shutil
from pathlib import Path

import pytest

from liability_lens.extract_tool import MAX_KEYS, extract_transactions

SAMPLES = Path(__file__).parent / "fixtures" / "samples"
TRUTH = json.loads((SAMPLES / "truth.json").read_text())
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


def fetch_from_samples(key: str) -> bytes:
    return (SAMPLES / key.rsplit("/", 1)[-1]).read_bytes()


def never(key: str) -> bytes:
    raise AssertionError("fetch must not be called for a rejected key")


@pytest.mark.parametrize("key", [
    "uploads/../secrets.png", "other/case1/a.png", "uploads/case1/", "/etc/passwd", "uploads/c1/a.exe",
    "s3://bucket/uploads/a.png", "uploads/c 1/a.png", None, 7,
])
def test_bad_keys_are_rejected_before_any_fetch(key):
    out = extract_transactions({"keys": [key]}, never)
    assert "error" in out["images"][0]


@pytest.mark.parametrize("event", [{}, {"keys": []}, {"keys": "uploads/a/b.png"}, None])
def test_missing_keys(event):
    assert "keys must be" in extract_transactions(event, never)["error"]


def test_too_many_keys():
    keys = [f"uploads/c/{i}.png" for i in range(MAX_KEYS + 1)]
    assert "at most" in extract_transactions({"keys": keys}, never)["error"]


def test_fetch_failure_is_reported_not_raised():
    def boom(key):
        raise FileNotFoundError("secret internal path")
    out = extract_transactions({"keys": ["uploads/c1/a.png"]}, boom)
    assert out["images"][0]["error"] == "could not read the file (FileNotFoundError)"


def test_garbage_image_is_reported_not_raised():
    out = extract_transactions({"keys": ["uploads/c1/a.png"]}, lambda k: b"not an image")
    assert "could not read this image" in out["images"][0]["error"]


@needs_tesseract
def test_reads_every_synthetic_sample_and_leaks_no_secret():
    names = sorted(TRUTH)
    out = extract_transactions({"keys": [f"uploads/case1/{n}" for n in names[:MAX_KEYS]]}, fetch_from_samples)
    for name, img in zip(names, out["images"]):
        t = TRUTH[name]
        assert img["fields"]["amount"] == t["amount"], name
        assert img["fields"]["utr"] == t["utr"], name
        assert img["fields"]["txn_date"] == t["date"], name
        assert img["missing"] == [] or img["fields"]["direction"] is None, name
        assert "482913" not in img["text"] and "CVV 731" not in img["text"], name
    assert any(i["secrets_removed"] for i in out["images"]) == any(TRUTH[n]["has_secret"] for n in names[:MAX_KEYS])
