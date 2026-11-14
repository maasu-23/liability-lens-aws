"""Draft documents: figures come from the tools, secrets and contact details never get in, PDFs render."""

import pytest

from liability_lens import drafts
from liability_lens.drafts_tool import draft_documents
from liability_lens.pdf import render
from test_tools import SUNITA

CASE = {
    **SUNITA,
    "complainant_name": "Sunita Sharma",
    "bank_name": "Example Bank",
    "account_last4": "4821",
    "incident_summary": "A caller said my KYC would expire and I shared the OTP 482913 with him.",
    "as_of": "2027-01-06",
    "transactions": [{**t, "utr": f"70041234567{i}", "mode": "UPI", "beneficiary": "someone@okexample"}
                     for i, t in enumerate(SUNITA["transactions"])],
}


def texts(case):
    docs, blanks, extra = drafts.build(case)
    return {d.kind: d.text() for d in docs}, blanks, extra


def test_rupees_uses_indian_grouping():
    assert [drafts.rupees(n) for n in (500, 25_000, 125_000, 12_345_678)] == \
        ["Rs 500", "Rs 25,000", "Rs 1,25,000", "Rs 1,23,45,678"]


def test_hero_case_figures_and_dates_match_the_rules_engine():
    t, _, _ = texts(CASE)
    bank = t["bank_notice"]
    assert "Rs 25,000 (85% of my net loss of Rs 40,000" in bank
    assert "Please decide and reply in writing by 20 February 2027 (76Q)." in bank
    assert "(76I)" in bank and "(76S)" in bank and "(76K)" in bank
    omb = t["ombudsman_complaint"]
    assert "20 February 2027" in omb and "6 May 2027" in omb and "21 May 2027" in omb
    assert "compensation of Rs 25,000 under para 76T" in omb
    assert "Total debited: Rs 40,000." in t["ncrp_narrative"]


def test_letters_never_concede_customer_negligence():
    t, _, _ = texts(CASE)
    for text in t.values():
        assert "Under para 76N" not in text
        assert "customer liability only until reporting" not in text


def test_bank_negligence_is_asserted_when_the_answers_support_it():
    case = {**CASE, "answers": {"shared_credentials": True, "missing_sms_alert_over_500": True}}
    t, _, _ = texts(case)
    assert "Under para 76L, the outcome should be zero customer liability" in t["bank_notice"]


def test_no_compensation_line_when_not_eligible():
    case = {**CASE, "lifetime_compensation_used": True}
    t, _, _ = texts(case)
    assert "76T" not in t["bank_notice"]
    assert "compensation of" not in t["ombudsman_complaint"]


def test_old_regime_uses_2017_timelines():
    case = {**CASE, "transactions": [{"amount": 8_000, "txn_at": "2026-12-01T10:00",
                                      "alert_received_date": "2026-12-01"}],
            "bank_reported_at": "2026-12-02T09:00", "answers": {"sim_swap_or_telecom_fault": True}}
    t, _, _ = texts(case)
    bank = t["bank_notice"]
    assert "(2017 para 9)" in bank and "(2017 para 10)" in bank
    assert "Under para 2017 para 6(ii)" in bank
    assert "(76I)" not in bank and "76T" not in bank


def test_otp_is_removed_from_the_summary():
    t, _, extra = texts(CASE)
    assert extra["secrets_removed"]
    assert all("482913" not in text for text in t.values())


def test_missing_details_become_blanks_not_guesses():
    case = {k: v for k, v in CASE.items() if k not in ("complainant_name", "bank_name", "account_last4",
                                                         "incident_summary")}
    case["transactions"] = SUNITA["transactions"]
    t, blanks, _ = texts(case)
    assert {"Your full name", "Bank name", "account ending (last 4 digits)",
            "UTR / reference number of each debit", "Phone", "Email", "Signature"} <= set(blanks)
    assert "[Bank name]" in t["bank_notice"]


@pytest.mark.parametrize("field,value,message", [
    ("account_last4", "123456789012", "last 4 digits"),
    ("incident_summary", "x" * 1501, "at most 1500"),
    ("bank_reply", "maybe", "bank_reply"),
    ("documents", ["fir"], "documents must be"),
    ("complainant_name", "x" * 81, "longer than 80"),
])
def test_bad_input_is_an_error_not_a_crash(field, value, message):
    out = draft_documents({**CASE, field: value}, lambda k, b: "u")
    assert message in out["error"]


def test_tool_errors_pass_through():
    assert "bank_reported_at" in draft_documents({**CASE, "bank_reported_at": None}, lambda k, b: "u")["error"]


def test_tool_stores_one_pdf_per_document_under_generated_keys():
    stored = {}

    def store(key, data):
        stored[key] = data
        return f"https://signed.example/{key}"

    out = draft_documents({**CASE, "documents": ["bank_notice", "ombudsman_complaint"]}, store)
    keys = [d["key"] for d in out["documents"]]
    assert [k.rsplit("/", 1)[-1] for k in keys] == ["bank-notice.pdf", "ombudsman-complaint.pdf"]
    assert all(k.startswith("drafts/") and k in stored for k in keys)
    assert all(data.startswith(b"%PDF") for data in stored.values())
    assert out["fill_in"] and out["rules_last_verified"]
    assert {"label": "Bank must decide and reply", "date": "2027-02-20", "citation": "76Q"} in out["key_dates"]


def test_pdf_survives_non_latin_text():
    docs, _, _ = drafts.build({**CASE, "incident_summary": "कॉल आया, ₹40,000 कटे — “KYC” बोला"})
    assert render(docs[0]).startswith(b"%PDF")
