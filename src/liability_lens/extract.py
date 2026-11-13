"""Screenshot text -> redacted text -> transaction fields. No model involved.

Pipeline: Tesseract (eng+hin: order matters, hin+eng drops the digit 1) -> redact secrets in code -> regex field extraction.
Only the redacted text may ever be sent to a model. Gaps in extraction are for a
text-only model call to fill, never the raw image.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date

from PIL import Image, ImageOps

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _prepare(image_path: str, target_width: int, tmp_dir: str) -> str:
    """Grayscale, upscale to a target width and pad: Tesseract drops edge characters on small images."""
    img = Image.open(image_path).convert("L")
    if img.width < target_width:
        scale = target_width / img.width
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    img = ImageOps.expand(ImageOps.autocontrast(img), border=60, fill=255)
    out = f"{tmp_dir}/prepared.png"
    img.save(out)
    return out


def ocr(image_path: str, langs: str = "eng+hin", target_width: int = 2400, psm: int = 6) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        prepared = _prepare(image_path, target_width, tmp) if target_width else image_path
        out = subprocess.run(
            ["tesseract", prepared, "stdout", "-l", langs, "--psm", str(psm)],
            capture_output=True, text=True, check=True,
        )
    return out.stdout


# ---- redaction ---------------------------------------------------------------------------

_SECRET_WORDS = r"(?:\b(?:otp|pin|cvv|cvc|password|passcode)\b|ओटीपी|पिन|पासवर्ड)"  # no \b on Devanagari: it is not a word char after vowel signs
_REDACTIONS: list[tuple[str, re.Pattern[str], str]] = [
    # order matters: the lookahead pattern needs the word OTP, which the next pattern would consume
    ("secret", re.compile(r"(?i)\b\d{4,8}\b(?=\s+is\s+(?:your\s+|the\s+)?(?:otp|one[- ]time))"), "[SECRET REMOVED]"),
    ("secret", re.compile(rf"(?i){_SECRET_WORDS}[^\d\n]{{0,20}}\d{{2,8}}"), "[SECRET REMOVED]"),
    ("card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), None),
    ("aadhaar", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), "[AADHAAR REMOVED]"),
    ("account", re.compile(r"\b(?:\d{9,11}|\d{13,18})\b"), None),  # 12 digits is left alone: UTR
]


def _mask_last4(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "X" * (len(digits) - 4) + digits[-4:]


def redact(text: str) -> tuple[str, list[str]]:
    """Mask secrets and long account/card numbers. Returns (clean_text, kinds_redacted)."""
    text = text.translate(DEVANAGARI_DIGITS)
    found: list[str] = []
    for kind, pattern, repl in _REDACTIONS:
        def sub(m: re.Match[str], kind: str = kind, repl: str | None = repl) -> str:
            found.append(kind)
            return repl if repl is not None else _mask_last4(m)
        text = pattern.sub(sub, text)
    return text, found


# ---- field extraction --------------------------------------------------------------------

@dataclass(frozen=True)
class Txn:
    amount: int | None = None  # whole rupees
    utr: str | None = None
    txn_date: date | None = None
    time: str | None = None
    direction: str | None = None  # DEBIT | CREDIT
    counterparty: str | None = None  # UPI ID
    account_last4: str | None = None


_AMOUNT = re.compile(r"(?:Rs\.?|INR|₹|रु\.?)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
_ROW_AMOUNT = re.compile(r"(\d[\d,]*\.\d{2})\s*$", re.M)  # statement rows: no currency symbol
_UTR = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_VPA = re.compile(r"\b([\w.\-]{2,}@[a-z][\w]{1,})\b", re.I)
_ACCT = re.compile(r"(?:[Xx*]{2,}|[Aa]/[Cc]\s*(?:no\.?)?\s*)\s*(\d{4})\b")
_TIME = re.compile(r"\b(\d{1,2}:\d{2})(?::\d{2})?\s*([AP]M)?\b", re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")
_DATE_MON = re.compile(r"\b(\d{1,2})[ -]([A-Za-z]{3})[a-z]*[ -,]*(\d{2,4})\b")
_DEBIT = re.compile(r"(?i)\b(debited|debit|withdrawn|sent|paid)\b|डेबिट|निकाले|भेजे")
_CREDIT = re.compile(r"(?i)\b(credited|received|credit)\b|क्रेडिट|जमा")


def _year(y: str) -> int:
    return 2000 + int(y) if len(y) == 2 else int(y)


def _parse_date(text: str) -> date | None:
    for m in _DATE_NUM.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            continue
    for m in _DATE_MON.finditer(text):
        mo = MONTHS.get(m.group(2).lower())
        if mo:
            try:
                return date(_year(m.group(3)), mo, int(m.group(1)))
            except ValueError:
                continue
    return None


def parse_transaction(text: str) -> Txn:
    """One transaction from one screenshot's redacted text. Missing fields stay None."""
    text = text.translate(DEVANAGARI_DIGITS)
    amt = _AMOUNT.search(text) or _ROW_AMOUNT.search(text)
    time_m = _TIME.search(text)
    direction = "DEBIT" if _DEBIT.search(text) else "CREDIT" if _CREDIT.search(text) else None
    if direction == "DEBIT" and _CREDIT.search(text) and _CREDIT.search(text).start() < _DEBIT.search(text).start():
        direction = None  # ambiguous order: leave it to a human or a text-only model call
    utr = _UTR.search(text)
    vpa = _VPA.search(text)
    acct = _ACCT.search(text)
    return Txn(
        amount=int(float(amt.group(1).replace(",", ""))) if amt else None,
        utr=utr.group(1) if utr else None,
        txn_date=_parse_date(text),
        time=(time_m.group(0).strip() if time_m else None),
        direction=direction,
        counterparty=vpa.group(1) if vpa else None,
        account_last4=acct.group(1) if acct else None,
    )


def extract_best(image_path: str) -> tuple[Txn, str]:
    """OCR twice (eng+hin for Hindi text, eng for Latin tokens), redact each, merge field by field.

    eng+hin wins ties; the eng-only pass fills fields the first pass could not read.
    Returns (transaction, redacted_text_of_first_pass).
    """
    primary, _ = redact(ocr(image_path, "eng+hin"))
    secondary, _ = redact(ocr(image_path, "eng"))
    a, b = parse_transaction(primary), parse_transaction(secondary)
    merged = Txn(**{f: getattr(a, f) if getattr(a, f) is not None else getattr(b, f) for f in Txn.__dataclass_fields__})
    return merged, primary
