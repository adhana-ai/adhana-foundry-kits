"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src.extract import compute as _compute         # noqa: E402
from src.extract import is_claim_valid as _icv      # noqa: E402
from src.extract import owed_commission as _owed    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ TWO NULLABLE FIELDS, AND THEIR NULLABILITY IS A RULE RATHER THAN A CONVENIENCE. They are
# COMPLEMENTARY: a booking the guest stayed on has a refund line and no cancellation penalty; a
# cancellation or no-show has a penalty line and no refund. That is checked directly below rather
# than folded into a generic nullable set, because "null sometimes" is a weaker and less useful
# property than "null exactly when the folio status makes the line inapplicable".
NULLABLE = {"room_revenue_refunded_usd", "penalty_charged_usd"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["claim_ref"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate claim_ref in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for claim_ref, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (claim_ref, f["name"], v, f["values"]))
            # ⚑ EVERY ALLOWED VALUE MUST ACTUALLY OCCUR. An enum member no record states is a
            # member the run never measures, and publishing it as an allowed value is a coverage
            # claim the corpus does not support.
            seen = {r.get(f["name"]) for r in by_id.values()}
            unseen = [v for v in f["values"] if v not in seen]
            if unseen:
                bad("%s allows %s but no gold row states %s"
                    % (f["name"], f["values"], unseen))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ THE TWO NULLABILITY INVARIANTS THEMSELVES, AND THEY MUST BE COMPLEMENTARY.
    wrong_refund = [s for s, r in by_id.items()
                    if (r.get("room_revenue_refunded_usd") is None)
                    != (r.get("folio_status") in ("cancelled", "no_show"))]
    if wrong_refund:
        bad("%d row(s) have room_revenue_refunded_usd nullness that disagrees with folio_status: "
            "%s" % (len(wrong_refund), sorted(wrong_refund)[:5]))
    wrong_penalty = [s for s, r in by_id.items()
                     if (r.get("penalty_charged_usd") is None)
                     != (r.get("folio_status") in ("stayed", "rebooked"))]
    if wrong_penalty:
        bad("%d row(s) have penalty_charged_usd nullness that disagrees with folio_status: %s"
            % (len(wrong_penalty), sorted(wrong_penalty)[:5]))
    both_null = [s for s, r in by_id.items()
                 if r.get("room_revenue_refunded_usd") is None
                 and r.get("penalty_charged_usd") is None]
    if both_null:
        bad("%d row(s) are null on BOTH nullable fields -- they are complementary by design: %s"
            % (len(both_null), sorted(both_null)[:5]))

    for claim_ref, r in sorted(by_id.items()):
        for name in ("room_revenue_usd", "non_room_charges_usd", "claimed_commission_usd",
                     "contract_rate_pct"):
            v = r.get(name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                bad("%s: %s=%r is not a non-negative number" % (claim_ref, name, v))
        for name in sorted(NULLABLE):
            v = r.get(name)
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0):
                bad("%s: %s=%r is not a non-negative number or null" % (claim_ref, name, v))
        if r.get("contract_rate_pct") == 0:
            bad("%s: a contracted rate of 0 pct makes every claim trivially zero" % claim_ref)

    # ⚑ GOLD MUST AGREE WITH ITS OWN COMPUTATION. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the reviewer's note, it is the arithmetic.
    disagree = []
    for claim_ref, r in sorted(by_id.items()):
        want = _icv(r.get("claimed_commission_usd"), r.get("folio_status"),
                    r.get("booking_source"), r.get("already_commissioned"),
                    r.get("room_revenue_usd"), r.get("room_revenue_refunded_usd"),
                    r.get("penalty_charged_usd"), r.get("contract_rate_pct"))
        if want != r.get("claim_valid"):
            disagree.append(claim_ref)
    if disagree:
        bad("%d gold row(s) label a validity their own folio values do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE SHARPEST CASES, ASSERTED RATHER THAN TRUSTED.
    # (a) A cancellation or no-show WITH a penalty charged is owed commission ON THE PENALTY.
    penalty_owed = [r for r in by_id.values()
                    if r.get("folio_status") in ("cancelled", "no_show")
                    and (r.get("penalty_charged_usd") or 0) > 0
                    and r.get("booking_source") == "channel"
                    and r.get("already_commissioned") == "no"]
    wrong_penalty_math = [
        r["claim_ref"] for r in penalty_owed
        if abs(_owed(r["folio_status"], r["booking_source"], r["already_commissioned"],
                     r["room_revenue_usd"], r["room_revenue_refunded_usd"],
                     r["penalty_charged_usd"], r["contract_rate_pct"])
               - round(r["penalty_charged_usd"] * r["contract_rate_pct"] / 100.0, 2)) > 0.005]
    if wrong_penalty_math:
        bad("%d cancellation/no-show row(s) with a penalty charged did not compute commission on "
            "the penalty: %s" % (len(wrong_penalty_math), wrong_penalty_math[:5]))
    else:
        print("  info  %d cancellation/no-show row(s) carry a charged penalty and are owed "
              "commission on it" % len(penalty_owed))

    # (b) A rebooked reservation is a stay and is commissionable on room revenue.
    rebooked = [r for r in by_id.values() if r.get("folio_status") == "rebooked"]
    rebooked_zero = [r["claim_ref"] for r in rebooked
                     if r.get("booking_source") == "channel"
                     and r.get("already_commissioned") == "no"
                     and (_owed(r["folio_status"], r["booking_source"], r["already_commissioned"],
                                r["room_revenue_usd"], r["room_revenue_refunded_usd"],
                                r["penalty_charged_usd"], r["contract_rate_pct"]) or 0) <= 0]
    if rebooked_zero:
        bad("%d rebooked row(s) computed to nothing owed -- a rebooked reservation is a stay: %s"
            % (len(rebooked_zero), rebooked_zero[:5]))
    else:
        print("  info  %d rebooked row(s), all commissionable on their room revenue"
              % len(rebooked))

    # (c) Non-room charges are NEVER in the base. Asserted by construction: adding them would
    #     change the answer on every row that has any, so the rule provably does not read them.
    reads_taxes = []
    for claim_ref, r in sorted(by_id.items()):
        if (r.get("non_room_charges_usd") or 0) <= 0:
            continue
        with_taxes = _owed(r["folio_status"], r["booking_source"], r["already_commissioned"],
                           (r["room_revenue_usd"] or 0) + r["non_room_charges_usd"],
                           r["room_revenue_refunded_usd"], r["penalty_charged_usd"],
                           r["contract_rate_pct"])
        without = _owed(r["folio_status"], r["booking_source"], r["already_commissioned"],
                        r["room_revenue_usd"], r["room_revenue_refunded_usd"],
                        r["penalty_charged_usd"], r["contract_rate_pct"])
        if r.get("booking_source") == "channel" and r.get("already_commissioned") == "no" \
                and r.get("folio_status") in ("stayed", "rebooked") \
                and abs((with_taxes or 0) - (without or 0)) < 0.005:
            reads_taxes.append(claim_ref)
    if reads_taxes:
        bad("%d row(s) are unchanged by adding non-room charges to the base -- the tax trap is "
            "not actually planted there: %s" % (len(reads_taxes), reads_taxes[:5]))

    # (d) Every fault class is present and non-empty, so a headline figure cannot hide an
    #     unmeasured case.
    counts = {}
    for r in by_id.values():
        key = r.get("_fault") or r.get("_shape") or "unclassified"
        counts[key] = counts.get(key, 0) + 1
    empty = [k for k, v in counts.items() if v == 0]
    if empty:
        bad("case class(es) with no rows: %s" % empty)
    else:
        print("  info  case mix: %s"
              % "  ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))

    n_no = sum(1 for r in by_id.values() if r.get("claim_valid") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one validity class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d claims are not owed as claimed (claim_valid=no)"
              % (n_no, len(by_id)))

    # The recovery flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"claim_valid": r.get("claim_valid"),
                              "invoice_status": r.get("invoice_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code recovery flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d claims are wrong AND on an already-paid invoice -- the recovery "
              "flag" % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the same lesson a sibling kit in this series paid for live:
    # its first keyword list fired on a negation inside a settled note and mis-registered four
    # records. Every note template here is checked against the floor's own keyword list before
    # any run may spend.
    try:
        from evals.baseline import DISPUTING_KEYWORDS
        from tools.build_corpus import ACCEPTING_NOTES, DISPUTING_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def disputing(note):
            return any(k in note.lower() for k in DISPUTING_KEYWORDS)
        for note in ACCEPTING_NOTES:
            if disputing(note):
                bad("the free floor reads an ACCEPTING note as a dispute -- a keyword in %r fires "
                    "on prose that says the opposite: %r"
                    % ([k for k in DISPUTING_KEYWORDS if k in note.lower()], note))
        for note in DISPUTING_NOTES:
            if not disputing(note):
                bad("the free floor reads a disputing note as settled -- no keyword matches: %r"
                    % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(ACCEPTING_NOTES) + len(DISPUTING_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own computation" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
