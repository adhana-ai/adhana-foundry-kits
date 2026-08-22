"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                          # noqa: E402
from src.extract import compute as _compute            # noqa: E402
from src.extract import coverage_verdict as _cv        # noqa: E402
from src.extract import months_between as _months      # noqa: E402
from evals.judge import deciding_branch as _branch     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ NOTHING IS NULLABLE IN THIS CORPUS, AND THAT IS AN ASSERTION RATHER THAN AN ASSUMPTION. Every
# one of the thirteen fields is stated on every claim, which is what lets evals/judge.py treat a
# `miss` as a real miss instead of a legitimately-absent value.
NULLABLE = set()

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

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- nothing in this corpus is nullable"
                % (f["name"], n_null))

    for claim_ref, r in sorted(by_id.items()):
        for name in ("months_in_service", "odometer_miles"):
            v = r.get(name)
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                bad("%s: %s=%r is not a positive whole number" % (claim_ref, name, v))

    # ⚑ THE DATE ARITHMETIC MUST AGREE WITH ITS OWN TWO DATES. This is the check that makes the
    # boundary cases honest: months_in_service is not a number somebody typed, it is the
    # calculation, and if the label and the calculation disagree then six of the records this
    # corpus is built around are testing nothing.
    date_bad = []
    for claim_ref, r in sorted(by_id.items()):
        if _months(r.get("in_service_date"), r.get("repair_date")) != r.get("months_in_service"):
            date_bad.append(claim_ref)
        try:
            a = datetime.date.fromisoformat(r["in_service_date"])
            b = datetime.date.fromisoformat(r["repair_date"])
            if b <= a:
                bad("%s: repair_date is not after in_service_date" % claim_ref)
        except (KeyError, TypeError, ValueError):
            bad("%s: a date is unreadable" % claim_ref)
    if date_bad:
        bad("%d gold row(s) state a months_in_service their own two dates do not produce: %s"
            % (len(date_bad), date_bad[:5]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULE. This is the check that makes the whole kit honest: the
    # label is not a second opinion about the technician's narrative, it is the six-branch rule.
    disagree = []
    for claim_ref, r in sorted(by_id.items()):
        want = _cv(r.get("coverage_plan"), r.get("months_in_service"), r.get("odometer_miles"),
                   r.get("failed_component"), r.get("claimed_labor_op"),
                   r.get("narrative_finding"))
        if want != r.get("covered"):
            disagree.append(claim_ref)
    if disagree:
        bad("%d gold row(s) label a coverage their own values do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ EVERY BRANCH OF THE RULE MUST ACTUALLY BE EXERCISED, AND BY MORE THAN ONE ROW. A six-branch
    # rule whose sharpest branch is tested by a single record is not measured, it is anecdotal.
    branches = {}
    for r in by_id.values():
        branches[_branch(r)] = branches.get(_branch(r), 0) + 1
    for name in ("exclusion", "labor_op", "wear", "component_list", "limit_exceeded",
                 "inside_terms"):
        if branches.get(name, 0) < 2:
            bad("branch %r is exercised by %d row(s) -- fewer than two is anecdote, not "
                "measurement" % (name, branches.get(name, 0)))
    print("  info  deciding branch: %s"
          % "  ".join("%s=%d" % (k, branches[k]) for k in sorted(branches)))

    # ⚑ THE SHARPEST CASE, ASSERTED RATHER THAN TRUSTED: every row past 36 months AND 36,000 miles
    # that gold still calls covered must be on a plan whose own limit is longer than the
    # bumper-to-bumper one. That is the "reach for the 3/36 and get it wrong" case, counted.
    beats_basic = [s for s, r in by_id.items()
                   if r.get("covered") == "yes"
                   and (r.get("months_in_service") or 0) > 36
                   and (r.get("odometer_miles") or 0) > 36000]
    wrong_plan = [s for s in beats_basic if by_id[s].get("coverage_plan") == "basic"]
    if wrong_plan:
        bad("%d covered row(s) are past 36/36,000 on a BASIC plan, which the rule cannot produce: "
            "%s" % (len(wrong_plan), wrong_plan[:5]))
    else:
        print("  info  %d covered row(s) are past 36 months AND 36,000 miles -- the "
              "reach-for-the-3/36 trap" % len(beats_basic))

    # ⚑ THE INCLUSIVE BOUNDARY, ASSERTED: a row EXACTLY on its plan's month or mileage limit is
    # inside the term.
    exact = []
    for s, r in by_id.items():
        lim = EX.PLANS.get(r.get("coverage_plan")) or {}
        if r.get("months_in_service") == lim.get("months") \
                or r.get("odometer_miles") == lim.get("miles"):
            exact.append(s)
    exact_wrong = [s for s in exact if by_id[s].get("covered") != "yes"]
    if exact_wrong:
        bad("%d row(s) sit exactly on a limit and are not covered -- the limit is inclusive: %s"
            % (len(exact_wrong), exact_wrong[:5]))
    else:
        print("  info  %d row(s) sit EXACTLY on a month or mileage limit, all covered" % len(exact))

    # ⚑ THE WEAR EXCEPTION MUST CUT BOTH WAYS, or it teaches "wear item, therefore no".
    wear_yes = sum(1 for r in by_id.values()
                   if r.get("failed_component") in EX.WEAR_PARTS and r.get("covered") == "yes")
    wear_no = sum(1 for r in by_id.values()
                  if r.get("failed_component") in EX.WEAR_PARTS and r.get("covered") == "no")
    if wear_yes < 2 or wear_no < 2:
        bad("the wear-item exception is one-sided (%d covered, %d denied) -- a reader who answers "
            "'wear item, therefore no' would score perfectly on it" % (wear_yes, wear_no))
    else:
        print("  info  %d wear-item claim(s) covered as premature failures, %d denied"
              % (wear_yes, wear_no))

    # ⚑ THE CODED CAUSE MUST DISAGREE WITH THE NARRATED FINDING ON A MEASURED NUMBER OF ROWS, IN
    # BOTH DIRECTIONS.
    cause_for = {"defect": "defect", "collision_damage": "damage",
                 "unauthorized_modification": "modification",
                 "missed_maintenance": "maintenance"}
    excl_as_defect = [s for s, r in by_id.items()
                      if r.get("narrative_finding") in EX.EXCLUSIONS
                      and r.get("cause_code") == "defect"]
    defect_as_other = [s for s, r in by_id.items()
                       if r.get("narrative_finding") == "defect"
                       and r.get("cause_code") != "defect"]
    if not excl_as_defect or not defect_as_other:
        bad("the coded-cause confusion is one-directional (%d exclusions coded 'defect', %d plain "
            "defects coded otherwise) -- a reader who learns 'the coded field is always wrong' "
            "would be no worse off than one who trusts it"
            % (len(excl_as_defect), len(defect_as_other)))
    else:
        print("  info  %d exclusion(s) coded 'defect', %d plain defect(s) coded otherwise -- %d "
              "rows where the coded cause disagrees with the narrative"
              % (len(excl_as_defect), len(defect_as_other),
                 sum(1 for r in by_id.values()
                     if r.get("cause_code") != cause_for.get(r.get("narrative_finding")))))

    n_no = sum(1 for r in by_id.values() if r.get("covered") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one coverage class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d claims are not covered" % (n_no, len(by_id)))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"covered": r.get("covered"),
                              "claim_status": r.get("claim_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code recovery flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d claims are not covered AND already paid -- the recovery flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the same lesson a sibling kit in this series paid for live:
    # its first keyword list fired on a negation inside a positive note and mis-registered four
    # records. Every opinion template here is checked against the floor's own keyword list before
    # any run may spend.
    try:
        from evals.baseline import DENIAL_KEYWORDS
        from tools.build_corpus import OPINION_ANTI, OPINION_PRO
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def denies(op):
            return any(k in op.lower() for k in DENIAL_KEYWORDS)
        for op in OPINION_PRO:
            if denies(op):
                bad("the free floor reads a PRO-coverage opinion as a denial -- a keyword in %r "
                    "fires on prose that says the opposite: %r"
                    % ([k for k in DENIAL_KEYWORDS if k in op.lower()], op))
        for op in OPINION_ANTI:
            if not denies(op):
                bad("the free floor reads a denial-sounding opinion as positive -- no keyword "
                    "matches: %r" % op)
        if not problems:
            print("  info  the free floor classifies all %d opinion templates to the register "
                  "they were written as" % (len(OPINION_PRO) + len(OPINION_ANTI)))

    # ⚑ AND THE TWO COPIES OF THE COVERAGE TERMS MUST AGREE. src/extract.py restates PLANS,
    # PLAN_COMPONENTS and LABOR_OPS so a fork that drops tools/ still runs; that is a second copy,
    # and a second copy with no check is a drift waiting to be published.
    try:
        from tools import build_corpus as BC
    except ImportError as exc:
        print("  info  terms cross-check skipped: %s" % exc)
    else:
        for name, a, b in (("PLANS", EX.PLANS, BC.PLANS),
                           ("PLAN_COMPONENTS", EX.PLAN_COMPONENTS, BC.PLAN_COMPONENTS),
                           ("LABOR_OPS", EX.LABOR_OPS, BC.LABOR_OPS),
                           ("WEAR_PARTS", sorted(EX.WEAR_PARTS), sorted(BC.WEAR_PARTS))):
            if a != b:
                bad("%s in src/extract.py disagrees with tools/build_corpus.py -- the corpus and "
                    "the guardrail would be applying different coverage terms" % name)
        if EX.EARLY_MONTHS != BC.EARLY_MONTHS or EX.EARLY_MILES != BC.EARLY_MILES:
            bad("the wear-item early-failure window disagrees between src/ and tools/")

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d claim(s), %d field(s), gold consistent with the corpus, with its own "
          "date arithmetic and with its own rule" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
