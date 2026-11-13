"""Generate synthetic SMS / UPI-receipt screenshots for a FICTIONAL bank, with ground truth.

No real bank names, logos or numbers. Every image is watermarked SYNTHETIC. Seeded, so reruns match.
Usage: python scripts/make_samples.py
"""
import json
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "samples"
LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEVA = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
DEVA_RE = re.compile(r"[ऀ-ॿ]+")


def indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def draw_line(d, xy, text, size, fill):
    """Draw mixed Latin/Devanagari text, switching fonts per run, on a shared baseline."""
    x, y = xy
    lf, df = ImageFont.truetype(LATIN, size), ImageFont.truetype(DEVA, size)
    pos = 0
    for m in list(DEVA_RE.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        if end > pos:
            d.text((x, y), text[pos:end], font=lf, fill=fill, anchor="ls")
            x += d.textlength(text[pos:end], font=lf)
        if m:
            d.text((x, y), m.group(), font=df, fill=fill, anchor="ls")
            x += d.textlength(m.group(), font=df)
            pos = m.end()


def render(lines, path, width=900, size=30, bg=(245, 245, 245), fg=(20, 20, 20), pad=40, gap=48):
    h = pad * 2 + gap * (len(lines) + 1)
    img = Image.new("RGB", (width, h), bg)
    d = ImageDraw.Draw(img)
    y = pad + gap
    for ln in lines:
        draw_line(d, (pad, y), ln, size, fg)
        y += gap
    draw_line(d, (pad, h - 14), "SYNTHETIC SAMPLE - NOT A REAL BANK", 18, (150, 150, 150))
    img.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2027)
    truth = {}
    months = ["Jan", "Feb", "Mar"]
    for i in range(15):
        amount = rng.choice([4999, 12500, 20000, 40000, 85000, 125000, 380000])
        utr = "".join(str(rng.randint(0, 9)) for _ in range(12))
        utr = "3" + utr[1:]
        day, mon, hh, mm = rng.randint(2, 28), rng.randint(1, 3), rng.randint(9, 21), rng.randint(0, 59)
        acct = f"{rng.randint(0, 9999):04d}"
        vpa = rng.choice(["ramesh.k", "kyc.update", "helpdesk88", "priya.s", "refund.cell"]) + "@okpay"
        date_dd = f"{day:02d}-{mon:02d}-27"
        kind = ["sms_en", "sms_en_otp", "sms_hi", "receipt", "statement"][i % 5]
        amt = indian(amount)
        if kind == "sms_en":
            lines = [f"SampleBank: Rs.{amt}.00 debited from A/c XX{acct}", f"on {date_dd} {hh:02d}:{mm:02d} to VPA {vpa}.",
                     f"UPI Ref {utr}. Not you? Call 1930 / bank."]
        elif kind == "sms_en_otp":
            lines = [f"SampleBank: Rs.{amt}.00 debited from A/c XX{acct}", f"on {date_dd} {hh:02d}:{mm:02d} to VPA {vpa}.",
                     f"UPI Ref {utr}.", f"482913 is your OTP. Do not share. CVV 731"]
        elif kind == "sms_hi":
            lines = [f"SampleBank: आपके खाते XX{acct} से Rs.{amt}.00 डेबिट हुए।", f"दिनांक {date_dd} {hh:02d}:{mm:02d}, प्राप्तकर्ता {vpa}",
                     f"UPI Ref {utr}"]
        elif kind == "receipt":
            lines = ["Payment successful", f"Rs.{amt}", f"Paid to {vpa}", f"UPI transaction ID {utr}",
                     f"{day} {months[mon-1]} 2027, {hh:02d}:{mm:02d}", f"Debited from SampleBank XX{acct}"]
        else:
            lines = ["Date        Narration                          Debit", f"{date_dd}  UPI/{utr}/{vpa}   {amt}.00",
                     f"Account XX{acct}  debited"]
        name = f"{i:02d}_{kind}.png"
        render(lines, OUT / name, width=1200 if kind == "statement" else 900)
        truth[name] = {"amount": amount, "utr": utr, "date": f"2027-{mon:02d}-{day:02d}", "account_last4": acct,
                       "counterparty": vpa, "has_secret": kind == "sms_en_otp"}
    (OUT / "truth.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False))
    print(f"wrote {len(truth)} samples to {OUT}")


main()
