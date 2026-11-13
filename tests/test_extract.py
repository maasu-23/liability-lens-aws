"""Redaction and field-parsing tests. No OCR needed: they run on text."""

from datetime import date

import pytest

from liability_lens.extract import parse_transaction, redact


def test_otp_and_cvv_on_same_line_are_both_removed():
    """Regression: the 'OTP ... digits' pattern once ate the word OTP and left the code behind."""
    clean, kinds = redact("482913 is your OTP. Do not share. CVV 731")
    assert "482913" not in clean and "731" not in clean
    assert "secret" in kinds


@pytest.mark.parametrize("text,leaked", [
    ("Your OTP is 123456", "123456"),
    ("OTP: 8841", "8841"),
    ("PIN 4321", "4321"),
    ("cvv 73", "73"),  # OCR can drop digits
    ("पासवर्ड 998877", "998877"),
    ("ओटीपी 556677", "556677"),
    ("123456 is your OTP", "123456"),
    ("5588 is the one-time password", "5588"),
])
def test_secrets_removed(text, leaked):
    clean, _ = redact(text)
    assert leaked not in clean


def test_card_and_account_numbers_masked_to_last_four():
    clean, kinds = redact("Card 4111 1111 1111 1234 and a/c 123456789012345")
    assert "4111" not in clean and "1234" in clean and "2345" in clean
    assert "123456789012345" not in clean


def test_aadhaar_removed_but_twelve_digit_utr_kept():
    clean, _ = redact("Aadhaar 2345 6789 0123 UPI Ref 310562625924")
    assert "2345" not in clean
    assert "310562625924" in clean


def test_devanagari_digits_normalised():
    clean, _ = redact("UPI Ref ३१०५६२६२५९२४")
    assert "310562625924" in clean


def test_parse_english_sms():
    t = parse_transaction("SampleBank: Rs.3,80,000.00 debited from A/c XX1184 on 04-01-27 13:37 to VPA ramesh.k@okpay. UPI Ref 330574814669.")
    assert (t.amount, t.utr, t.txn_date, t.direction, t.account_last4, t.counterparty) == (
        380000, "330574814669", date(2027, 1, 4), "DEBIT", "1184", "ramesh.k@okpay")


def test_parse_hindi_sms_and_month_name_date():
    t = parse_transaction("आपके खाते XX1184 से Rs.40,000.00 डेबिट हुए। UPI Ref 330574814669")
    assert t.direction == "DEBIT" and t.amount == 40000
    assert parse_transaction("Paid on 4 Jan 2027, 11:42 AM").txn_date == date(2027, 1, 4)


def test_missing_fields_stay_none_rather_than_guessed():
    t = parse_transaction("Payment successful")
    assert (t.amount, t.utr, t.txn_date, t.counterparty) == (None, None, None, None)


# ---- chat input -------------------------------------------------------------------------

from liability_lens.extract import redact_message  # noqa: E402


@pytest.mark.parametrize("text", [
    "a caller got her to read out OTPs, the last one was 482913.",
    "She shared the OTP with him. Later he asked for her PIN and she said 4417",
    "उसने ओटीपी बताया, आखिरी वाला 482913 था",
    "my mpin is 2580",
])
def test_chat_secret_far_from_keyword_is_removed(text):
    clean, kinds = redact_message(text)
    assert "482913" not in clean and "4417" not in clean and "2580" not in clean
    assert "secret" in kinds


def test_chat_keeps_years_amounts_times_and_last4():
    text = ("On 4 Jan 2027 at 11:02 she read out the OTP and Rs 25000 left account XX4821. "
            "Rs 15,000 more went at 11:09.")
    clean, kinds = redact_message(text)
    assert clean == ("On 4 Jan 2027 at 11:02 she read out the OTP and Rs 25000 left account XX4821. "
                     "Rs 15,000 more went at 11:09.")
    assert kinds == []


def test_chat_numbers_left_alone_without_secret_words():
    clean, kinds = redact_message("The caller's number ended 482913 and the ticket was 5521.")
    assert "482913" in clean and kinds == []
