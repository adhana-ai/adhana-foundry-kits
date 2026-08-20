#!/usr/bin/env python3
"""Generate the invoice records and vendor inquiries this kit checks against, from a fixed seed.

    python3 tools/build_corpus.py
    python3 tools/build_corpus.py --verify     # re-reads data/*.jsonl from disk and re-derives
                                                # every gold row independently -- see verify()

Writes data/invoices.jsonl and data/gold.jsonl, byte-identical on every run. Nothing is fetched and
nothing is licensed from anybody: every vendor, invoice number, PO number and amount here is
invented, so the corpus ships under this repo's MIT licence and there is no third-party grant to
verify.

⚑ WHY THE RECORDS ARE INVENTED. A real payment run and a real vendor's payment-status history name
a real vendor, a real bank reference and a real approval chain nobody will let leave the building.
A synthetic set is the only kind of AP-tracing corpus that can be re-run by a stranger with a clone
and no NDA to sign. See data/SOURCES.md.

⚑ THE FOUR STAGES ARE ALWAYS ALL PRESENT, WHATEVER THEIR STATE. Every invoice carries a full match,
approval, run_inclusion and remittance record -- never a partial one -- because the mechanic this
kit measures is reading all four IN ORDER and stopping at the true bottleneck, not filling in a
blank. See src/prompt.py for the precedence rule stated to the model.

⚑ THE TRAP, PLANTED ON PURPOSE. A meaningful fraction of the invoices whose true governing stage is
an open exception (match_exception or approval_exception) are built so a DOWNSTREAM field --
usually remittance, sometimes run_inclusion -- still carries a complete-looking value: a real
run_id and scheduled_date, or a real remittance_date and reference. This is a DATA-SHAPE trap, not
adversarial text -- nothing in any field is written to deceive, the fields are simply what they
are, and the eval exists to measure whether a reader (model or baseline) applies the precedence
rule or stops at the first field that looks reassuring. See TRAP_N below for exactly how often, and
`derive_stage()` for the precedence rule itself, used both to label gold and, independently, by
--verify to catch this file lying about its own corpus.
"""
import argparse
import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
sys.path.insert(0, HERE)

from src import prompt as P                                          # noqa: E402

SEED = 20260819                              # fixed. change it and every downstream file changes.

# 35 invoices across the five stages -- similar order of magnitude to every sibling kit's corpus.
# Weighted toward the two exception stages (14 of 35) because that is where the trap lives and
# where requires_ap_review matters; the other three stages exist so the model has to actually
# discriminate rather than always answering "needs review".
STAGE_COUNTS = {
    "match_exception": 6,
    "approval_exception": 8,
    "awaiting_run_inclusion": 6,
    "in_scheduled_run": 8,
    "remitted": 7,
}

# ⚑ 6 OF THE 14 EXCEPTION-STAGE INVOICES ARE TRAPS -- ~43%, THE SAME ORDER OF MAGNITUDE AS
# fin-invval's 45% AMBIGUOUS-LINE FRACTION. Split 4 remittance-trap / 2 run_inclusion-trap because
# the mechanic spec names remittance as the MOST OFTEN trapped field, not the only one -- a fixed
# split guarantees both patterns actually ship, the same reason fin-close samples NO_BASIS_N /
# NO_THRESHOLD_N rather than drawing an independent coin flip per template (an independent draw at
# this corpus's size can legitimately land on zero of one pattern).
TRAP_N = 6
TRAP_REMITTANCE_N = 4
TRAP_RUN_INCLUSION_N = 2

VENDOR_NAMES = [
    "Meridian Supply Co.", "Northgate Logistics", "Vantage Office Systems",
    "Crestline Industrial Parts", "Bluecrest Facilities Group", "Ashford Packaging",
    "Wrenfield Electrical Supply", "Harlow Fleet Services", "Copperline Materials",
    "Silverdale IT Procurement", "Fenwick Janitorial Supply", "Oakmere Print & Design",
    "Thornbury Freight Co.", "Larkspur Catering Group", "Greystone Security Systems",
]

MATCH_REASONS = [
    "quantity variance vs receipt",
    "price variance vs purchase order",
    "missing receiving record",
    "duplicate invoice number flagged",
    "invoice references a purchase order not found in the system",
]
APPROVAL_REASONS = [
    "amount exceeds manager approval threshold, escalated",
    "budget code mismatch, held for correction",
    "cost center owner has not responded to the approval request",
    "invoice amount exceeds the original purchase order by more than tolerance, escalated for "
    "review",
]
RUN_HOLD_REASONS = [
    "held pending vendor W-9 update",
    "held pending vendor banking details confirmation",
    "missed this cycle's payment run cutoff, queued for the next run",
    "on hold pending a repeat three-way match re-verification",
]
METHODS = ["ACH", "wire", "check"]

INQUIRY_TEMPLATES = [
    "Can you confirm when {inv} will be paid?",
    "Has payment for {inv} gone out yet?",
    "Why hasn't {inv} been paid -- it was submitted {weeks} ago?",
    "What's the status on {inv}? Our records show it as overdue.",
    "When should we expect payment on {inv}?",
    "Following up on {inv} -- any update on payment timing?",
    "We haven't seen payment for {inv} land yet. Can you check on it?",
    "Quick check on {inv} -- is that one scheduled for this run?",
]

SUBMITTED_START = date(2024, 4, 1)
SUBMITTED_END = date(2024, 7, 20)


def _rand_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _after(rng, d, lo, hi):
    return d + timedelta(days=rng.randint(lo, hi))


def _match_clean():
    return {"matched": True, "reason": None}


def _match_exception(rng):
    return {"matched": False, "reason": rng.choice(MATCH_REASONS)}


def _approval_clean():
    return {"status": "approved", "reason": None}


def _approval_pending():
    # ⚠︎ NOT AN ARBITRARY DEFAULT. When match has not cleared, approval genuinely has not been
    # reached yet -- "pending" is what a real AP system shows here, and it is also why approval's
    # own check in the precedence rule only fires on "exception": "pending" resolves through
    # naturally at the run_inclusion step, which is correctly false whenever approval is pending.
    return {"status": "pending", "reason": None}


def _approval_exception(rng):
    return {"status": "exception", "reason": rng.choice(APPROVAL_REASONS)}


def _run_not_reached(reason_text):
    return {"included": False, "run_id": None, "scheduled_date": None, "reason": reason_text}


def _run_held(rng):
    return {"included": False, "run_id": None, "scheduled_date": None,
            "reason": rng.choice(RUN_HOLD_REASONS)}


def _run_included(run_id, scheduled_date):
    return {"included": True, "run_id": run_id, "scheduled_date": scheduled_date, "reason": None}


def _remit_not_yet(reason_text):
    return {"remitted": False, "remittance_date": None, "method": None, "reference": None,
            "reason": reason_text}


def _remit_done(rng, remittance_date):
    return {"remitted": True, "remittance_date": remittance_date, "method": rng.choice(METHODS),
            "reference": "REM-%06d" % rng.randint(100000, 999999), "reason": None}


def derive_stage(inv):
    """The precedence rule, and the ONLY place it is written. Read match, approval, run_inclusion,
    remittance IN ORDER; the true current stage is the first one that is not cleanly complete.
    Used to label gold at generation time AND, independently via --verify, to re-derive gold from
    the records actually written to disk -- so a drift between the two is caught rather than
    assumed away. See src/prompt.py's SYSTEM for the same rule stated to the model."""
    if not inv["match"]["matched"]:
        return "match_exception"
    if inv["approval"]["status"] == "exception":
        return "approval_exception"
    if not inv["run_inclusion"]["included"]:
        return "awaiting_run_inclusion"
    if not inv["remittance"]["remitted"]:
        return "in_scheduled_run"
    return "remitted"


def derive_requires_ap_review(stage):
    return stage in P.REVIEW_STAGES


def derive_expected_date(inv, stage):
    if stage == "in_scheduled_run":
        return inv["run_inclusion"]["scheduled_date"]
    if stage == "remitted":
        return inv["remittance"]["remittance_date"]
    return None


def build_invoice(idx, invoice_no, target_stage, trap_type, rng):
    """One invoice record plus the inquiry it is paired with. `target_stage` is what this
    invoice is BUILT to resolve to; `derive_stage()` is run on the finished record afterward and
    asserted to match -- the gold label is never the target_stage variable itself, precisely so a
    bug in this function's field construction cannot silently ship a mislabelled row."""
    invoice_id = "INV-2024-%04d" % invoice_no
    vendor = rng.choice(VENDOR_NAMES)
    po_number = "PO-%05d" % rng.randint(10000, 99999)
    amount = round(rng.uniform(420.0, 68000.0), 2)
    submitted = _rand_date(rng, SUBMITTED_START, SUBMITTED_END)

    run_id = "RUN-2024-%03d" % rng.randint(1, 52)
    scheduled = _after(rng, submitted, 5, 20)
    remitted_on = _after(rng, scheduled, 0, 3)

    if target_stage == "match_exception":
        match = _match_exception(rng)
        approval = _approval_pending()
        if trap_type == "remittance":
            run_inclusion = _run_included(run_id, scheduled.isoformat())
            remittance = _remit_done(rng, remitted_on.isoformat())
        elif trap_type == "run_inclusion":
            run_inclusion = _run_included(run_id, scheduled.isoformat())
            remittance = _remit_not_yet(
                "not yet remitted; pulled from the scheduled run pending resolution")
        else:
            run_inclusion = _run_not_reached(
                "not yet eligible for run inclusion; match exception outstanding")
            remittance = _remit_not_yet("not yet remitted; match exception outstanding")

    elif target_stage == "approval_exception":
        match = _match_clean()
        approval = _approval_exception(rng)
        if trap_type == "remittance":
            run_inclusion = _run_included(run_id, scheduled.isoformat())
            remittance = _remit_done(rng, remitted_on.isoformat())
        elif trap_type == "run_inclusion":
            run_inclusion = _run_included(run_id, scheduled.isoformat())
            remittance = _remit_not_yet(
                "not yet remitted; pulled from the scheduled run pending resolution")
        else:
            run_inclusion = _run_not_reached(
                "not yet eligible for run inclusion; approval not complete")
            remittance = _remit_not_yet("not yet remitted; approval not complete")

    elif target_stage == "awaiting_run_inclusion":
        match = _match_clean()
        approval = _approval_clean()
        run_inclusion = _run_held(rng)
        remittance = _remit_not_yet("not yet remitted; pending run inclusion")

    elif target_stage == "in_scheduled_run":
        match = _match_clean()
        approval = _approval_clean()
        run_inclusion = _run_included(run_id, scheduled.isoformat())
        remittance = _remit_not_yet("not yet remitted; scheduled for this run")

    else:  # remitted
        match = _match_clean()
        approval = _approval_clean()
        run_inclusion = _run_included(run_id, scheduled.isoformat())
        remittance = _remit_done(rng, remitted_on.isoformat())

    tpl = rng.choice(INQUIRY_TEMPLATES)
    weeks = rng.randint(1, 6)
    inquiry = tpl.format(inv=invoice_id, weeks=("1 week" if weeks == 1 else "%d weeks" % weeks))

    inv = {
        "invoice_id": invoice_id, "vendor_name": vendor, "po_number": po_number,
        "amount": amount, "submitted_date": submitted.isoformat(), "inquiry": inquiry,
        "match": match, "approval": approval, "run_inclusion": run_inclusion,
        "remittance": remittance,
    }

    stage = derive_stage(inv)
    assert stage == target_stage, (
        "built invoice %s for target_stage %r but derive_stage() says %r -- the field "
        "construction above and the precedence rule have drifted" % (invoice_id, target_stage,
                                                                      stage))
    review = derive_requires_ap_review(stage)
    expected_date = derive_expected_date(inv, stage)
    downstream_paid_looking = bool(remittance["remitted"])
    trap = trap_type is not None
    gold = {
        "invoice_id": invoice_id, "current_stage": stage, "requires_ap_review": review,
        "expected_date": expected_date, "trap": trap, "trap_field": trap_type,
        "downstream_paid_looking": downstream_paid_looking,
    }
    return inv, gold


def build_corpus(rng):
    plan = []
    for stage, n in STAGE_COUNTS.items():
        plan.extend([stage] * n)
    rng.shuffle(plan)

    exception_idx = [i for i, s in enumerate(plan) if s in P.REVIEW_STAGES]
    trap_idx = set(rng.sample(exception_idx, TRAP_N))
    remittance_trap_idx = set(rng.sample(sorted(trap_idx), TRAP_REMITTANCE_N))
    run_trap_idx = trap_idx - remittance_trap_idx
    assert len(run_trap_idx) == TRAP_RUN_INCLUSION_N

    invoice_numbers = rng.sample(range(100, 2000), len(plan))

    invoices, gold = [], []
    for i, (stage, no) in enumerate(zip(plan, invoice_numbers)):
        trap_type = ("remittance" if i in remittance_trap_idx else
                    "run_inclusion" if i in run_trap_idx else None)
        inv, g = build_invoice(i, no, stage, trap_type, rng)
        invoices.append(inv)
        gold.append(g)
    return invoices, gold


def write(invoices, gold):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "invoices.jsonl"), "w", encoding="utf-8") as fh:
        for inv in invoices:
            fh.write(json.dumps(inv) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")


def verify():
    """Re-read data/invoices.jsonl and data/gold.jsonl FROM DISK -- not from build_corpus()'s
    in-memory return values -- and re-derive every gold row independently via derive_stage(). This
    is the mandatory internal-consistency check: gold must never be hand-labelled or copy-pasted,
    it must be reproducible from the invoice record alone, every time, by anyone who clones the
    repo. Same discipline fin-close's and fin-invval's corpus builders both enforce."""
    inv_path = os.path.join(DATA, "invoices.jsonl")
    gold_path = os.path.join(DATA, "gold.jsonl")
    invoices = [json.loads(l) for l in open(inv_path, encoding="utf-8") if l.strip()]
    gold_rows = {g["invoice_id"]: g for g in
                (json.loads(l) for l in open(gold_path, encoding="utf-8") if l.strip())}

    checked = 0
    for inv in invoices:
        g = gold_rows[inv["invoice_id"]]
        stage = derive_stage(inv)
        assert stage == g["current_stage"], (
            "%s: gold says current_stage=%r but derive_stage(record) says %r"
            % (inv["invoice_id"], g["current_stage"], stage))
        review = derive_requires_ap_review(stage)
        assert review == g["requires_ap_review"], (
            "%s: gold says requires_ap_review=%r but derive_requires_ap_review(%r) says %r"
            % (inv["invoice_id"], g["requires_ap_review"], stage, review))
        expected_date = derive_expected_date(inv, stage)
        assert expected_date == g["expected_date"], (
            "%s: gold says expected_date=%r but derive_expected_date says %r"
            % (inv["invoice_id"], g["expected_date"], expected_date))
        downstream_paid_looking = bool(inv["remittance"]["remitted"])
        assert downstream_paid_looking == g["downstream_paid_looking"], (
            "%s: gold says downstream_paid_looking=%r but the record's remittance.remitted is %r"
            % (inv["invoice_id"], g["downstream_paid_looking"], downstream_paid_looking))
        checked += 1

    trap_rows = [g for g in gold_rows.values() if g["trap"]]
    print("verify: %d invoices checked against gold, all four derived fields match, 0 drift"
          % checked)
    print("verify: %d trap invoices (%d remittance, %d run_inclusion), all with "
          "current_stage != remitted and downstream_paid_looking or a stale run_inclusion"
          % (len(trap_rows), sum(1 for g in trap_rows if g["trap_field"] == "remittance"),
             sum(1 for g in trap_rows if g["trap_field"] == "run_inclusion")))
    for g in trap_rows:
        assert g["current_stage"] != "remitted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="re-derive gold from data/*.jsonl on disk and assert no drift; does "
                         "not regenerate anything")
    a = ap.parse_args()

    if a.verify:
        verify()
        return

    rng = random.Random(SEED)
    invoices, gold = build_corpus(rng)
    write(invoices, gold)

    tally = {}
    for g in gold:
        tally[g["current_stage"]] = tally.get(g["current_stage"], 0) + 1
    review_n = sum(1 for g in gold if g["requires_ap_review"])
    trap_n = sum(1 for g in gold if g["trap"])
    print("invoices: %d" % len(invoices))
    print("stage tally:", tally)
    print("requires_ap_review: %d of %d" % (review_n, len(gold)))
    print("trap invoices: %d of %d exception-stage invoices (%.0f%%)"
          % (trap_n, tally.get("match_exception", 0) + tally.get("approval_exception", 0),
             100.0 * trap_n / (tally.get("match_exception", 0) + tally.get("approval_exception",
                                                                            0))))
    verify()


if __name__ == "__main__":
    main()
