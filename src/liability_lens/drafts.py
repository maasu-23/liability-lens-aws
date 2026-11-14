"""Draft documents from case facts: a bank complaint, an NCRP narrative and an RBI Ombudsman complaint.

Fixed templates, no model. Every amount, paragraph and date comes from the tool layer (tools.py,
which calls rules.py), so a draft can never state a figure the rules engine did not produce. The
user's own words appear only in the incident summary, which is redacted first.

Contact details are left as bracketed blanks for the user to fill in by hand, so phone numbers,
addresses and emails never pass through the system. The user reviews, signs and files; nothing here
sends anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from liability_lens import tools
from liability_lens.extract import redact_message
from liability_lens.tools import ToolInputError

KINDS = ("bank_notice", "ncrp_narrative", "ombudsman_complaint")
MAX_SUMMARY = 1500
DISCLAIMER = ("Prepared with Liability Lens, a free self-help tool. Legal information, not legal advice. "
              "Check every fact and date before you sign; you file this yourself.")

VERDICTS = {
    "ZERO_LIABILITY_REVERSAL": "zero customer liability, with the amount reversed",
    "ZERO_LIABILITY_REVERSAL_BORDERLINE": "zero customer liability if the report counts as within 5 calendar days",
    "ZERO_LIABILITY": "zero customer liability",
    "CAPPED_LIABILITY": "customer liability capped",
    "BANK_BEARS": "the bank bears the loss, as it occurred after I reported",
    "LIABILITY_NOT_ESTABLISHED_BY_BANK": "no customer liability unless the bank establishes it",
    "CANNOT_COMPUTE_DAY_ZERO": "the bank must produce its timestamped alert record",
}
FAVOURABLE = {"ZERO_LIABILITY_REVERSAL", "ZERO_LIABILITY_REVERSAL_BORDERLINE", "ZERO_LIABILITY",
              "CAPPED_LIABILITY", "BANK_BEARS", "LIABILITY_NOT_ESTABLISHED_BY_BANK", "CANNOT_COMPUTE_DAY_ZERO"}
BANK_TIMELINES = {
    "76Q": "Please decide and reply in writing by {} (76Q).",
    "2017 para 9": "Please give me the provisional (shadow) credit by {} (2017 para 9).",
    "2017 para 10": "Please resolve this complaint by {} (2017 para 10).",
}
UTR_RE = re.compile(r"^[A-Za-z0-9]{6,22}$")
LAST4_RE = re.compile(r"^\d{4}$")


@dataclass
class Document:
    kind: str
    title: str
    blocks: list[tuple] = field(default_factory=list)

    def add(self, *block) -> None:
        self.blocks.append(block)

    def text(self) -> str:
        """Plain-text rendering, used by tests and as the source for copy-paste."""
        out = []
        for kind, *rest in self.blocks:
            if kind == "table":
                headers, rows = rest
                out.append(" | ".join(headers))
                out += [" | ".join(r) for r in rows]
            elif kind == "list":
                out += [f"{i}. {item}" for i, item in enumerate(rest[0], 1)]
            elif kind == "lines":
                out += rest[0]
            else:
                out.append(rest[0])
            out.append("")
        return "\n".join(out).strip() + "\n"


# ---- formatting ---------------------------------------------------------------------------


def rupees(n: int) -> str:
    """Indian digit grouping: 125000 -> Rs 1,25,000."""
    s = str(int(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        s = f"{head},{tail}"
    return f"Rs {s}"


def day(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def moment(dt: datetime) -> str:
    return day(dt.date()) if (dt.hour, dt.minute) == (0, 0) else f"{day(dt.date())}, {dt:%H:%M}"


def _blank(label: str, blanks: list[str]) -> str:
    if label not in blanks:
        blanks.append(label)
    return f"[{label}]"


# ---- input -------------------------------------------------------------------------------


def _parties(case: dict) -> dict:
    last4 = case.get("account_last4")
    if last4 not in (None, "") and not LAST4_RE.match(str(last4)):
        raise ToolInputError("account_last4 must be exactly the last 4 digits, never the full number")
    summary = case.get("incident_summary") or ""
    if not isinstance(summary, str) or len(summary) > MAX_SUMMARY:
        raise ToolInputError(f"incident_summary must be text of at most {MAX_SUMMARY} characters")
    summary, removed = redact_message(summary.strip())
    reply = case.get("bank_reply", "none")
    if reply not in ("none", "rejected", "partial", "unsatisfactory"):
        raise ToolInputError("bank_reply must be none, rejected, partial or unsatisfactory")
    return {
        "name": _short(case.get("complainant_name"), 80),
        "bank": _short(case.get("bank_name"), 80),
        "last4": str(last4) if last4 else None,
        "complaint_ref": _short(case.get("bank_complaint_ref"), 40),
        "ncrp_ack": _short(case.get("ncrp_ack"), 40),
        "summary": summary,
        "secrets_removed": bool(removed),
        "reply": reply,
        "reply_date": tools._d(case.get("bank_reply_date"), "bank_reply_date"),
        "as_of": tools._d(case.get("as_of"), "as_of") or date.today(),
    }


def _short(value, limit: int) -> str | None:
    if value in (None, ""):
        return None
    value = " ".join(str(value).split())
    if len(value) > limit:
        raise ToolInputError(f"a text field is longer than {limit} characters: {value[:20]}...")
    return value


def _rows(case: dict, blanks: list[str]) -> list[list[str]]:
    rows = []
    for i, t in enumerate(case.get("transactions") or [], 1):
        utr = t.get("utr")
        if utr and not UTR_RE.match(str(utr)):
            raise ToolInputError(f"transactions[{t.get('id') or i}].utr must be 6-22 letters or digits")
        rows.append([
            t.get("id") or f"t{i}",
            moment(tools._dt(t.get("txn_at"), "txn_at")),
            rupees(tools._amount(t.get("amount"), "amount")),
            _short(t.get("mode"), 20) or "-",
            str(utr) if utr else _blank("UTR / reference number of each debit", blanks),
            _short(t.get("beneficiary"), 60) or "-",
        ])
    return rows


# ---- documents ---------------------------------------------------------------------------


def _who(p: dict, blanks: list[str]) -> tuple[str, str, str]:
    name = p["name"] or _blank("Your full name", blanks)
    bank = p["bank"] or _blank("Bank name", blanks)
    acct = f"account ending {p['last4']}" if p["last4"] else _blank("account ending (last 4 digits)", blanks)
    return name, bank, acct


def _summary(p: dict, blanks: list[str]) -> str:
    return p["summary"] or _blank("In your own words: who contacted you, how, and what happened", blanks)


def _reported(case: dict, p: dict) -> list[str]:
    out = []
    bank_at = tools._dt(case.get("bank_reported_at"), "bank_reported_at")
    ref = f" (complaint reference {p['complaint_ref']})" if p["complaint_ref"] else ""
    out.append(f"I reported this to the bank on {moment(bank_at)}{ref}.")
    if case.get("ncrp_reported_at"):
        ack = f" (acknowledgement {p['ncrp_ack']})" if p["ncrp_ack"] else ""
        ncrp_at = tools._dt(case["ncrp_reported_at"], "ncrp_reported_at")
        out.append(f"I reported it on the 1930 helpline / National Cybercrime Reporting Portal on {moment(ncrp_at)}{ack}.")
    return out


def _grounds(classified: dict) -> list[str]:
    """Outcomes that help the customer, one line per paragraph.

    Outcomes that put liability on the customer (76N, 2017 para 7(i)) are left out: the letter is the
    customer's case, and the bank must prove those itself (76K). 76N is handled by the compensation line.
    """
    seen, out = set(), []
    for t in classified["transactions"]:
        for o in t["outcomes"]:
            if o["verdict"] not in FAVOURABLE or (o["citation"], o["verdict"]) in seen:
                continue
            seen.add((o["citation"], o["verdict"]))
            cap = f" of at most {rupees(o['cap'])}" if o.get("cap") else ""
            out.append(f"Under para {o['citation']}, the outcome should be {VERDICTS[o['verdict']]}{cap}.")
    return out


def _comp_line(ent: dict) -> str | None:
    block = ent.get("new_regime")
    if not block or block["status"] == "NOT_ELIGIBLE":
        return None
    line = (f"If the bank treats this as customer negligence under para 76N, I request compensation under "
            f"para 76T: on my figures {rupees(block['amount'])} (85% of my net loss of {rupees(block['net_loss'])}, "
            f"up to Rs 25,000). Please give me the Annex II(1) application form (76T(4)).")
    if block["status"] == "BORDERLINE":
        line += " I note that one report was made on day 5, and ask the bank to count it as within the window."
    return line


def bank_notice(case, p, classified, ent, cal, blanks) -> Document:
    name, bank, acct = _who(p, blanks)
    doc = Document("bank_notice", "Complaint: unauthorised electronic banking transactions")
    doc.add("lines", [f"Date: {day(p['as_of'])}", "To: The Branch Manager / Principal Nodal Officer", bank])
    doc.add("h", f"Subject: Fraudulent electronic banking transactions in my {acct}: complaint and requests "
                 f"under RBI's customer-protection directions")
    doc.add("p", f"I, {name}, report that the following electronic banking transactions in my {acct} were "
                 f"fraudulent.")
    doc.add("table", ["Id", "Date and time", "Amount", "Mode", "UTR / reference", "Beneficiary"], _rows(case, blanks))
    doc.add("p", " ".join(_reported(case, p)))
    doc.add("h", "What happened")
    doc.add("p", _summary(p, blanks))
    doc.add("h", "My requests")
    new_only = {t["regime"] for t in classified["transactions"]} == {"NEW"}
    asks = [
        "Register this as a complaint and give me the complaint number and the date and time of receipt"
        + (" (76I)." if new_only else "."),
        "The bank carries the burden of proving any customer liability (76K). Please share the basis of your "
        "classification of this complaint.",
    ]
    asks += _grounds(classified)
    for item in cal["deadlines"]:
        template = BANK_TIMELINES.get(item.get("citation"))
        line = template and template.format(day(date.fromisoformat(item["date"])))
        if line and line not in asks:
            asks.append(line)
    comp = _comp_line(ent)
    if comp:
        asks.append(comp)
    asks.append("If you reject any part of this complaint, give me the reasons in writing (76S).")
    doc.add("list", asks)
    doc.add("p", "If I do not receive a satisfactory reply in time, I may approach the RBI Ombudsman under the "
                 "Reserve Bank - Integrated Ombudsman Scheme, 2026.")
    doc.add("lines", ["Yours faithfully,", "", name, _blank("Phone", blanks), _blank("Email", blanks),
                      _blank("Signature", blanks)])
    doc.add("note", DISCLAIMER)
    return doc


def ncrp_narrative(case, p, classified, ent, cal, blanks) -> Document:
    name, bank, acct = _who(p, blanks)
    doc = Document("ncrp_narrative", "Incident description for the National Cybercrime Reporting Portal")
    doc.add("note", "Copy this into the incident details on cybercrime.gov.in, or read it out on 1930. "
                    "Add the beneficiary details exactly as they appear in your bank messages.")
    doc.add("h", "Incident")
    doc.add("p", _summary(p, blanks))
    doc.add("h", "Money lost")
    doc.add("p", f"The following amounts were debited from my {acct} with {bank}:")
    doc.add("table", ["Id", "Date and time", "Amount", "Mode", "UTR / reference", "Beneficiary"], _rows(case, blanks))
    total = sum(tools._amount(t.get("amount"), "amount") for t in case.get("transactions") or [])
    doc.add("p", f"Total debited: {rupees(total)}.")
    doc.add("h", "Reported")
    doc.add("p", " ".join(_reported(case, p)))
    doc.add("h", "Request")
    doc.add("p", "Please trace the beneficiary accounts and have the amounts put on hold, and share the "
                 "complaint acknowledgement number with me.")
    doc.add("lines", [name])
    doc.add("note", DISCLAIMER)
    return doc


def ombudsman_complaint(case, p, classified, ent, cal, blanks) -> Document:
    name, bank, acct = _who(p, blanks)
    doc = Document("ombudsman_complaint", "Complaint to the RBI Ombudsman (RB-IOS 2026)")
    doc.add("note", "File at cms.rbi.org.in (help line 14448). You must have complained to the bank first.")
    windows = [i for i in cal["deadlines"] if i.get("citation") == "RB-IOS 2026"]
    if windows:
        doc.add("list", [f"{i['label']}: {day(date.fromisoformat(i['date']))}" for i in windows])
    else:
        doc.add("p", "You may file if the bank rejects the complaint, replies unsatisfactorily, or does not reply "
                     "within 30 days; file within 90 days of that.")
    doc.add("h", "Complainant and bank")
    doc.add("lines", [f"Complainant: {name}", f"Bank: {bank}", f"Account: {acct[0].upper()}{acct[1:]}",
                      f"Bank complaint reference: {p['complaint_ref'] or _blank('Bank complaint number', blanks)}"])
    doc.add("h", "Complaint to the bank and its reply")
    reply = {"none": "The bank has not given a final reply.",
             "rejected": "The bank rejected my complaint",
             "partial": "The bank resolved my complaint only in part",
             "unsatisfactory": "The bank's reply does not resolve my complaint"}[p["reply"]]
    if p["reply"] != "none":
        reply += f" on {day(p['reply_date'])}." if p["reply_date"] else f" on {_blank('date of the reply', blanks)}."
    doc.add("p", " ".join(_reported(case, p)) + " " + reply)
    doc.add("h", "Facts")
    doc.add("p", _summary(p, blanks))
    doc.add("table", ["Id", "Date and time", "Amount", "Mode", "UTR / reference", "Beneficiary"], _rows(case, blanks))
    doc.add("h", "Grounds")
    doc.add("list", _grounds(classified) + ["The bank must prove any customer liability (76K) and give reasons "
                                            "for a rejection (76S)."])
    doc.add("h", "Relief sought")
    total = sum(tools._amount(t.get("amount"), "amount") for t in case.get("transactions") or [])
    relief = [f"Reversal of {rupees(total)}, value-dated to the transaction dates, to the extent the bank cannot "
              f"establish my liability."]
    comp = (ent.get("new_regime") or {})
    if comp.get("status") in ("ELIGIBLE", "BORDERLINE"):
        relief.append(f"Failing that, compensation of {rupees(comp['amount'])} under para 76T.")
    doc.add("list", relief)
    doc.add("h", "Declaration")
    doc.add("p", "The same complaint is not pending before, and has not been decided by, any court, tribunal, "
                 "arbitrator or other forum. The facts above are true to the best of my knowledge.")
    doc.add("lines", [name, f"Date: {day(p['as_of'])}", _blank("Signature", blanks)])
    doc.add("note", DISCLAIMER)
    return doc


BUILDERS = {"bank_notice": bank_notice, "ncrp_narrative": ncrp_narrative, "ombudsman_complaint": ombudsman_complaint}


def build(case: dict) -> tuple[list[Document], list[str], dict]:
    """Return the requested documents, the blanks the user must fill in, and extra facts for the reply.

    Raises ToolInputError with a message the model can turn into a question.
    """
    kinds = case.get("documents") or list(KINDS)
    if not isinstance(kinds, list) or set(kinds) - set(KINDS):
        raise ToolInputError(f"documents must be a list drawn from {', '.join(KINDS)}")
    classified = tools.classify_case(case)
    if "error" in classified:
        raise ToolInputError(classified["error"])
    ent = tools.compute_entitlement(case)
    if "error" in ent:  # compensation needs an NCRP date; the drafts still work without it
        ent = {}
    cal = tools.deadline_calendar({**case, "as_of": case.get("as_of")})
    p = _parties(case)
    blanks: list[str] = []
    docs = [BUILDERS[k](case, p, classified, ent, cal, blanks) for k in KINDS if k in kinds]
    key_dates = [{k: i[k] for k in ("label", "date", "citation")} for i in cal["deadlines"] if "date" in i]
    return docs, blanks, {"secrets_removed": p["secrets_removed"], "key_dates": key_dates}
