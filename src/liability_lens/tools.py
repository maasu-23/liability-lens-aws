"""JSON-in, JSON-out tools the agent calls through the Gateway.

Each tool takes the case facts as a plain dict and returns a plain dict, so the Lambda handler
only dispatches. All liability, money and date logic stays in rules.py; this module validates
input, applies the right regime to each transaction, and attaches citations and caveats.

Errors come back as {"error": "..."} instead of raising, so the model can ask the user for the
missing fact rather than fail.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta

from liability_lens import rules
from liability_lens.rules import Answers, Cause

RULES_VERIFIED = "2026-11-13"
CAVEAT = ("Candidate classification only. The bank classifies the complaint and carries the burden "
          "of proof. Legal information, not legal advice.")
PENDING_NOTE = ("A Supreme Court case on digital-arrest fraud may lead RBI to add compensation where a "
                "bank's due diligence failed. Nothing has been notified yet.")


class ToolInputError(ValueError):
    pass


# ---- input parsing -----------------------------------------------------------------------


def _dt(value, field: str) -> datetime:
    if not value:
        raise ToolInputError(f"{field} is required (ISO date or date-time, e.g. 2027-01-04 or 2027-01-04T11:02)")
    try:
        return datetime.fromisoformat(value) if "T" in value else datetime.fromisoformat(value + "T00:00")
    except (TypeError, ValueError):
        raise ToolInputError(f"{field} must be an ISO date or date-time, got {value!r}") from None


def _d(value, field: str) -> date | None:
    if value in (None, ""):
        return None
    return _dt(value, field).date()


def _amount(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ToolInputError(f"{field} must be a non-negative number of rupees")
    return int(round(value))


def _answers(raw: dict | None) -> Answers:
    raw = raw or {}
    known = Answers.__dataclass_fields__
    unknown = sorted(set(raw) - set(known))
    if unknown:
        raise ToolInputError(f"unknown answers: {', '.join(unknown)}; allowed: {', '.join(known)}")
    return Answers(**{k: bool(v) for k, v in raw.items()})


def _transactions(case: dict) -> list[dict]:
    txns = case.get("transactions") or []
    if not txns:
        raise ToolInputError("transactions must list at least one fraudulent transaction")
    out = []
    for i, t in enumerate(txns, 1):
        tid = t.get("id") or f"t{i}"
        out.append({
            "id": tid,
            "amount": _amount(t.get("amount"), f"transactions[{tid}].amount"),
            "txn_at": _dt(t.get("txn_at"), f"transactions[{tid}].txn_at"),
            "alert_received_date": _d(t.get("alert_received_date"), f"transactions[{tid}].alert_received_date"),
            "cross_border": bool(t.get("cross_border", False)),
        })
    return out


def _entity(case: dict) -> str:
    entity = case.get("entity", "CB")
    if entity not in rules.PREFIX:
        raise ToolInputError(f"entity must be one of {', '.join(rules.PREFIX)}")
    return entity


def _account_type(case: dict) -> str:
    acct = case.get("account_type", "SB")
    if acct not in rules.CAPS:
        raise ToolInputError(f"account_type must be one of {', '.join(rules.CAPS)}")
    return acct


def _safe(fn):
    def wrapper(case: dict) -> dict:
        try:
            return fn(case or {})
        except ToolInputError as e:
            return {"error": str(e)}
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _outcome(o: rules.Outcome) -> dict:
    return {k: v for k, v in asdict(o).items() if v not in (None, "")}


# ---- tools -------------------------------------------------------------------------------


@_safe
def classify_case(case: dict) -> dict:
    """Candidate liability outcome for every transaction under every candidate cause."""
    entity, acct = _entity(case), _account_type(case)
    causes = sorted(rules.candidate_causes(_answers(case.get("answers"))), key=lambda c: c.value)
    bank_at = _dt(case.get("bank_reported_at"), "bank_reported_at")
    results = []
    for t in _transactions(case):
        regime = rules.regime_for(t["txn_at"].date())
        per_cause = []
        for cause in causes:
            if regime == "NEW":
                o = rules.classify_new(t["txn_at"], bank_at, cause, entity)
            else:
                o = rules.classify_old(txn_at=t["txn_at"], bank_reported_at=bank_at,
                                       alert_received_date=t["alert_received_date"], cause=cause,
                                       account_type=acct, amount=t["amount"])
            per_cause.append({"cause": cause.value, **_outcome(o)})
        results.append({"id": t["id"], "amount": t["amount"], "regime": regime, "outcomes": per_cause})
    regimes = {r["regime"] for r in results}
    notes = [CAVEAT]
    if len(causes) > 1:
        notes.append("Several causes may apply. RBI does not say which takes priority, so all are shown.")
    if regimes == {"NEW", "OLD"}:
        notes.append("Mixed regimes: transactions before 1 Jan 2027 follow the 2017 rules, later ones the 2026 directions.")
    if "OLD" in regimes:
        notes.append("Old-regime working days use an approximate calendar (Sundays, 2nd and 4th Saturdays).")
    return {"causes": [c.value for c in causes], "transactions": results, "notes": notes,
            "rules_last_verified": RULES_VERIFIED}


@_safe
def compute_entitlement(case: dict) -> dict:
    """76T compensation for new-regime transactions, plus old-regime liability caps.

    Optional `later_recovery`: money credited after compensation was paid (76T(3) recalculation).
    """
    txns = _transactions(case)
    causes = rules.candidate_causes(_answers(case.get("answers")))
    new = [t for t in txns if rules.regime_for(t["txn_at"].date()) == "NEW"]
    old = [t for t in txns if t not in new]
    out: dict = {"rules_last_verified": RULES_VERIFIED, "notes": [CAVEAT]}

    if new:
        bank = _dt(case.get("bank_reported_at"), "bank_reported_at").date()
        ncrp = _d(case.get("ncrp_reported_at"), "ncrp_reported_at")
        if ncrp is None:
            raise ToolInputError("ncrp_reported_at is required: compensation needs a 1930 or NCRP report date")
        gross = sum(t["amount"] for t in new)
        cross = any(t["cross_border"] for t in new)
        comp = rules.compensation(
            gross_loss=gross,
            recoveries=_amount(case.get("recoveries_credited", 0), "recoveries_credited"),
            cause=Cause.CUSTOMER_NEGLIGENCE if Cause.CUSTOMER_NEGLIGENCE in causes else min(causes, key=lambda c: c.value),
            individual=bool(case.get("individual", True)),
            first_txn_date=min(t["txn_at"].date() for t in new),
            ncrp_report_date=ncrp,
            bank_report_date=bank,
            cross_border=cross,
            lifetime_used=bool(case.get("lifetime_compensation_used", False)),
        )
        block = {"gross_loss": gross, **asdict(comp), "reasons": list(comp.reasons), "citation": "76T"}
        if Cause.BANK_NEGLIGENCE in causes or Cause.THIRD_PARTY_BREACH in causes:
            block["also_consider"] = ("Bank negligence (76L) or a timely third-party breach report (76M) "
                                      "means zero liability and full reversal, which is better than compensation.")
        later = case.get("later_recovery")
        if later is not None and comp.amount:
            newly = _amount(later, "later_recovery")
            total = _amount(case.get("recoveries_credited", 0), "recoveries_credited") + newly
            r = rules.recalculate_after_recovery(gross_loss=gross, paid=comp, total_recovered=total,
                                                 newly_recovered=newly, cross_border=cross)
            block["after_later_recovery"] = {**asdict(r), "citation": "76T(3)"}
        out["new_regime"] = block
        out["notes"].append(PENDING_NOTE)

    if old:
        acct = _account_type(case)
        bank_at = _dt(case.get("bank_reported_at"), "bank_reported_at")
        rows = []
        for t in old:
            for cause in sorted(causes, key=lambda c: c.value):
                o = rules.classify_old(txn_at=t["txn_at"], bank_reported_at=bank_at,
                                       alert_received_date=t["alert_received_date"],
                                       cause=cause, account_type=acct, amount=t["amount"])
                rows.append({"id": t["id"], "amount": t["amount"], "cause": cause.value, **_outcome(o)})
        out["old_regime"] = {"liability": rows,
                             "note": "No compensation exists for frauds before 1 Jan 2027. "
                                     "A cap is the most the customer can be made to bear for that transaction."}
    return out


@_safe
def deadline_calendar(case: dict) -> dict:
    """Every date the user must act by, for each regime present. `as_of` sets the demo clock."""
    txns = _transactions(case)
    bank = _d(case.get("bank_reported_at"), "bank_reported_at")
    as_of = _d(case.get("as_of"), "as_of") or date.today()
    items: list[dict] = []

    def add(label: str, when: date | None, citation: str, kind: str = "deadline"):
        if when:
            items.append({"label": label, "date": when.isoformat(), "days_left": (when - as_of).days,
                          "kind": kind, "citation": citation})

    new = [t for t in txns if rules.regime_for(t["txn_at"].date()) == "NEW"]
    old = [t for t in txns if t not in new]
    if new:
        first = min(t["txn_at"].date() for t in new)
        add("Report to the bank and to 1930/NCRP (safe date)", first + timedelta(days=4), "76M, 76T(1)(b)")
        add("Outer limit for the 5-day window (counting rule is open)", first + timedelta(days=5),
            "76M, 76T(1)(b)", kind="outer_limit")
        if bank:
            d = rules.new_regime_deadlines(first, bank, any(t["cross_border"] for t in new))
            add("Bank must decide and reply", d.bank_decision_due, "76Q")
            add("You may approach the RBI Ombudsman from (or at once if rejected)", d.ombudsman_open_from,
                "RB-IOS 2026", kind="opens")
            add("File with the RBI Ombudsman by (safe date)", d.ombudsman_file_by_earliest, "RB-IOS 2026")
            add("Latest reading of the Ombudsman filing deadline", d.ombudsman_file_by_latest, "RB-IOS 2026",
                kind="outer_limit")
    for t in old:
        if bank:
            d = rules.old_regime_deadlines(t["alert_received_date"], bank)
            add(f"[{t['id']}] Report within 3 working days of the alert for zero liability",
                d.zero_liability_report_by, "2017 para 6(ii)")
            add(f"[{t['id']}] Bank's provisional (shadow) credit due", d.shadow_credit_due, "2017 para 9")
            add(f"[{t['id']}] Bank must resolve the complaint", d.resolution_due, "2017 para 10")
    if not bank:
        items.append({"label": "Report the fraud to your bank now; most deadlines start from that date",
                      "kind": "action", "citation": "76I"})
    items.sort(key=lambda i: i.get("date", ""))
    return {"as_of": as_of.isoformat(), "deadlines": items, "notes": [CAVEAT],
            "rules_last_verified": RULES_VERIFIED}


TOOLS = {f.__name__: f for f in (classify_case, compute_entitlement, deadline_calendar)}
