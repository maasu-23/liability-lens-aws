"""RBI customer-liability rules for electronic banking fraud, as deterministic code.

Two regimes, chosen per transaction by date:
  OLD: RBI circular of 6 Jul 2017 (now paras 64-76 of the 2025 Responsible Business
       Conduct Directions). Working days counted from the bank's alert. No compensation.
  NEW: Third Amendment Directions of 24 Jun 2026 (RBI/2026-27/167 to /173), for
       transactions undertaken on or after 1 Jan 2027. Paras 76A-76V (commercial banks).

Every ambiguity in RBI's text resolves in the victim's favour. See
docs/rbi-rules-verification.md for sources and the open-items table.
The model never decides liability; it only interviews. The output is a *candidate*
classification: the bank classifies, and carries the burden of proof (76K / 2017 para 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

NEW_REGIME_START = date(2027, 1, 1)
COMPENSATION_SUNSET = date(2027, 12, 31)  # 76U "one year from effective date"; exact day open
PREFIX = {"CB": "76", "SFB": "76", "PB": "33", "LAB": "16", "RRB": "128", "UCB": "65.1", "RCB": "70"}

COMP_MAX_GROSS = 50_000
COMP_CAP = 25_000
COMP_PCT = 85
SPLIT_THRESHOLD_NET = 29_412
FIXED_SPLIT = {"domestic": (19_118, 2_941, 2_941), "cross_border": (19_118, 5_882, 0)}


class Cause(str, Enum):
    BANK_NEGLIGENCE = "BANK_NEGLIGENCE"
    THIRD_PARTY_BREACH = "THIRD_PARTY_BREACH"
    CUSTOMER_NEGLIGENCE = "CUSTOMER_NEGLIGENCE"
    COVERAGE_UNCERTAIN = "COVERAGE_UNCERTAIN"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass(frozen=True)
class Answers:
    """Facts gathered by the interview. Code maps them to causes; the model only asks."""

    missing_sms_alert_over_500: bool = False
    bank_ignored_notification: bool = False
    bank_system_breach: bool = False
    sim_swap_or_telecom_fault: bool = False
    tpap_pa_pg_breach: bool = False
    shared_credentials: bool = False
    ignored_specific_bank_warning: bool = False
    installed_malicious_app: bool = False
    coerced_approval: bool = False
    pure_deception_no_credentials_no_coercion: bool = False


@dataclass(frozen=True)
class Outcome:
    verdict: str
    citation: str
    cap: int | None = None
    note: str = ""


def regime_for(txn_date: date) -> str:
    return "NEW" if txn_date >= NEW_REGIME_START else "OLD"


def candidate_causes(a: Answers) -> set[Cause]:
    """Map interview answers to candidate limbs. Several may apply; show all of them."""
    causes: set[Cause] = set()
    if a.missing_sms_alert_over_500 or a.bank_ignored_notification or a.bank_system_breach:
        causes.add(Cause.BANK_NEGLIGENCE)  # 4(20B)(ii)/(iv)/(v)
    if a.sim_swap_or_telecom_fault or a.tpap_pa_pg_breach:
        causes.add(Cause.THIRD_PARTY_BREACH)  # 4(26.1A)
    if a.shared_credentials or a.ignored_specific_bank_warning or a.installed_malicious_app or a.coerced_approval:
        causes.add(Cause.CUSTOMER_NEGLIGENCE)  # coercion most likely lands here (inference)
    if a.pure_deception_no_credentials_no_coercion:
        causes.add(Cause.COVERAGE_UNCERTAIN)  # draft APP category was dropped from the final text
    return causes or {Cause.UNCLASSIFIED}


# ---- NEW regime: transactions on or after 1 Jan 2027 -------------------------------------


def window_status(txn_date: date, report_date: date) -> str:
    """5 calendar days 'from the date of occurrence'. Day-0 vs day-1 is open, so day 5 is BORDERLINE."""
    days = (report_date - txn_date).days
    if days <= 4:
        return "WITHIN"
    if days == 5:
        return "BORDERLINE"
    return "OUTSIDE"


def classify_new(txn_at: datetime, bank_reported_at: datetime, cause: Cause, entity: str = "CB") -> Outcome:
    p = PREFIX[entity]
    if txn_at > bank_reported_at:
        return Outcome("BANK_BEARS", p + "O", note="Losses after the customer reports fall on the bank")
    if cause is Cause.BANK_NEGLIGENCE:
        return Outcome("ZERO_LIABILITY_REVERSAL", p + "L", note="Applies whether or not the customer reported")
    if cause is Cause.THIRD_PARTY_BREACH:
        status = window_status(txn_at.date(), bank_reported_at.date())
        if status == "WITHIN":
            return Outcome("ZERO_LIABILITY_REVERSAL", p + "M")
        if status == "BORDERLINE":
            return Outcome("ZERO_LIABILITY_REVERSAL_BORDERLINE", p + "M", note="Day 5: counting rule is open")
        return Outcome("PER_BANK_POLICY", p + "M", note="Reported after 5 calendar days; see the bank's published policy")
    if cause is Cause.CUSTOMER_NEGLIGENCE:
        return Outcome("CUSTOMER_LIABLE_UNTIL_REPORT_LESS_COMPENSATION", p + "N",
                       note="Compensation under 76T may apply; the bank must still prove negligence")
    if cause is Cause.COVERAGE_UNCERTAIN:
        return Outcome("MANUAL_REVIEW", "4(15A)", note="Pure deception is not expressly covered")
    return Outcome("LIABILITY_NOT_ESTABLISHED_BY_BANK", p + "K", note="Burden of proof is on the bank")


def _pct(amount: int, pct: int) -> int:
    return (amount * pct + 50) // 100  # round half up to the rupee


def split_for(net: int, cross_border: bool = False) -> tuple[int, int, int, int]:
    """Return (compensation, rbi, customer_bank, beneficiary_bank). Split is keyed on NET loss."""
    comp = min(_pct(net, COMP_PCT), COMP_CAP)
    if net < SPLIT_THRESHOLD_NET:
        own = _pct(net, 20 if cross_border else 10)
        ben = 0 if cross_border else _pct(net, 10)
        return comp, comp - own - ben, own, ben
    rbi, own, ben = FIXED_SPLIT["cross_border" if cross_border else "domestic"]
    return comp, rbi, own, ben


@dataclass(frozen=True)
class Compensation:
    status: str  # ELIGIBLE | BORDERLINE | NOT_ELIGIBLE
    reasons: tuple[str, ...]
    net_loss: int
    amount: int
    rbi: int
    customer_bank: int
    beneficiary_bank: int


def compensation(
    *,
    gross_loss: int,
    recoveries: int,
    cause: Cause,
    individual: bool,
    first_txn_date: date,
    ncrp_report_date: date,
    bank_report_date: date,
    cross_border: bool = False,
    lifetime_used: bool = False,
    sunset: date = COMPENSATION_SUNSET,
) -> Compensation:
    """76T: 85% of net loss, capped at Rs 25,000, once in a lifetime, customer-negligence cases only.

    `recoveries` counts only amounts credited to the customer, not funds merely lien-marked.
    """
    why: list[str] = []
    if not individual:
        why.append("Only individuals (including sole proprietors) qualify")
    if cause is not Cause.CUSTOMER_NEGLIGENCE:
        why.append("Compensation applies only to customer-negligence cases (76N)")
    if gross_loss > COMP_MAX_GROSS:
        why.append("Gross loss above Rs 50,000")
    if lifetime_used:
        why.append("Compensation already used once")
    if not (NEW_REGIME_START <= first_txn_date <= sunset):
        why.append("Fraud outside the compensation period (76U)")
    windows = {window_status(first_txn_date, ncrp_report_date), window_status(first_txn_date, bank_report_date)}
    if "OUTSIDE" in windows:
        why.append("Not reported to both NCRP/1930 and the bank within 5 calendar days")
    net = max(0, gross_loss - recoveries)
    if why:
        return Compensation("NOT_ELIGIBLE", tuple(why), net, 0, 0, 0, 0)
    comp, rbi, own, ben = split_for(net, cross_border)
    status = "BORDERLINE" if "BORDERLINE" in windows else "ELIGIBLE"
    reasons = ("Reported on day 5: counting rule is open",) if status == "BORDERLINE" else ()
    return Compensation(status, reasons, net, comp, rbi, own, ben)


@dataclass(frozen=True)
class Recalculation:
    customer_extra: int
    rbi_refund: int
    customer_bank_refund: int
    beneficiary_bank_refund: int


def recalculate_after_recovery(
    *, gross_loss: int, paid: Compensation, total_recovered: int, newly_recovered: int, cross_border: bool = False
) -> Recalculation:
    """76T(3): recoveries after payment. Customer gets the new money plus any compensation change;
    funders are refunded the difference in their shares."""
    net = max(0, gross_loss - total_recovered)
    new_comp, rbi, own, ben = split_for(net, cross_border) if net else (0, 0, 0, 0)
    return Recalculation(
        customer_extra=newly_recovered + new_comp - paid.amount,
        rbi_refund=paid.rbi - rbi,
        customer_bank_refund=paid.customer_bank - own,
        beneficiary_bank_refund=paid.beneficiary_bank - ben,
    )


# ---- OLD regime: transactions before 1 Jan 2027 ------------------------------------------

CAPS = {
    "BSBD": 5_000,
    "SB": 10_000,
    "PPI_GIFT": 10_000,
    "MSME_CA_CC_OD": 10_000,
    "INDIV_CA_CC_OD_UPTO_25L": 10_000,
    "CC_UPTO_5L": 10_000,
    "OTHER_CA_CC_OD": 25_000,
    "CC_ABOVE_5L": 25_000,
}


def is_working_day(d: date, holidays: frozenset[date] = frozenset()) -> bool:
    """Approximation of a home-branch calendar: Sundays, 2nd/4th Saturdays and listed holidays are off."""
    if d.weekday() == 6 or d in holidays:
        return False
    if d.weekday() == 5 and (d.day - 1) // 7 in (1, 3):
        return False
    return True


def working_days_between(alert_date: date, report_date: date, holidays: frozenset[date] = frozenset()) -> int:
    """Working days after the alert date (alert day excluded) up to and including the report date."""
    count, d = 0, alert_date + timedelta(days=1)
    while d <= report_date:
        count += is_working_day(d, holidays)
        d += timedelta(days=1)
    return count


def add_working_days(start: date, n: int, holidays: frozenset[date] = frozenset()) -> date:
    d = start
    while n > 0:
        d += timedelta(days=1)
        n -= is_working_day(d, holidays)
    return d


def classify_old(
    *,
    txn_at: datetime,
    bank_reported_at: datetime,
    alert_received_date: date | None,
    cause: Cause,
    account_type: str,
    amount: int,
    holidays: frozenset[date] = frozenset(),
) -> Outcome:
    if txn_at > bank_reported_at:
        return Outcome("BANK_BEARS", "2017 para 7(i)")
    if cause is Cause.BANK_NEGLIGENCE:
        return Outcome("ZERO_LIABILITY", "2017 para 6(i)")
    if cause is Cause.CUSTOMER_NEGLIGENCE:
        return Outcome("CUSTOMER_LIABLE_UNTIL_REPORT", "2017 para 7(i)", note="No compensation exists before 2027")
    if cause is Cause.THIRD_PARTY_BREACH:
        if alert_received_date is None:
            return Outcome("CANNOT_COMPUTE_DAY_ZERO", "2017 para 5/12",
                           note="No alert on record; the bank must keep timestamped alerts and carries the burden of proof")
        days = working_days_between(alert_received_date, bank_reported_at.date(), holidays)
        if days <= 3:
            return Outcome("ZERO_LIABILITY", "2017 para 6(ii)")
        if days <= 7:
            cap = min(amount, CAPS[account_type])
            return Outcome("CAPPED_LIABILITY", "2017 para 7(ii), Table 1", cap=cap)
        return Outcome("PER_BANK_POLICY", "2017 para 7(ii)")
    return Outcome("LIABILITY_NOT_ESTABLISHED_BY_BANK", "2017 para 12")


# ---- Deadlines ----------------------------------------------------------------------------


@dataclass(frozen=True)
class NewRegimeDeadlines:
    report_safe_by: date  # txn + 4 (earliest reading)
    report_outer_by: date  # txn + 5
    bank_decision_due: date  # receipt + 45 (60 cross-border)
    ombudsman_open_from: date  # latest reading; immediately on a rejection
    ombudsman_file_by_earliest: date  # receipt + 30 + 90
    ombudsman_file_by_latest: date  # bank_decision_due + 90


def new_regime_deadlines(txn_date: date, bank_receipt_date: date, cross_border: bool = False) -> NewRegimeDeadlines:
    decision = bank_receipt_date + timedelta(days=60 if cross_border else 45)
    return NewRegimeDeadlines(
        report_safe_by=txn_date + timedelta(days=4),
        report_outer_by=txn_date + timedelta(days=5),
        bank_decision_due=decision,
        ombudsman_open_from=decision,
        ombudsman_file_by_earliest=bank_receipt_date + timedelta(days=30 + 90),
        ombudsman_file_by_latest=decision + timedelta(days=90),
    )


@dataclass(frozen=True)
class OldRegimeDeadlines:
    zero_liability_report_by: date | None
    shadow_credit_due: date  # notification + 10 working days
    resolution_due: date  # receipt + 90 calendar days


def old_regime_deadlines(
    alert_received_date: date | None, bank_notified_date: date, holidays: frozenset[date] = frozenset()
) -> OldRegimeDeadlines:
    zero_by = add_working_days(alert_received_date, 3, holidays) if alert_received_date else None
    return OldRegimeDeadlines(
        zero_liability_report_by=zero_by,
        shadow_credit_due=add_working_days(bank_notified_date, 10, holidays),
        resolution_due=bank_notified_date + timedelta(days=90),
    )
