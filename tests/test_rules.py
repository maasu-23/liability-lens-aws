"""Golden tests. The compensation cases reproduce RBI's own worked illustrations (76T)."""

from datetime import date, datetime

import pytest

from liability_lens.rules import (
    Answers,
    Cause,
    add_working_days,
    candidate_causes,
    classify_new,
    classify_old,
    compensation,
    is_working_day,
    new_regime_deadlines,
    old_regime_deadlines,
    recalculate_after_recovery,
    regime_for,
    split_for,
    window_status,
    working_days_between,
)

JAN4 = date(2027, 1, 4)  # a Monday
JAN6 = date(2027, 1, 6)


def comp(**kw):
    base = dict(
        gross_loss=40_000, recoveries=0, cause=Cause.CUSTOMER_NEGLIGENCE, individual=True,
        first_txn_date=JAN4, ncrp_report_date=JAN4, bank_report_date=JAN6,
    )
    return compensation(**{**base, **kw})


# ---- regime selection ----

def test_regime_switches_on_transaction_date_not_report_date():
    assert regime_for(date(2026, 12, 31)) == "OLD"
    assert regime_for(date(2027, 1, 1)) == "NEW"


# ---- RBI illustrations (gross loss Rs 40,000 each) ----

def test_illustration_1_recovery_before_payment():
    c = comp(recoveries=15_000)
    assert c.status == "ELIGIBLE"
    assert (c.net_loss, c.amount, c.rbi, c.customer_bank, c.beneficiary_bank) == (25_000, 21_250, 16_250, 2_500, 2_500)


def test_illustration_2_full_recovery_after_payment():
    paid = comp()
    assert (paid.amount, paid.rbi, paid.customer_bank, paid.beneficiary_bank) == (25_000, 19_118, 2_941, 2_941)
    r = recalculate_after_recovery(gross_loss=40_000, paid=paid, total_recovered=40_000, newly_recovered=40_000)
    assert (r.customer_extra, r.rbi_refund, r.customer_bank_refund, r.beneficiary_bank_refund) == (15_000, 19_118, 2_941, 2_941)


def test_illustration_3_partial_recovery_after_payment():
    paid = comp()
    r = recalculate_after_recovery(gross_loss=40_000, paid=paid, total_recovered=15_000, newly_recovered=15_000)
    assert (r.customer_extra, r.rbi_refund, r.customer_bank_refund, r.beneficiary_bank_refund) == (11_250, 2_868, 441, 441)


# ---- compensation eligibility ----

@pytest.mark.parametrize("kw,fragment", [
    (dict(cause=Cause.THIRD_PARTY_BREACH), "customer-negligence"),
    (dict(cause=Cause.BANK_NEGLIGENCE), "customer-negligence"),
    (dict(gross_loss=50_001), "Rs 50,000"),
    (dict(individual=False), "individuals"),
    (dict(lifetime_used=True), "already used"),
    (dict(first_txn_date=date(2026, 12, 31), ncrp_report_date=date(2026, 12, 31), bank_report_date=date(2026, 12, 31)), "period"),
    (dict(bank_report_date=date(2027, 1, 12)), "5 calendar days"),
    (dict(ncrp_report_date=date(2027, 1, 12)), "5 calendar days"),
])
def test_not_eligible(kw, fragment):
    c = comp(**kw)
    assert c.status == "NOT_ELIGIBLE" and c.amount == 0
    assert any(fragment in r for r in c.reasons)


def test_day_five_report_is_borderline_not_denied():
    c = comp(bank_report_date=date(2027, 1, 9))
    assert c.status == "BORDERLINE" and c.amount == 25_000


def test_digital_arrest_sized_loss_gets_no_compensation():
    c = comp(gross_loss=380_000)
    assert c.status == "NOT_ELIGIBLE" and c.amount == 0


def test_cross_border_split():
    assert split_for(20_000, cross_border=True) == (17_000, 17_000 - 4_000, 4_000, 0)
    assert split_for(40_000, cross_border=True) == (25_000, 19_118, 5_882, 0)


@pytest.mark.parametrize("net", [1, 999, 10_001, 29_411, 29_412, 40_000, 50_000])
def test_split_always_sums_to_amount(net):
    amount, rbi, own, ben = split_for(net)
    assert rbi + own + ben == amount <= 25_000


# ---- new-regime classification ----

def at(d, h=12):
    return datetime(d.year, d.month, d.day, h)


def test_bank_negligence_is_zero_liability_even_when_reported_late():
    o = classify_new(at(JAN4), at(date(2027, 3, 1)), Cause.BANK_NEGLIGENCE)
    assert (o.verdict, o.citation) == ("ZERO_LIABILITY_REVERSAL", "76L")


def test_third_party_breach_windows():
    assert classify_new(at(JAN4), at(date(2027, 1, 8)), Cause.THIRD_PARTY_BREACH).verdict == "ZERO_LIABILITY_REVERSAL"
    assert classify_new(at(JAN4), at(date(2027, 1, 9)), Cause.THIRD_PARTY_BREACH).verdict == "ZERO_LIABILITY_REVERSAL_BORDERLINE"
    assert classify_new(at(JAN4), at(date(2027, 1, 10)), Cause.THIRD_PARTY_BREACH).verdict == "PER_BANK_POLICY"


def test_customer_negligence_routes_to_76n_and_commercial_prefix_used_per_entity():
    assert classify_new(at(JAN4), at(JAN6), Cause.CUSTOMER_NEGLIGENCE).citation == "76N"
    assert classify_new(at(JAN4), at(JAN6), Cause.CUSTOMER_NEGLIGENCE, entity="RRB").citation == "128N"


def test_debits_after_reporting_fall_on_bank():
    assert classify_new(at(JAN6, 15), at(JAN6, 9), Cause.CUSTOMER_NEGLIGENCE).citation == "76O"


def test_unclassified_leaves_burden_on_bank():
    assert classify_new(at(JAN4), at(JAN6), Cause.UNCLASSIFIED).citation == "76K"


def test_window_status():
    assert window_status(JAN4, date(2027, 1, 8)) == "WITHIN"
    assert window_status(JAN4, date(2027, 1, 9)) == "BORDERLINE"
    assert window_status(JAN4, date(2027, 1, 10)) == "OUTSIDE"


# ---- interview mapping ----

def test_missing_sms_alert_points_to_bank_negligence():
    assert Cause.BANK_NEGLIGENCE in candidate_causes(Answers(missing_sms_alert_over_500=True))


def test_shared_otp_and_missing_alert_shows_both_limbs():
    c = candidate_causes(Answers(shared_credentials=True, missing_sms_alert_over_500=True))
    assert c == {Cause.BANK_NEGLIGENCE, Cause.CUSTOMER_NEGLIGENCE}


def test_no_facts_is_unclassified_and_pure_deception_needs_review():
    assert candidate_causes(Answers()) == {Cause.UNCLASSIFIED}
    assert candidate_causes(Answers(pure_deception_no_credentials_no_coercion=True)) == {Cause.COVERAGE_UNCERTAIN}


# ---- deadlines ----

def test_worked_example_from_report():
    """Fraud Mon 4 Jan 2027, reported to the bank Wed 6 Jan 2027."""
    d = new_regime_deadlines(JAN4, JAN6)
    assert d.report_safe_by == date(2027, 1, 8) and d.report_outer_by == date(2027, 1, 9)
    assert d.bank_decision_due == date(2027, 2, 20)
    assert d.ombudsman_open_from == date(2027, 2, 20)
    assert d.ombudsman_file_by_earliest == date(2027, 5, 6)
    assert d.ombudsman_file_by_latest == date(2027, 5, 21)


def test_cross_border_decision_is_60_days():
    assert new_regime_deadlines(JAN4, JAN6, cross_border=True).bank_decision_due == date(2027, 3, 7)


# ---- old regime ----

def old(report, alert, account="SB", amount=20_000, cause=Cause.THIRD_PARTY_BREACH):
    return classify_old(
        txn_at=datetime(2026, 12, 28, 11), bank_reported_at=datetime.combine(report, datetime.min.time()),
        alert_received_date=alert, cause=cause, account_type=account, amount=amount,
    )


def test_working_day_calendar():
    assert not is_working_day(date(2026, 12, 27))  # Sunday
    assert not is_working_day(date(2026, 12, 12))  # 2nd Saturday
    assert is_working_day(date(2026, 12, 5))  # 1st Saturday
    assert not is_working_day(date(2026, 12, 26))  # 4th Saturday
    assert working_days_between(date(2026, 12, 28), date(2026, 12, 29)) == 1  # alert day excluded


def test_old_regime_zero_then_capped_then_policy():
    alert = date(2026, 12, 28)  # Monday
    assert old(date(2026, 12, 31), alert).verdict == "ZERO_LIABILITY"  # 3 working days
    o = old(date(2027, 1, 2), alert)  # working day 5 (Tue, Wed, Thu, Fri, Sat)
    assert o.verdict == "CAPPED_LIABILITY" and o.cap == 10_000
    assert old(date(2027, 1, 20), alert).verdict == "PER_BANK_POLICY"


def test_old_cap_never_exceeds_transaction_value_and_varies_by_account():
    alert = date(2026, 12, 28)
    assert old(date(2027, 1, 2), alert, amount=3_000).cap == 3_000
    assert old(date(2027, 1, 2), alert, account="BSBD").cap == 5_000
    assert old(date(2027, 1, 2), alert, account="OTHER_CA_CC_OD", amount=40_000).cap == 25_000


def test_old_regime_has_no_compensation_and_needs_an_alert_to_count_days():
    o = old(date(2027, 1, 2), None)
    assert o.verdict == "CANNOT_COMPUTE_DAY_ZERO"
    assert "No compensation" in old(date(2027, 1, 2), date(2026, 12, 28), cause=Cause.CUSTOMER_NEGLIGENCE).note


def test_old_regime_deadlines():
    d = old_regime_deadlines(date(2026, 12, 28), date(2026, 12, 29))
    assert d.zero_liability_report_by == date(2026, 12, 31)
    assert d.resolution_due == date(2027, 3, 29)
    assert d.shadow_credit_due == add_working_days(date(2026, 12, 29), 10)
