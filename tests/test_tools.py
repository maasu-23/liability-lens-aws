"""Tool layer: JSON in, JSON out, numbers from rules.py. Uses the demo's hero case."""

from liability_lens.tools import TOOLS, classify_case, compute_entitlement, deadline_calendar

# Sunita: Mon 4 Jan 2027, a "KYC update" caller gets her OTPs, Rs 40,000 leaves in two UPI debits.
# She calls 1930 that evening and reaches the bank on Wed 6 Jan.
SUNITA = {
    "entity": "CB",
    "account_type": "SB",
    "individual": True,
    "answers": {"shared_credentials": True},
    "transactions": [
        {"id": "t1", "amount": 25_000, "txn_at": "2027-01-04T11:02", "alert_received_date": "2027-01-04"},
        {"id": "t2", "amount": 15_000, "txn_at": "2027-01-04T11:09", "alert_received_date": "2027-01-04"},
    ],
    "ncrp_reported_at": "2027-01-04T19:30",
    "bank_reported_at": "2027-01-06T10:00",
}


def test_registry_lists_the_three_tools():
    assert set(TOOLS) == {"classify_case", "compute_entitlement", "deadline_calendar"}


def test_classify_hero_case_is_76n_candidate():
    out = classify_case(SUNITA)
    assert out["causes"] == ["CUSTOMER_NEGLIGENCE"]
    for t in out["transactions"]:
        assert t["regime"] == "NEW"
        assert t["outcomes"] == [{"cause": "CUSTOMER_NEGLIGENCE",
                                  "verdict": "CUSTOMER_LIABLE_UNTIL_REPORT_LESS_COMPENSATION",
                                  "citation": "76N",
                                  "note": "Compensation under 76T may apply; the bank must still prove negligence"}]
    assert any("Candidate classification only" in n for n in out["notes"])


def test_missing_sms_alert_adds_bank_negligence():
    case = {**SUNITA, "answers": {"shared_credentials": True, "missing_sms_alert_over_500": True}}
    out = classify_case(case)
    assert out["causes"] == ["BANK_NEGLIGENCE", "CUSTOMER_NEGLIGENCE"]
    verdicts = {o["cause"]: o["verdict"] for o in out["transactions"][0]["outcomes"]}
    assert verdicts["BANK_NEGLIGENCE"] == "ZERO_LIABILITY_REVERSAL"
    assert any("Several causes" in n for n in out["notes"])


def test_entitlement_hero_case_matches_rbi_split():
    block = compute_entitlement(SUNITA)["new_regime"]
    assert block["status"] == "ELIGIBLE"
    assert (block["gross_loss"], block["amount"]) == (40_000, 25_000)
    assert (block["rbi"], block["customer_bank"], block["beneficiary_bank"]) == (19_118, 2_941, 2_941)


def test_later_recovery_matches_rbi_illustration_3():
    after = compute_entitlement({**SUNITA, "later_recovery": 15_000})["new_regime"]["after_later_recovery"]
    assert after == {"customer_extra": 11_250, "rbi_refund": 2_868, "customer_bank_refund": 441,
                     "beneficiary_bank_refund": 441, "citation": "76T(3)"}


def test_bank_negligence_points_to_reversal_not_compensation():
    case = {**SUNITA, "answers": {"missing_sms_alert_over_500": True}}
    block = compute_entitlement(case)["new_regime"]
    assert block["status"] == "NOT_ELIGIBLE"
    assert "76L" in block["also_consider"]


def test_loss_above_50000_gets_no_compensation():
    case = {**SUNITA, "transactions": [{"amount": 3_80_000, "txn_at": "2027-01-04T11:02"}]}
    block = compute_entitlement(case)["new_regime"]
    assert block["status"] == "NOT_ELIGIBLE" and block["amount"] == 0
    assert "Gross loss above Rs 50,000" in block["reasons"]


def test_deadlines_hero_case():
    out = deadline_calendar({**SUNITA, "as_of": "2027-01-06"})
    by_label = {d["label"]: d for d in out["deadlines"]}
    assert by_label["Report to the bank and to 1930/NCRP (safe date)"]["date"] == "2027-01-08"
    assert by_label["Report to the bank and to 1930/NCRP (safe date)"]["days_left"] == 2
    assert by_label["Outer limit for the 5-day window (counting rule is open)"]["date"] == "2027-01-09"
    assert by_label["Bank must decide and reply"]["date"] == "2027-02-20"
    assert by_label["File with the RBI Ombudsman by (safe date)"]["date"] == "2027-05-06"
    assert by_label["Latest reading of the Ombudsman filing deadline"]["date"] == "2027-05-21"
    dates = [d["date"] for d in out["deadlines"]]
    assert dates == sorted(dates)


# Second beat: a SIM-swap debit on Mon 28 Dec 2026 falls under the 2017 rules.
SIM_SWAP = {
    "account_type": "SB",
    "answers": {"sim_swap_or_telecom_fault": True},
    "transactions": [{"id": "s1", "amount": 12_000, "txn_at": "2026-12-28T09:00", "alert_received_date": "2026-12-28"}],
    "bank_reported_at": "2027-01-04T10:00",
}


def test_old_regime_working_day_cap():
    # Working days after 28 Dec: 29, 30, 31 Dec, 1 Jan, Sat 2 Jan (1st Saturday), Mon 4 Jan = 6 -> capped
    outcome = classify_case(SIM_SWAP)["transactions"][0]
    assert outcome["regime"] == "OLD"
    assert outcome["outcomes"][0]["verdict"] == "CAPPED_LIABILITY"
    assert outcome["outcomes"][0]["cap"] == 10_000


def test_old_regime_has_no_compensation():
    out = compute_entitlement(SIM_SWAP)
    assert "new_regime" not in out
    assert "No compensation exists" in out["old_regime"]["note"]
    assert out["old_regime"]["liability"][0]["cap"] == 10_000


def test_mixed_regimes_are_flagged():
    case = {**SUNITA, "transactions": SUNITA["transactions"] + SIM_SWAP["transactions"]}
    out = classify_case(case)
    assert {t["regime"] for t in out["transactions"]} == {"NEW", "OLD"}
    assert any("Mixed regimes" in n for n in out["notes"])


def test_bad_input_returns_error_not_exception():
    assert "error" in classify_case({})
    assert "bank_reported_at" in classify_case({**SUNITA, "bank_reported_at": None})["error"]
    assert "ncrp_reported_at" in compute_entitlement({**SUNITA, "ncrp_reported_at": None})["error"]
    assert "unknown answers" in classify_case({**SUNITA, "answers": {"shared_otp": True}})["error"]
    assert "amount" in classify_case({**SUNITA, "transactions": [{"amount": -5, "txn_at": "2027-01-04"}]})["error"]


def test_deadlines_without_bank_report_prompt_action():
    case = {k: v for k, v in SUNITA.items() if k != "bank_reported_at"}
    out = deadline_calendar({**case, "as_of": "2027-01-04"})
    assert any(d["kind"] == "action" for d in out["deadlines"])
