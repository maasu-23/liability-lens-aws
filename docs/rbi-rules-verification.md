# RBI customer-liability rules: verification notes

Sources and reasoning behind the rules engine in `src/liability_lens/rules.py`. Rules last verified against rbi.org.in and pib.gov.in on 13 November 2026, then re-checked for changes since 14 July 2026 on the same day (no change found; see the open items). Re-check again after the Supreme Court hearing expected on 23 November 2026 and after 30 November 2026. This is legal information, not legal advice. Re-check the open items below before relying on any date.

**Summary.** Under RBI's new framework (seven directions dated 24 June 2026, for electronic banking transactions on or after 1 January 2027), **zero liability is narrow**. It covers bank negligence at any time, and a "third-party breach" (a failure by a telecom operator, UPI app or payment gateway, not by the victim) if reported within **5 calendar days of the transaction**. The **₹25,000 compensation applies only to customer-negligence cases**, for gross losses up to ₹50,000, reported to both NCRP/1930 and the bank within 5 days, once in a lifetime, and only for frauds in roughly the first year. **Shadow reversal in 5 days is mandated only for credit cards.** The 2021 Ombudsman scheme was replaced on 1 July 2026 by one with a 90-day filing window. Transactions before 2027 still fall under the 2017 rules, where the clock is three *working* days counted from the bank's alert. The "saved" fraud money that ministers cite means frozen (lien-marked), not returned.

Labels used throughout: **PRIMARY** means read in full on rbi.org.in or pib.gov.in. **PRIMARY (summary)** means an official page read through a summarising fetch, so the wording is paraphrased. **SECONDARY** means law-firm, news or guide coverage. **INFERENCE** means the author's own reading. The code blocks below are illustrative pseudocode; the implementation and its tests are in `src/liability_lens/rules.py` and `tests/test_rules.py`.


## The 2027 rulebook: zero liability is narrow, compensation is small and short-lived

### Seven directions, one text, keyed by paragraph suffix

RBI press release 2026-2027/533 of 24 June 2026 announced seven final amendment directions, RBI/2026-27/167 to /173. One applies to each bank category: commercial, small finance, payments, local area, regional rural, urban co-operative and rural co-operative banks. All apply to electronic banking transactions (EBTs) "undertaken by customers … on or after January 1, 2027" (PRIMARY: [RBI PR prid=63011](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=63011); [Commercial Banks direction, Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543)). Each deletes the old "Limiting Liability" section and inserts "Customer Protection in Fraudulent Electronic Banking Transactions". The operative paragraphs carry the **same letter suffixes A–V in every direction**: 76A–76V for commercial and small finance banks, 33A–V for payments banks, 16A–V for local area banks, 128A–V for regional rural banks, 65.1A–V for urban co-operatives and 70A–V for rural co-operatives (PRIMARY, checked by text match across [Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543) to [Id=13549](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13549)). The code can therefore store rules once and cite them as `prefix[entity] + suffix`.

Two traps apply. First, definition numbers differ: the regional rural bank direction swaps 4(20B) and 4(20C) relative to commercial banks. Second, the payments bank text has no credit-card shadow-reversal sentence, because payments banks cannot issue credit cards. The draft of 6 March 2026 differed materially. It had a 1 July 2026 start, a 30-day resolution period, no credit-card shadow reversal, and an impersonation/authorised-push-payment category that the final text dropped (SECONDARY: [TaxGuru draft reproduction](https://taxguru.in/rbi/revised-draft-rbi-commercial-banks-responsible-business-conduct-amendment-directions-2026.html)). Blog posts written from the draft are wrong on all four points. The framework binds **banks only**. Non-bank wallets (PPIs) and NBFC card issuers are outside it.

### What counts as a "fraudulent EBT", and who is liable

Para 4(15A) defines a fraudulent EBT as one of three things. It may be (i) executed by a third party using credentials obtained from the customer by fraud. It may be (ii) executed by the customer "by granting approval under coercion or duress from the third-party". Or it may be (iii) an unauthorised EBT under 4(26B), which includes bank negligence and third-party breach (PRIMARY, [Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543)).

**Pure deception is not expressly covered.** That means an investment or romance scam, or a fake payee, with no credential theft and no threat. Treat it as "coverage uncertain, manual review" (INFERENCE). Coercion is in the definition, and the ELP law firm reads it as reaching digital-arrest scams (SECONDARY: [ELP note](https://elplaw.in/wp-content/uploads/2026/06/RBI-Tightens-Customer-Protection-Framework-for-Fraudulent-Electronic-Banking-Transactions.pdf)). But RBI defines neither "coercion" nor "duress" and never mentions digital arrest. More importantly, **being a fraudulent EBT does not mean zero liability**. Coerced and credential-phished transactions are, by definition, neither bank negligence nor third-party breach. They most likely land in customer negligence, because 4(20C)(i) covers handing credentials to another person "whether intentionally or otherwise". That routes them to the compensation mechanism, not to reversal (INFERENCE).

The liability limbs, all PRIMARY from [Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543), are short:

- **76K:** the bank bears the burden of proving customer liability and must classify every complaint.
- **76L:** bank negligence means zero liability and reversal, whether or not the customer reports. Under **4(20B), bank negligence includes not sending mandatory alerts**, not providing 24x7 reporting channels, not acting diligently on a notification, and system breaches or internal fraud.
- **76M:** third-party breach means zero liability and reversal if the customer reports "within five calendar days from the date of its occurrence". After that, liability follows the bank's own policy.
- **76N:** customer negligence means the customer bears the loss until reporting, less any 76T compensation.
- **76O:** losses after reporting fall on the bank.
- **76P:** the bank may waive liability.
- **76S:** a rejection must state reasons.

The old ₹5,000/₹10,000/₹25,000 caps are gone. **76D** makes instant SMS alerts mandatory for every EBT above ₹500, and 76E requires email alerts wherever an address is registered. Combine 76D with 4(20B)(ii) and 76L, and one interview question becomes a powerful check: *"Did you get an SMS for every debit above ₹500?"* A "no" points to bank negligence and zero liability, regardless of how late the victim reported.

### Code-ready decision table (new regime)

```python
NEW_START = date(2027, 1, 1)
PREFIX = {"CB": "76", "SFB": "76", "PB": "33", "LAB": "16", "RRB": "128", "UCB": "65.1", "RCB": "70"}

def candidate_causes(answers):           # model interviews; code maps answers -> limbs (4(20B), 4(26.1A), 4(20C))
    c = set()
    if answers.missing_sms_alert_over_500 or answers.bank_ignored_notification or answers.bank_system_breach:
        c.add("BANK_NEGLIGENCE")          # 4(20B)(ii)/(iv)/(v)
    if answers.sim_swap_or_telecom_fault or answers.tpap_pa_pg_breach:
        c.add("THIRD_PARTY_BREACH")       # 4(26.1A) names TPAP, PA, PG, telecom
    if answers.shared_credentials or answers.ignored_specific_bank_warning or answers.installed_malicious_app \
       or answers.coerced_approval:       # coercion = fraudulent EBT 4(15A)(ii); limb most likely 76N (INFERENCE)
        c.add("CUSTOMER_NEGLIGENCE")
    if answers.pure_deception_no_credentials_no_coercion:
        c.add("COVERAGE_UNCERTAIN")       # draft APP category dropped from final 4(15A)
    return c or {"UNCLASSIFIED"}

def classify_new(txn, case, cause):
    p = PREFIX[case.entity]
    if txn.dt > case.bank_report_dt:      return ("BANK_BEARS", p + "O")
    if cause == "BANK_NEGLIGENCE":        return ("ZERO_LIABILITY_REVERSAL", p + "L")   # no reporting condition
    if cause == "THIRD_PARTY_BREACH":
        d = (case.bank_report_date - txn.date).days                                   # calendar days, per txn
        if d <= 4:  return ("ZERO_LIABILITY_REVERSAL", p + "M")
        if d == 5:  return ("ZERO_LIABILITY_REVERSAL_BORDERLINE", p + "M")             # day-0 vs day-1 open item
        return ("PER_BANK_POLICY", p + "M")
    if cause == "CUSTOMER_NEGLIGENCE":    return ("CUSTOMER_LIABLE_UNTIL_REPORT_LESS_COMP", p + "N")
    return ("LIABILITY_NOT_ESTABLISHED_BY_BANK", p + "K")                              # burden stays on bank
# Always attach: bank may waive (P); rejection needs reasons (S); bank, not app, makes the classification.
```

When several limbs are candidates, show all of them with what the bank would have to prove. RBI does not say whether bank negligence overrides customer negligence (open item). The output is always a *candidate* classification. The bank classifies, and the app's job is to make the bank show its work.

### Compensation: 85% of net loss, capped at ₹25,000, customer-negligence only

**76T(1)** (PRIMARY, [Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543)) applies to a bona fide victim, defined as "an individual person, including a sole proprietor". The victim must have a complaint with **gross loss up to ₹50,000** from EBTs "covered under 76N". The award is **85% of net loss or ₹25,000, whichever is less, once in a lifetime**. Net loss is gross loss minus recoveries, whether made before or after payment. Two conditions apply: the bank's internal process accepts the loss as bona fide, and the victim reported on **NCRP or 1930 *and* to the bank, both within five calendar days of occurrence**. Joint holders get one claim between them. 76T(2) splits the funding.

| Loss band | RBI | Customer's bank | Beneficiary bank |
|---|---|---|---|
| Domestic, loss < ₹29,412 | 65% of loss | 10% | 10% |
| Domestic, loss ₹29,412–₹50,000 | ₹19,118 | ₹2,941 | ₹2,941 |
| Cross-border, loss < ₹29,412 | 65% | 20% | — |
| Cross-border, ₹29,412–₹50,000 | ₹19,118 | ₹5,882 | — |

Other operative rules from the same paragraphs:

- The bank hands over the Annex II(1) form once satisfied the claim is bona fide (76T(4)), and **pays within 5 calendar days of receiving the application** (76T(5)).
- Recoveries after payment trigger a recalculation (76T(3)).
- **76U sunsets the mechanism** for frauds "occurring up to one year from the effective date".
- Annex II(1) mentions a credit card number, so card frauds qualify.

RBI's three worked illustrations, each with a ₹40,000 gross loss, are perfect golden tests:

1. ₹15,000 recovered first, giving ₹21,250 (RBI ₹16,250, each bank ₹2,500).
2. ₹25,000 paid, then the full ₹40,000 recovered: the customer gets ₹15,000, RBI ₹19,118 and each bank ₹2,941.
3. ₹25,000 paid, then ₹15,000 recovered: the customer gets an extra ₹11,250, RBI is refunded ₹2,868 and each bank ₹441.

```python
def compensation(case, txns, as_of):
    gross = sum(t.amount for t in txns if t.regime == "NEW")           # INFERENCE: mixed-regime complaints open
    eligible = (case.customer_type in {"INDIVIDUAL", "SOLE_PROPRIETOR"}
        and case.cause == "CUSTOMER_NEGLIGENCE" and gross <= 50_000
        and within_5_days(case.ncrp_or_1930_date, case.first_txn_date)
        and within_5_days(case.bank_report_date, case.first_txn_date)
        and not case.lifetime_comp_used                                  # self-declared on Annex II(1); no registry
        and NEW_START <= case.first_txn_date <= SUNSET)                  # SUNSET = 2027-12-31 (conservative; open)
    net = max(0, gross - case.recoveries_credited)                       # credited, not merely lien-marked (open)
    comp = min(round(0.85 * net), 25_000) if eligible else 0
    if net < 29_412: split = dict(rbi=.65*net, own=(.20 if case.cross_border else .10)*net,
                                  ben=0 if case.cross_border else .10*net)  # split keyed on NET (Illustration 1)
    else:            split = dict(rbi=19_118, own=5_882 if case.cross_border else 2_941,
                                  ben=0 if case.cross_border else 2_941)
    return comp, split, "bank decides bona fide status (76T(1)(a)); a rejection needs reasons (76S)"

def after_recovery(old_comp, gross, R_total, R_new):                    # Illustration 3
    new_comp = min(round(0.85 * max(0, gross - R_total)), 25_000)
    return R_new + new_comp - old_comp                                   # extra paid to the customer
```

### Timelines and channels the agent should track

Under **76Q** the bank must examine the complaint, establish liability and respond within its policy timeline. That timeline may not exceed **45 calendar days from receipt for domestic fraud, or 60 days for cross-border**. A zero-liability response must include reversal details, and a 76N response must describe compensation where the customer is eligible. **76R** value-dates every reversal to the transaction date, so the customer loses no interest. Shadow reversal (a provisional credit) applies **only to fraud on a credit card**, within **5 calendar days of the customer's notification**. No separate reversal deadline exists for accounts or UPI. Reversal details belong in the 45-day response (INFERENCE).

Under **76I** every report must be registered as a complaint, with an **immediate acknowledgement** giving the complaint number and the receipt date and time. Under **76G**, banks must run 24x7 reporting channels, put a reply-to-object number in each alert SMS, and place a home-page reporting link. Under **76J**, the bank must tell the customer to file on NCRP or call 1930. **No FIR is required** for zero liability or compensation (all PRIMARY, [Id=13543](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13543)). The 76I timestamp is therefore the anchor for both the 45-day and the credit-card 5-day clocks. The app should capture the bank's complaint number and timestamp as first-class fields.

## Today's frauds still run on the 2017 working-day clock

Every transaction before 1 January 2027 remains under the 6 July 2017 circular, DBR.No.Leg.BC.78/09.07.005/2017-18 ([Id=11040](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11040&Mode=0)). It is now consolidated almost word for word as paras 64–76 of the Commercial Banks Responsible Business Conduct (RBC) Directions, 2025, still present "as on October 1, 2026" ([MD id=13140](https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=13140)). The amendment deletes those paragraphs only for EBTs from 2027. The 2025 Directions' savings clause (paras 464–465) preserves rights already accrued (PRIMARY). A fraud on 31 December 2026 that is reported in January 2027 therefore stays under the old rules (INFERENCE from the transaction-date trigger, which RBI does not state as a carve-out). Until 31 December 2026, the old regime is the one that matters to real victims, and a tool that only knows the 2027 rules would be wrong for them.

The old rules differ on almost every parameter, and **the clock starts at a different event**. They count working days from *receipt of the bank's communication* (the alert), not calendar days from the transaction. The rules are:

- **Zero liability** for bank fault, regardless of reporting (para 6(i)), or for third-party breach notified within **3 working days** (para 6(ii)).
- **Capped liability** for notification within **4–7 working days**, per transaction, at the lower of the transaction value and Table 1: ₹5,000 for basic savings (BSBD) accounts; ₹10,000 for other savings accounts, PPIs and gift cards, MSME current accounts, individual current accounts up to ₹25 lakh, and credit cards with limits up to ₹5 lakh; ₹25,000 for other current/CC/OD accounts and cards above ₹5 lakh.
- **Bank policy** beyond 7 working days.
- **Customer negligence:** the customer bears the full loss until reporting (para 7(i)).
- Working days are counted "as per the working schedule of the home branch … excluding the date of receiving the communication" (para 8).
- **Shadow credit within 10 working days for every unauthorised EBT**, value-dated (para 9).
- **Resolution within 90 days**, and if the bank misses that, the compensation must be paid anyway (para 10).
- **Burden of proof on the bank** (para 12).

All PRIMARY, [Id=11040](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11040&Mode=0).

```python
CAP = {"BSBD": 5_000, "SB": 10_000, "PPI_GIFT": 10_000, "MSME_CA_CC_OD": 10_000,
       "INDIV_CA_CC_OD_UPTO_25L": 10_000, "CC_UPTO_5L": 10_000, "OTHER_CA_CC_OD": 25_000, "CC_ABOVE_5L": 25_000}

def classify_old(txn, case, cause):
    if txn.dt > case.bank_report_dt:   return ("BANK_BEARS", "2017 para 7(i)")
    if cause == "BANK_NEGLIGENCE":     return ("ZERO_LIABILITY", "2017 para 6(i)")
    if cause == "CUSTOMER_NEGLIGENCE": return ("CUSTOMER_LIABLE_UNTIL_REPORT", "2017 para 7(i)")
    if cause == "THIRD_PARTY_BREACH":
        d = working_days(case.home_branch_calendar, start=txn.alert_received_date + 1, end=case.bank_report_date)
        if d <= 3: return ("ZERO_LIABILITY", "2017 para 6(ii)")
        if d <= 7: return (("CAPPED", min(txn.amount, CAP[case.account_type])), "2017 para 7(ii), Table 1")
        return ("PER_BANK_POLICY", "2017 para 7(ii)")
    return ("LIABILITY_NOT_ESTABLISHED_BY_BANK", "2017 para 12")
# shadow_credit_due = add_working_days(notification_date, 10); resolution_due = receipt_date + 90 calendar days
# no small-value compensation exists under the old regime
```

Two variants need separate branches. **Co-operative banks** follow an equivalent 14 December 2017 circular with the same day counts and caps. The one difference is that the ₹25,000 row omits "credit cards above ₹5 lakh" (PRIMARY, [Id=11188](https://rbi.org.in/scripts/NotificationUser.aspx?Id=11188&Mode=0)). **Non-bank wallets** (Paytm, PhonePe or Amazon Pay *wallet* balances, as opposed to UPI from a bank account) follow para 17 of the PPI Master Direction. It counts calendar "days", has a flat ₹10,000 cap for days 4–7, and requires shadow reversal within 10 days. If the issuer misses 90 days, the amount is payable "irrespective of whether the negligence is on the part of customer or otherwise" (PRIMARY, [PPI MD id=12156](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12156)). A UPI debit from a bank account falls under the bank framework. The September 2019 TAT circular's ₹100-per-day compensation applies only to *failed* transactions, never to a successful fraudulent debit, so the agent must never offer it for fraud (PRIMARY, [Id=11693](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11693&Mode=0)).

The regime selector is one line: `"NEW" if txn.date >= date(2027,1,1) else "OLD"`, applied **per transaction**, with a separate PPI branch keyed on the debited instrument. The old clock also carries a practical warning. If the bank never sent an alert, the app cannot compute day zero. That favours the customer, because the bank must keep timestamped alert and response logs and carries the burden of proof (para 5 and para 12).

## Three tracks run in parallel after a fraud

A victim faces three separate systems, and today nobody joins them up.

**Track 1: police and money trail (1930 → NCRP → CFCFRMS → MRM).** The victim calls 1930 or files at cybercrime.gov.in and gets an acknowledgement number. Guides describe it as 14 digits, which is unverified against the portal (SECONDARY: [The420](https://the420.in/how-to-report-cybercrime-online-india/)). CFCFRMS, the closed system linking banks and police, alerts the first bank's nodal officer. That bank holds the funds if they are still there, or the alert cascades down the chain (SECONDARY: [Telangana Today, quoting the Hyderabad DCP](https://telanganatoday.com/golden-hour-rule-to-rescue-of-cyber-fraud-victims-in-hyderabad)). No official source fixes a "golden hour" in minutes; police guidance says roughly 1–3 hours. MHA says the Money Restoration Module (MRM) and the Grievance Redressal Module have been "functional from April, 2026", alongside a new SOP on removing liens and restoring funds (PRIMARY: [PIB 2287039](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2287039&reg=48&lang=2)).

MRM thresholds are SECONDARY only. **Category 1:** at most ₹50,000 held in one account, no FIR or court order needed. **Category 2:** more than ₹50,000 in total but no single account above ₹50,000, still no FIR. **Category 3:** more than ₹50,000 held in a single account, FIR mandatory (SECONDARY: [Free Press Journal/IANS](https://www.freepressjournal.in/mumbai/relief-for-cyber-scam-victims-mha-launches-online-money-restoration-module-to-recover-frozen-funds)). The victim logs in with an OTP on the NCRP-registered mobile, enters the complaint ID, uploads a PAN and gives a receiving account (SECONDARY: [CSAI](https://www.ncsai.in/banking-cyber-policies)). Two further claims rest on one search snippet: that banks must lift a freeze within 90 days absent a court order, and the SOP date of about 15 January 2026 (SECONDARY: [Business Standard](https://www.business-standard.com/india-news/mha-sop-cyber-fraud-refunds-below-50000-no-court-order-126011500706_1.html)). Contested or large amounts go to a Magistrate under BNSS s.503 or s.497. Complaints above ₹10 lakh become an e-Zero FIR under an I4C pilot running since 19 May 2025 through Delhi's e-Crime Police Station. National roll-out was announced but is unconfirmed (SECONDARY: [India TV](https://www.indiatvnews.com/news/india/home-ministry-unveils-e-zero-fir-system-to-swiftly-tackle-cybercrime-and-aid-victims-in-recovery-2025-05-19-990982)). Money already withdrawn cannot be restored. **No public API exists for NCRP, 1930, CFCFRMS or MRM**, and every citizen step is gated by the victim's own phone or OTP.

**Track 2: bank liability.** This is the RBI framework above. Its value is that it **does not depend on the money being traced**. Even if police freeze nothing, the bank may owe a reversal or compensation.

**Track 3: internal grievance, then the RBI Ombudsman.** Under the Internal Ombudsman Directions, 2026 (commercial banks with 10 or more outlets), a partially resolved or rejected complaint is **auto-escalated to the bank's Internal Ombudsman within 20 days**. The **final decision is due within 30 days of receipt**, and the reply must point to the RBI Ombudsman and cms.rbi.org.in (PRIMARY: [MD id=13271](https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=13271), cl. 14(1), 14(9), 14(12)). The **Reserve Bank – Integrated Ombudsman Scheme 2026 replaced RB-IOS 2021 on 1 July 2026** (PRIMARY: [PR prid=62052](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=62052)). The complainant must first go to the bank, then wait **30 days, or any longer RBI/NPCI/card-network timeline, "whichever is higher"**, unless the bank replies unsatisfactorily earlier. The Ombudsman complaint is due **within 90 days** of that expiry or of the bank's last communication, whichever is later.

There is **no cap on the disputed amount**. Consequential loss is capped at ₹30 lakh, and time, expenses and harassment at ₹3 lakh. Appeals go within 30 days of the award, extendable by 30. Filing is via cms.rbi.org.in, crpc@rbi.org.in or CRPC Chandigarh, with contact centre 14448 (PRIMARY (summary): [RBI FAQ Id=153](https://rbi.org.in/SCRIPTs/FAQView.aspx?Id=153); [cms.rbi.org.in](https://cms.rbi.org.in/)). Clause numbers such as 10(1)(g) and 8(3) are SECONDARY ([Vinod Kothari](https://vinodkothari.com/2026/01/rbi-integrated-ombudsman-scheme-2026-key-changes/)). The scheme PDF sat behind a CAPTCHA and was not read. The FAQ says criminal proceedings and police investigations do **not** bar an Ombudsman complaint, so an FIR or NCRP complaint is no obstacle.

The deadline engine therefore computes these clocks per case. In each, the first value is the safe date to act by:

| Clock | New regime (txn ≥ 1 Jan 2027) | Old regime (txn < 1 Jan 2027) | Status |
|---|---|---|---|
| Report window for zero liability (third-party breach) | 5 calendar days from occurrence; show txn+4 as safe, txn+5 as outer | 3 working days from alert receipt, receipt day excluded | PRIMARY; day-0 rule open |
| Report window for compensation | NCRP/1930 **and** bank within 5 calendar days | none (no compensation) | PRIMARY |
| Shadow reversal | credit cards only, receipt+5 calendar days | all EBTs, notification+10 working days | PRIMARY |
| Bank decision | receipt+45 (cross-border 60) | receipt+90 | PRIMARY |
| Internal Ombudsman final decision | receipt+30 (CBs ≥10 outlets) | same | PRIMARY; conflict with 45/90 open |
| Compensation payment | application+5 calendar days | n/a | PRIMARY |
| Earliest Ombudsman filing | receipt+30, or receipt+45 if the 76Q timeline counts as "longer"; immediately on rejection | receipt+30, or +90 | PRIMARY (summary); interaction open |
| Ombudsman filing deadline | max(that expiry, last bank reply) + 90 | same | PRIMARY (summary) |
| MRM freeze lift if no order | ~90 days | same | SECONDARY, single snippet |

One design principle resolves every ambiguity on the user's side. **"File by" dates use the earliest reading** (txn+4, receipt+30+90). **"You may file from" dates use the latest reading** (receipt+45), because a premature Ombudsman complaint is non-maintainable. The only exception is a rejection, which opens the door at once. For a fraud on Monday 4 January 2027 reported to the bank on Wednesday 6 January, the screen shows:

- report by **Friday 8 January** (outer limit 9 January)
- bank decision due **20 February**
- Ombudsman may be approached from **20 February**, or immediately on rejection
- file by **6 May 2027** (latest reading 21 May)

## Fraud statistics: ₹22,495 crore reported across 24 lakh complaints, and "saved" means frozen

The defensible headline figure is: **"₹22,495 crore reported lost across 24,02,579 cyber-financial-fraud complaints in 2025"** (PRIMARY: MHA Rajya Sabha reply, 11 Feb 2026, [PIB 2226441](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2226441&lang=1&reg=3)). The same table gives 2024 as 19,18,835 complaints and ₹22,848 crore, and 2021 as ₹551 crore. That is roughly a 40-fold rise in the reported amount over four years. Complaints grew about 25% in 2025 while the reported amount dipped slightly. "Amount reported" is what citizens claimed on NCRP. It is not adjudicated and not net of frozen money, and the table is footnoted "data is dynamic". MHA's July 2026 reply gives 2021–25 cumulative totals of more than 65.89 lakh complaints, more than ₹55,050 crore reported, **more than ₹8,189 crore "marked as Lien"**, and more than 1,95,760 FIRs (PRIMARY: [PIB 2287039](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2287039&reg=48&lang=2)). The year-wise rows actually sum to ₹55,649 crore. Neither reply explains the gap, so say "more than ₹55,000 crore".

The "saved" figures resolve into one fact. The ₹8,189 crore that the February reply calls "saved" to 31 December 2025 is the same number the July reply calls "amount marked as Lien". **"Saved" means frozen in accounts, not returned to victims.** The latest cut-off is more than **₹11,158 crore saved in more than 32.80 lakh complaints, cumulative to 30 June 2026** (PRIMARY, [PIB 2287039](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2287039&reg=48&lang=2)). **No official figure exists for money actually restored.** Frozen money is at most about 15% of the amount reported for 2021–25, and the share actually restored is unknown and probably lower (INFERENCE). That gap between "frozen" and "repaid" is why the bank-liability track matters: it does not depend on the money being traced.

| Figure | Value | Source | Status |
|---|---|---|---|
| 2025 complaints / reported amount | 24,02,579 / ₹22,495 cr | [PIB 2226441](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2226441&lang=1&reg=3) | PRIMARY |
| Growth 2021→2025 | ₹551 cr → ₹22,495 cr | same | PRIMARY |
| 2021–25 cumulative | >65.89 lakh complaints, >₹55,050 cr, >1.96 lakh FIRs (~3%) | [PIB 2287039](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2287039&reg=48&lang=2) | PRIMARY |
| Frozen ("saved") | >₹11,158 cr, to 30 Jun 2026 | same | PRIMARY |
| MRM functional | from April 2026 | same | PRIMARY |
| Senior citizens, 2025 | 1,03,488 complaints, ₹4,005.12 cr (≈4% of complaints, ≈18% of amount) | [Asianet Newsable (PTI)](https://newsable.asianetnews.com/india/senior-citizens-women-lost-rs-7-769-crore-to-cyber-fraud-in-2025-articleshow-u9oad8w) | SECONDARY; attribute "as reported" |
| Digital arrest | 1,23,672 / ₹1,935 cr (2024); 58,239 / ₹1,211 cr (2025); >21,900 / ₹647 cr (Jan–Aug 2026) | [Free Press Journal](https://www.freepressjournal.in/tech/digital-arrest-fraud-over-21900-complaints-involving-647-crore-registered-in-2026-centre-tells-supreme-court) | SECONDARY ("MHA status report to SC, as reported") |

Avoid these figures:

- "28 lakh complaints in 2025": untraced.
- "₹19,812 crore": a cheating-only cut.
- "22.6 lakh complaints in 2024": does not match the official series.
- "₹7,130 crore saved in 2025": cumulative from 2021 to 31 October 2025.
- "₹8,189 crore recovered": it is lien-marked, not recovered.
- Any "digital fraud fell 98%" figure from RBI's annual report: it counts only bank-reported frauds of ₹1 lakh and above.
- Any claim that RBI cited fraud statistics when revising the rules. Its press releases give none, only that the landscape "has evolved considerably" ([PR prid=62340](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=62340)).

The senior-citizen figure is SECONDARY until the PIB release is found: older victims file few complaints but lose about four times the average per complaint.

## Legal envelope and design constraints

The legal envelope is workable if the scope stays disciplined: a free self-help tool that never looks like a recovery agent.

**Data protection.** The DPDP Rules were notified in November 2025 with an 18-month phase-in. The core duties (notice, security, breach reporting, erasure, cross-border transfer) bind from about 13–14 May 2027, so they are **not yet in force** (PRIMARY: [PIB backgrounder](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf); SECONDARY: [SCC Online](https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/)). A January 2026 MeitY proposal to compress the timeline to 12 months, which would make today the deadline, has no confirmed notification ([Mondaq/SS Rana](https://www.mondaq.com/india/data-protection/1773554/meity-plans-to-cut-short-dpdp-compliance-timeline-and-notify-cross-border-restrictions-for-sdfs)). Meanwhile the IT Act's SPDI Rules 2011 still treat financial information as sensitive personal data ([Mondaq](https://www.mondaq.com/india/privacy-protection/1707558/digital-personal-data-protection-rules-2025-highlights)). So build to full DPDP standard now: a standalone bilingual consent notice, minimal collection, delete-on-request with short retention, and a "helper" role, which matches DPDP's right to nominate someone. Synthetic data is outside DPDP, but the consent screen and delete button should still be shown.

**Practice of law.** The Advocates Act reserves the practice of law to enrolled advocates (ss.29 and 33), and s.45 punishes unauthorised practice. In September 2026 the Bar Council of Maharashtra & Goa issued a s.45 notice to a non-lawyer advice platform, citing case law that treats drafting as practice ([LiveLaw](https://www.livelaw.in/news-updates/bar-council-of-maharashtra-goa-warns-platform-against-giving-legal-advice-without-advocate-enrolment-548350)). No ruling covers a tool that helps citizens fill in their own government forms. The safe design is legal *information* and self-help. The user is author and filer. Outputs cite the rule in conditional language ("under para 76M, liability can be zero if…") and never predict outcomes. There are no fees and no representation, and the app signposts free legal aid and lawyers for court matters.

**Impersonation and recovery scams.** RBI warns that fraudsters use fake RBI letterheads to collect "processing fees" ([RBI caution](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=58595)). Fake "recovery agents" re-victimise people: a Mumbai retired teacher who lost ₹70,000 then lost ₹14.38 lakh to a recovery scam ([The420](https://the420.in/retired-teacher-recovery-scam-1438-lakh)). Telangana's cyber bureau tells victims to use only MRM and says "no fee is charged" ([Telangana Today](https://telanganatoday.com/tgcsb-urges-cybercrime-victims-to-claim-refunds-only-through-official-portal)). The Emblems and Names Act bars imitating protected emblems ([Act text](https://thc.nic.in/Central%20Governmental%20Acts/Emblems%20and%20Names%20(Prevention%20of%20Improper%20Use)%20Act,%201950.pdf)). The synthetic-content rules in the February 2026 IT Rules amendment cover audio and visual content, reportedly not text, so text drafts are likely out of scope (SECONDARY: [KS&K](https://ksandk.com/information-technology/it-rules-2026-regulating-synthetic-media/)).

These lead to design rules the project treats as binding:

- **1930 before everything.** The first screen says "Lost money in the last few hours? Call 1930 and your bank's 24x7 line now, then come back."
- **Never accept or store secrets.** No OTP, PIN, CVV, passwords or full card numbers. Regex-block them client-side and auto-mask them in screenshots.
- **Redact by default.** Show last-four digits only, and mask third parties' phone numbers except the fraudster's.
- **The human submits everything.** The app never logs into a portal and never auto-files.
- **Cite every claim.** Each liability statement gets a paragraph citation and a "rules last verified" date.
- **No recovery language.** No recovered amounts and no recovery probabilities, anywhere.
- **Persistent disclaimer.** A footer on every page: "independent, free; not RBI, Government, police, NCRP or your bank". No RBI logo, emblem or police branding.
- **No outbound contact.** Reminders go only to the user who set them up.
- **Recovery-scam red-flag card.** "Anyone charging a fee to get your money back is a scammer."
- **Calm handling for digital-arrest victims.** Use the I4C fact that no agency arrests anyone on a video call ([ThePrint](https://theprint.in/india/cbi-ed-police-dont-arrest-people-through-video-calls-indian-cyber-crime-coordination-centre/2299608)). Never use countdown pressure on them. Route crisis language to national mental-health and emergency numbers, verified from official sources before shipping.
- **Preserve evidence.** Hash originals and annotate only copies.

## Open items and the default each one uses

| Area | Open item | Default encoding until resolved |
|---|---|---|
| New rules | Day-0 vs day-1 counting for "within five calendar days from the date of its occurrence" (76M, 76T(1)(b)) | Display txn+4 as the safe deadline; classify a day-5 report as BORDERLINE |
| New rules | Sunset of compensation: EBTs through 31 Dec 2027 or 1 Jan 2028 (76U)? Annex quarters end Dec'27 | Use 31 Dec 2027 |
| New rules | Does "coercion or duress" cover digital-arrest victims, and which liability limb applies? | Fraudulent EBT = yes (flagged); limb = 76N candidate; show "bank must prove" |
| New rules | Pure deception / authorised-push-payment coverage (draft category dropped; reasons in the unread feedback annex) | COVERAGE_UNCERTAIN → manual review |
| New rules | Compensation split base (net vs gross) and rounding | Net (per Illustration 1); round to the rupee |
| New rules | Do lien-marked or frozen amounts count as "recoveries"? | No: only amounts credited to the customer |
| New rules | Mixed-regime complaints; simultaneous bank and customer negligence | Assess per transaction; show both limbs |
| New rules | Late third-party-breach "per bank policy" outcome | Unencodable; link the bank's published policy (76A) |
| New rules | Any corrigendum, FAQ, extension or deferral after 14 Jul 2026. A 13 Nov 2026 re-check found none, but read RBI pages only through summaries, only spot-checked the notifications listing for 15 Jul to 18 Oct, and did not see press releases for 15 Jul to 2 Nov. (Id 13556 is an unrelated small-finance-bank governance direction; the 6 Aug 2026 RBC Fourth Amendment, Id 13665, covers recovery agents only.) | Re-check rbi.org.in before 1 Jan 2027; show a "rules last verified" date |
| New rules | 76T(2) fixed split (₹19,118 / ₹2,941 / ₹2,941 from net ₹29,412) was read from the primary text and RBI's Illustrations 2 and 3 in the first pass, but the 13 Nov re-check could not find it in any source it read (summaries only). Not refuted | Keep the encoded split and golden tests; re-read 76T(2) in the raw text before the demo |
| New rules | Possible bank-fault compensation. In Suo Motu WP (Crl) 3/2025 (digital arrest), the 4 Aug 2026 order (PRIMARY) asked RBI for a debit-hold SOP and asked a committee to discuss shared liability and victim compensation. A 29 Oct 2026 hearing, reported by several outlets but with no order text found (SECONDARY), wants RBI rules to make banks compensate "not less than the amount lost" where their due diligence failed. RBI's only response so far is the 11 Sep 2026 draft KYC debit-hold directions, which have no compensation clause. The 30 Nov / 31 Dec dates look like the government's own schedule; next hearing probably 23 Nov (unverified) | Show the current 76L / 76N / 76T result, flag that a bank-fault rule is pending, and never promise a cap or an amount above what the current rules give |
| Old rules | Home-branch holiday calendars for working days | National holiday list plus Sundays and 2nd/4th Saturdays, flagged approximate |
| Old rules | SFB/RRB consolidated paragraph numbers not opened; local area banks had no prior instructions | Cite the 2017 circular; LAB pre-2027 = "no RBI framework found" |
| Old rules | Co-op bank credit cards above ₹5 lakh (no Table 1 row); PPI "irrespective of negligence" 90-day clause | ₹25,000 flagged unclear; PPI clause shown with caveat |
| Escalation | RB-IOS 2026 clause text (PDF behind CAPTCHA; clause numbers secondary) | Cite the FAQ, not clause numbers |
| Escalation | Does the 45-day (new) or 90-day (old) bank timeline count as the "longer timeline" before the Ombudsman? Does the Internal Ombudsman's 30-day rule conflict? | "Earliest" = latest reading; "file by" = earliest reading |
| Escalation | NPCI UPI fraud dispute turnaround times not fetched | Omit; route via bank |
| Recovery | MRM categories, 90-day freeze lift, 24-hour NCRP completion after a 1930 call, 14-digit acknowledgement format, national e-Zero FIR status: all secondary | Present as "reported process"; link official portals |
| Statistics | Senior-citizen and digital-arrest figures secondary. The 4 Aug 2026 Supreme Court order gives digital-arrest complaint counts (1,23,672 in 2024; 58,239 in 2025; 16,377 to 30 Jun 2026) but no rupee amounts; the ₹1,935 cr / ₹1,211 cr / ₹647 cr figures could not be re-found on 13 Nov 2026 | Attribute "as reported" or omit; prefer the court order's complaint counts |
| Legal | Whether the DPDP 12-month compression was notified; Emblems Act Schedule; helpline numbers | Build to DPDP now; no RBI marks; verify numbers on official sites |
