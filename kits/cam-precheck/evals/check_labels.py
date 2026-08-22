"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                          # noqa: E402
from src.extract import compute as _compute            # noqa: E402
from src.rule import (MATERIALITY_USD, TOLERANCE_USD,  # noqa: E402
                      line_is_ok as _ok, permitted_amount as _permitted)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ SIX OF THE TWENTY FIELDS ARE NULLABLE IN THIS CORPUS, AND EVERY ONE OF THEM IS NULLABLE BY A
# RULE RATHER THAN BY CONVENIENCE. Each rule is asserted directly below rather than folded into a
# generic "these may be null" set, because "null sometimes" is a weaker and far less useful
# property than "null exactly when the lease says there is nothing to state".
NULLABLE = {"amortization_years", "expansion_area_sf", "expansion_month",
            "cap_pct", "cap_basis_usd", "cap_years"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def _gold_permitted(r):
    return _permitted(r.get("expense_class"), r.get("pool_gross_usd"),
                      r.get("amortization_years"), r.get("occupancy_sensitive"),
                      r.get("building_occupancy_pct"), r.get("building_area_sf"),
                      r.get("tenant_area_sf"), r.get("expansion_area_sf"),
                      r.get("expansion_month"), r.get("cap_type"), r.get("cap_pct"),
                      r.get("cap_basis_usd"), r.get("cap_years"))


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(line) for line in open(GOLD, encoding="utf-8") if line.strip()]
    by_id = {r["line_ref"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate line_ref in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for line_ref, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (line_ref, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ THE SIX NULLABILITY INVARIANTS, EACH STATED AS AN IFF RATHER THAN AS A TOLERANCE.
    amort_wrong = [s for s, r in by_id.items()
                   if r.get("amortization_years") is not None
                   and r.get("expense_class") != "capital_improvement"]
    if amort_wrong:
        bad("%d row(s) state an amortization term on a line that is not a capital improvement: %s"
            % (len(amort_wrong), sorted(amort_wrong)[:5]))

    exp_wrong = [s for s, r in by_id.items()
                 if (r.get("expansion_area_sf") is None) != (r.get("expansion_month") is None)]
    if exp_wrong:
        bad("%d row(s) state an expansion area without a month, or the reverse: %s"
            % (len(exp_wrong), sorted(exp_wrong)[:5]))

    for field in ("cap_pct", "cap_basis_usd"):
        wrong = [s for s, r in by_id.items()
                 if (r.get(field) is None) != (r.get("cap_type") == "none")]
        if wrong:
            bad("%d row(s) have %s nullness that disagrees with cap_type: %s"
                % (len(wrong), field, sorted(wrong)[:5]))

    years_wrong = [s for s, r in by_id.items()
                   if (r.get("cap_years") is not None) != (r.get("cap_type") == "cumulative")]
    if years_wrong:
        bad("%d row(s) state cap_years on a cap that does not compound, or omit it on one that "
            "does: %s" % (len(years_wrong), sorted(years_wrong)[:5]))

    for line_ref, r in sorted(by_id.items()):
        for field in ("pool_gross_usd", "building_area_sf", "tenant_area_sf",
                      "building_occupancy_pct"):
            v = r.get(field)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                bad("%s: %s=%r is not a positive number" % (line_ref, field, v))
        if r.get("tenant_area_sf", 0) >= r.get("building_area_sf", 0):
            bad("%s: the tenant's area is not smaller than the building's" % line_ref)
        if r.get("billed_to_tenant_usd") is None or r.get("billed_to_tenant_usd") < 0:
            bad("%s: billed_to_tenant_usd=%r is negative or absent"
                % (line_ref, r.get("billed_to_tenant_usd")))
        m = r.get("expansion_month")
        if m is not None and not (1 <= m <= 12):
            bad("%s: expansion_month=%r is outside 1-12" % (line_ref, m))

    # ⚑ GOLD MUST AGREE WITH ITS OWN ARITHMETIC. This is the check that makes the whole kit
    # honest: `permitted_amount_usd` is not a second opinion about the line, it is the four stages
    # run over the values the line itself states, and `line_ok` is the comparison.
    amount_disagree, verdict_disagree, immaterial = [], [], []
    for line_ref, r in sorted(by_id.items()):
        want = _gold_permitted(r)
        # ⚠︎ `r.get(...) or -1` WOULD BE A BUG HERE AND WAS ONE FOR ABOUT A MINUTE. A permitted
        # amount of 0.00 is the CORRECT answer on every correctly-excluded line -- seven of these
        # 55 -- and `0.0 or -1` is -1, so the falsy-default spelling convicted all seven as gold
        # disagreeing with its own arithmetic. A zero here is a value, not an absence.
        stated = r.get("permitted_amount_usd")
        if want is None or stated is None or abs(want - stated) > 0.005:
            amount_disagree.append(line_ref)
            continue
        if _ok(r.get("billed_to_tenant_usd"), want) != r.get("line_ok"):
            verdict_disagree.append(line_ref)
        elif r.get("line_ok") == "no" and \
                abs(r["billed_to_tenant_usd"] - want) < MATERIALITY_USD:
            immaterial.append(line_ref)
    if amount_disagree:
        bad("%d gold row(s) carry a permitted amount their own values do not produce: %s"
            % (len(amount_disagree), amount_disagree[:5]))
    if verdict_disagree:
        bad("%d gold row(s) label a verdict their own comparison does not support: %s"
            % (len(verdict_disagree), verdict_disagree[:5]))
    if immaterial:
        bad("%d 'no' row(s) are wrong by less than the %.2f USD materiality floor -- their labels "
            "would be a coin flip on the last cent: %s"
            % (len(immaterial), MATERIALITY_USD, immaterial[:5]))

    # ⚑ THE SHARPEST CASES, ASSERTED RATHER THAN TRUSTED.
    amortized = [r for r in by_id.values()
                 if r.get("expense_class") == "capital_improvement" and r.get("amortization_years")]
    partly_billable = [r for r in amortized if (r.get("permitted_amount_usd") or 0) > 0]
    if len(partly_billable) != len(amortized):
        bad("%d amortizable capital row(s) compute to a permitted amount of zero -- an amortizable "
            "capital item is PARTLY billable and the corpus's whole point is that middle case"
            % (len(amortized) - len(partly_billable)))
    else:
        print("  info  %d row(s) are amortizable capital -- partly billable, neither zero nor the "
              "whole cost" % len(amortized))

    binds_after = [s for s, r in by_id.items() if r.get("_shape") == "cap_binds_after_grossup"]
    for line_ref in binds_after:
        r = by_id[line_ref]
        ungrossed = _permitted(r["expense_class"], r["pool_gross_usd"], r["amortization_years"],
                               "no", r["building_occupancy_pct"], r["building_area_sf"],
                               r["tenant_area_sf"], r["expansion_area_sf"], r["expansion_month"],
                               "none", None, None, None)
        grossed = _permitted(r["expense_class"], r["pool_gross_usd"], r["amortization_years"],
                             r["occupancy_sensitive"], r["building_occupancy_pct"],
                             r["building_area_sf"], r["tenant_area_sf"], r["expansion_area_sf"],
                             r["expansion_month"], "none", None, None, None)
        ceiling = r["permitted_amount_usd"]
        if not (ungrossed < ceiling < grossed):
            bad("%s is labelled cap_binds_after_grossup but its ceiling %.2f does not sit between "
                "the ungrossed share %.2f and the grossed-up share %.2f"
                % (line_ref, ceiling, ungrossed, grossed))
    if binds_after and not problems:
        print("  info  %d row(s) carry a cap that has slack before the gross-up and binds after "
              "it -- the sharpest records in this corpus" % len(binds_after))

    decoys = [r for r in by_id.values() if r.get("_decoy_category")]
    bad_decoys = [r for r in decoys if r.get("expense_class") != "routine_operating"]
    if bad_decoys:
        bad("%d decoy-category row(s) are not routine_operating -- the decoy is a NAME on a line "
            "that is genuinely billable, or it is not a decoy" % len(bad_decoys))
    else:
        print("  info  %d row(s) carry an expense category whose NAME reads excludable on a line "
              "whose class says routine_operating" % len(decoys))

    n_no = sum(1 for r in by_id.values() if r.get("line_ok") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one verdict class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        over = sum(1 for r in by_id.values()
                   if r.get("line_ok") == "no"
                   and r["billed_to_tenant_usd"] > r["permitted_amount_usd"])
        print("  info  %d of %d lines are billed wrong (%d overcharges, %d undercharges)"
              % (n_no, len(by_id), over, n_no - over))

    # The review flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"line_ok": r.get("line_ok"),
                              "statement_status": r.get("statement_status"),
                              "billed_to_tenant_usd": r.get("billed_to_tenant_usd"),
                              "permitted_amount_usd": r.get("permitted_amount_usd")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code review flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d lines are overbilled AND already issued -- the review flag. That "
              "is a SMALL denominator and it is named here rather than hidden: one miss moves "
              "recall by %.1f points" % (n_flag, len(by_id), 100.0 / n_flag))

    # ⚑ BOTH FREE FLOORS MUST BE FAITHFUL DETECTORS OF THE THING THEY SHORT-CUT, and this is the
    # check that says so -- written in from the start, on the same lesson a sibling kit in this
    # series paid for live: its first keyword list fired on a negation inside a breezy note and
    # mis-registered four records. A floor that fails for a reason other than its own shortcut is
    # not a floor, it is a bug being published as a finding.
    try:
        from evals.baseline import WORRIED_KEYWORDS, name_says_excluded
        from tools.build_corpus import (BREEZY_NOTES, CAPITAL_CATEGORIES, CONCERNED_NOTES,
                                        DECOY_OPERATING, LEASING_CATEGORIES,
                                        OVERHEAD_CATEGORIES, PLAIN_OPERATING)
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  floor-fidelity check skipped: %s" % exc)
    else:
        def worried(note):
            return any(k in note.lower() for k in WORRIED_KEYWORDS)
        for note in BREEZY_NOTES:
            if worried(note):
                bad("the tone floor reads a BREEZY note as worried -- a keyword in %r fires on "
                    "prose that says the opposite: %r"
                    % ([k for k in WORRIED_KEYWORDS if k in note.lower()], note))
        for note in CONCERNED_NOTES:
            if not worried(note):
                bad("the tone floor reads a concerned note as calm -- no keyword matches: %r" % note)

        for cat in CAPITAL_CATEGORIES + OVERHEAD_CATEGORIES + LEASING_CATEGORIES + DECOY_OPERATING:
            if not name_says_excluded(cat):
                bad("the name floor does not read %r as excludable -- it must, or the floor is "
                    "failing for a reason other than its own shortcut" % cat)
        for cat in PLAIN_OPERATING:
            if name_says_excluded(cat):
                bad("the name floor reads the plainly-operating category %r as excludable -- its "
                    "keyword list is over-broad and its failures would not be the decoy's" % cat)
        if not problems:
            print("  info  both free floors are faithful: %d note templates classify to the "
                  "register they were written as, and %d expense categories to the family they "
                  "were authored in"
                  % (len(BREEZY_NOTES) + len(CONCERNED_NOTES),
                     len(CAPITAL_CATEGORIES + OVERHEAD_CATEGORIES + LEASING_CATEGORIES
                         + DECOY_OPERATING + PLAIN_OPERATING)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d line(s), %d field(s), gold consistent with the corpus and with its own "
          "arithmetic (tolerance %.2f USD, materiality %.2f USD)"
          % (len(docs), len(fields), TOLERANCE_USD, MATERIALITY_USD))


if __name__ == "__main__":
    main()
