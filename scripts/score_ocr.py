"""Score Tesseract extraction against ground truth for the synthetic samples."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from liability_lens.extract import ocr, redact, extract_best

D = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "samples"
truth = json.loads((D / "truth.json").read_text())
fields = ["amount", "utr", "date", "account_last4", "counterparty"]
tot = {f: 0 for f in fields}; verbose = "-v" in sys.argv
by_kind = {}
for name, t in truth.items():
    x, clean = extract_best(str(D / name)); kinds = redact(ocr(str(D / name)))[1]
    got = {"amount": x.amount, "utr": x.utr, "date": x.txn_date.isoformat() if x.txn_date else None,
           "account_last4": x.account_last4, "counterparty": x.counterparty}
    ok = {f: got[f] == t[f] for f in fields}
    for f in fields: tot[f] += ok[f]
    leaked = t["has_secret"] and any(s in clean for s in ("482913", "CVV 731"))
    k = name.split("_", 1)[1][:-4]; by_kind.setdefault(k, []).append(sum(ok.values()))
    flag = "" if all(ok.values()) else "  <-- " + ",".join(f for f in fields if not ok[f])
    print(f"{name:22} {sum(ok.values())}/5  redacted={kinds}{'  SECRET LEAK' if leaked else ''}{flag}")
    if verbose and not all(ok.values()):
        print("    OCR:", clean.replace("\n", " | ")[:260]); print("    GOT:", got)
n = len(truth)
print("\nper field:", {f: f"{tot[f]}/{n}" for f in fields})
print("per kind (avg fields correct of 5):", {k: round(sum(v)/len(v), 1) for k, v in by_kind.items()})
