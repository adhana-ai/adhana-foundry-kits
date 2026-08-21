#!/usr/bin/env python3
"""Generate synthetic position-break records and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one break per file) and data/gold.jsonl, byte-identical on every run.
Every account, security and memo here is invented -- nothing is fetched and nothing is licensed
from anybody, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ GOLD IS DERIVED FROM THE GENERATED RECORD TEXT, NEVER FROM A TARGET THAT SEEDED IT. The
quantities and the true/explainable classification are read back off the actual generated
document, not carried over from a random draw.

⚑ THE PLANTED AMBIGUITY: this kit's guardrail is that a break's TRUE status depends on what the
memo actually says happened, not on whether it USES settlement-sounding words. `AMBIGUOUS_FRACTION`
of this corpus's records use language from the "wrong" register on purpose: a genuine break whose
memo still mentions "pending settlement" (because that was the ORIGINAL, now-stale explanation,
overtaken by the fact that it never actually settled), and a genuinely explainable, resolved item
whose memo opens with an alarming word ("URGENT", "mismatch flagged") despite being fully
accounted for by the end of the same sentence. Gold always records the TRUE classification,
derived from which generator branch produced it -- never re-derived from a scorer's or a model's
own reading of the memo's surface tone.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_RECORDS = 55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]
SECURITIES = [
    ("US0378331005", "Apple-style Common Stock A"), ("US5949181045", "Northline Software Corp"),
    ("US02079K3059", "Meridian Search Holdings"), ("US88160R1014", "Voltway Motors Inc"),
    ("US0231351067", "Riverbend Commerce Group"), ("US4581401001", "Ironclad Industrials"),
    ("US30303M1027", "Bluepeak Media Corp"), ("US67066G1040", "Novacore Semiconductor"),
    ("US92826C8394", "Sunhaven Financial"), ("US1912161007", "Coastal Freight Lines"),
]
AGING_THRESHOLD_DAYS = 3
AMBIGUOUS_FRACTION = 0.40
NO_BREAK_FRACTION = 0.0  # every record here IS a break; is_true_break is the real question


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _explainable_memo(rng, ambiguous):
    if ambiguous:
        # opens with alarming language despite being fully resolved by the end of the memo
        variant = rng.choice([0, 1])
        if variant == 0:
            return ("URGENT -- system-flagged quantity mismatch. Reviewed same day: confirmed "
                    "as a T+1 settlement timing difference, trade has since settled, custodian "
                    "position now agrees. No action needed.")
        return ("Mismatch flagged by overnight reconciliation. Investigation found the "
                "difference is a corporate action (2-for-1 split) processing lag; custodian "
                "confirms shares will post by settlement date. Fully accounted for.")
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "Trade pending T+2 settlement, confirmed with custodian trade desk. Expected to clear on schedule."
    if variant == 1:
        return "Corporate action (cash dividend) processing; custodian will book on pay date per the announcement."
    return "Dividend receivable posted internally ahead of custodian's pay-date posting; timing difference only, no discrepancy."


def _true_break_memo(rng, ambiguous):
    if ambiguous:
        # still mentions "pending settlement" -- the ORIGINAL, now-stale explanation that never
        # actually resolved, which a model reading only for the word "pending" would misread as
        # explainable
        return ("Originally logged as trade pending T+2 settlement; settlement date has now "
                "passed with no confirmation from custodian and no correction submitted. "
                "Escalated to trade support, unresolved.")
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "No explanation on file. Custodian confirms a fail with no correction submitted."
    if variant == 1:
        return "Quantity discrepancy unresolved after three inquiries; custodian has not responded to the last two requests."
    return "Internal system shows a trade the custodian has no record of receiving. Unresolved."


def build_all(rng, n=N_RECORDS):
    stats = {"true_break": 0, "explainable": 0, "ambiguous": 0, "aged_past_threshold": 0}
    out = []
    for i in range(1, n + 1):
        holder = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        account_id = "ACCT-%06d" % rng.randint(100000, 999999)
        cusip, sec_name = rng.choice(SECURITIES)
        year, month = 2026, rng.randint(1, 8)
        as_of_date = "%04d-%02d-%02d" % (year, month, rng.randint(1, 25))

        internal_qty = rng.randint(100, 50000)
        break_amount = rng.randint(5, 2000)
        direction = rng.choice([1, -1])
        custodian_qty = internal_qty + direction * break_amount

        break_age_days = rng.randint(1, 12)
        if break_age_days > AGING_THRESHOLD_DAYS:
            stats["aged_past_threshold"] += 1

        is_true = rng.random() < 0.55
        ambiguous = rng.random() < AMBIGUOUS_FRACTION
        if ambiguous:
            stats["ambiguous"] += 1
        if is_true:
            memo = _true_break_memo(rng, ambiguous)
            stats["true_break"] += 1
        else:
            memo = _explainable_memo(rng, ambiguous)
            stats["explainable"] += 1

        rec_id = "PB-%04d" % i
        lines = [
            _underline("Account"), account_id, "",
            _underline("Security"), "%s -- %s" % (cusip, sec_name), "",
            _underline("As Of Date"), as_of_date, "",
            _underline("Internal Quantity"), str(internal_qty), "",
            _underline("Custodian Quantity"), str(custodian_qty), "",
            _underline("Break Age (Business Days)"), str(break_age_days), "",
            _underline("Assigned Analyst"), holder, "",
            _underline("Reconciling Memo"), memo, "",
        ]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rec_id,
            "account_id": account_id, "security_id": cusip, "security_name": sec_name,
            "as_of_date": as_of_date, "internal_quantity": internal_qty,
            "custodian_quantity": custodian_qty, "break_age_days": break_age_days,
            "assigned_analyst": holder, "reconciling_memo": memo,
            "is_true_break": "yes" if is_true else "no",
        }
        out.append((rec_id, text, gold))
    return out, stats


def _verify(rows):
    for rec_id, text, gold in rows:
        assert str(gold["internal_quantity"]) in text, rec_id
        assert str(gold["custodian_quantity"]) in text, rec_id
        assert gold["reconciling_memo"] in text, rec_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    n_flagged = sum(1 for _i, _t, g in rows
                    if g["is_true_break"] == "yes" and g["break_age_days"] > AGING_THRESHOLD_DAYS)
    print("records: %d   true breaks: %d   explainable: %d   %d (%.0f%%) written in the "
          "confusable ambiguous register"
          % (len(rows), stats["true_break"], stats["explainable"], stats["ambiguous"],
             100.0 * stats["ambiguous"] / len(rows)))
    print("breaks older than %d business days: %d   -> should be flagged (true AND aged): %d"
          % (AGING_THRESHOLD_DAYS, stats["aged_past_threshold"], n_flagged))
    print("internal consistency check: PASSED (every record's stated quantities and memo "
          "reconcile against its own document text)")


if __name__ == "__main__":
    main()
