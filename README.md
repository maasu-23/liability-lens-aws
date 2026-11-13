# Liability Lens

**What does your bank owe you after a fraud, under which RBI rule, and by when?**

Liability Lens is an AI case assistant for people in India who have lost money to electronic banking fraud, and for the family member helping them. It reads SMS and UPI screenshots into a transaction timeline, works out which RBI customer-liability rules apply, calculates what the bank may owe, lists every deadline, and drafts the paperwork. It drafts only. The person files everything themselves.

RBI's new customer-protection framework applies to transactions from 1 January 2027, while frauds before that date still run on the 2017 rules. Most guides online cite only the old ones, and Liability Lens applies the right regime to each transaction.

> **Call 1930 and your bank's 24x7 fraud line first.** Speed decides whether frozen money can be held. Liability Lens is for the days after.

## Design principle: the model talks, the code decides

All liability, money and date logic is deterministic Python in [`src/liability_lens/rules.py`](src/liability_lens/rules.py). A language model only interviews the user and writes drafts. It never decides liability, and no amount or deadline comes from it. Output is always a *candidate* classification: the bank classifies, and under RBI's rules the bank carries the burden of proof.

Where RBI's text is ambiguous, the code picks the reading that favours the victim and says so. The open items are listed in [`docs/rbi-rules-verification.md`](docs/rbi-rules-verification.md).

## Status

Early work. Implemented and tested:

- **Rules engine** (`rules.py`): regime selection per transaction date; classification under the 2017 circular and the 2026 directions (paras 76K to 76O and equivalents for each bank category); the 76T compensation (85% of net loss, up to ₹25,000) with the RBI, customer's-bank and beneficiary-bank split and recalculation after recoveries; deadline calendars for both regimes. The tests reproduce RBI's three worked illustrations to the rupee.
- **Case tools** (`tools.py`): `classify_case`, `compute_entitlement` and `deadline_calendar` turn case facts (JSON) into cited outcomes, rupee amounts and dated deadlines, with every number coming from the rules engine.
- **Screenshot extraction** (`extract.py`): Tesseract OCR in English and Hindi, redaction of OTPs, PINs, CVVs, Aadhaar and card numbers before anything else sees the text (including secrets typed into chat), and field parsing (amount, UTR, date, UPI ID, account last four). Nothing is guessed; missing fields stay empty. On the 15 synthetic test images it reads every field correctly, but those images are clean and the code was tuned on them, so expect lower accuracy on real screenshots.
- **Agent on AWS** (`agentcore/`, `app/`): a Strands agent on Amazon Bedrock AgentCore Runtime using Claude Sonnet 4.6. It interviews the user, calls the case tools through an AgentCore Gateway backed by a Lambda, and explains the results. It runs deployed in us-east-1.
- **Screenshot reading on AWS** (`infra/extract/`): a container-image Lambda running Tesseract reads screenshots uploaded to an encrypted S3 bucket (objects expire after one day) and returns the confirmed-by-the-user fields; the agent reaches it through the same Gateway.

Not built yet: document drafting, reminders, and the web interface.

## Safety and legal limits

- Independent, free tool. It is **not** RBI, the Government of India, the police, the National Cybercrime Reporting Portal (NCRP) or any bank.
- Legal information, not legal advice. Every liability statement cites the paragraph it rests on, with the date the rules were last verified.
- It never accepts or stores OTPs, PINs, CVVs, passwords or full card numbers, and it never logs in to any portal or sends anything on the user's behalf.
- It makes no promise or estimate of recovering money. "Saved" figures published by authorities mean frozen funds, not returned ones.
- Anyone who charges a fee to get your money back is a scammer.
- The test data is synthetic. The sample images use a fictional bank and are watermarked.

## Setup

Requires Python 3.12 or newer and Tesseract with English and Hindi data.

```bash
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-osd
python -m venv .venv
.venv/bin/pip install pytest pillow
.venv/bin/python -m pytest -q
```

Language order matters for OCR: `eng+hin` is correct, and `hin+eng` silently drops the digit "1".

Regenerate the synthetic sample images and score the extraction against their ground truth:

```bash
.venv/bin/python scripts/make_samples.py
.venv/bin/python scripts/score_ocr.py -v
```

`make_samples.py` also needs the DejaVu Sans and Noto Sans Devanagari fonts.

## Layout

| Path | Contents |
|---|---|
| `src/liability_lens/rules.py` | RBI rules as code |
| `src/liability_lens/tools.py` | JSON tools over the rules engine |
| `src/liability_lens/extract.py` | OCR, redaction and field parsing |
| `app/agent/` | Strands agent (AgentCore Runtime) |
| `app/tools/` | Gateway Lambda that dispatches the case tools |
| `agentcore/` | AgentCore project config and CDK app |
| `infra/extract/` | Tesseract Lambda image, upload bucket stack and tool schema |
| `tests/` | Unit tests and synthetic fixtures |
| `scripts/` | Sample generator, OCR scoring, deploy and commit-check scripts |
| `docs/rbi-rules-verification.md` | Sources, paragraph citations and open items |

## Related work

Several 2026 prototypes already turn screenshots into complaint drafts, including SAFAR, CasePilot and First Hour. As far as research found, none applies the 2027 framework or calculates a rupee entitlement. Liability Lens focuses on that part and treats extraction and drafting as supporting steps.
