"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                          # noqa: E402
from src.extract import compute as _compute            # noqa: E402
from src.extract import coverage_status as _cov        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ first_gap_party IS THE ONE NULLABLE FIELD IN THIS CORPUS, AND ITS NULLABILITY IS A RULE, NOT A
# CONVENIENCE: a fully covered package has no first gap, so it is null on exactly those packages
# and stated on every other one. That is checked directly below rather than folded into a generic
# per-field nullable set, because "null sometimes" is a weaker and less useful property than
# "null exactly when parties_uncovered is 0".
NULLABLE = {"first_gap_party"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["pkg_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate pkg_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for pkg_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (pkg_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only first_gap_party is nullable in this corpus"
                % (f["name"], n_null))

    # ⚑ THE NULLABILITY INVARIANT ITSELF, in both directions. Null iff nothing is uncovered.
    wrong_null = [s for s, r in by_id.items()
                  if (r.get("first_gap_party") is None) != (r.get("parties_uncovered") == 0)]
    if wrong_null:
        bad("%d row(s) have first_gap_party nullness that disagrees with parties_uncovered: %s"
            % (len(wrong_null), sorted(wrong_null)[:5]))
    wrong_none = [s for s, r in by_id.items()
                  if (r.get("first_gap_reason") == "none") != (r.get("parties_uncovered") == 0)]
    if wrong_none:
        bad("%d row(s) label first_gap_reason 'none' against a non-zero count, or a real reason "
            "against a zero one: %s" % (len(wrong_none), sorted(wrong_none)[:5]))

    for pkg_id, r in sorted(by_id.items()):
        n = r.get("parties_uncovered")
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            bad("%s: parties_uncovered=%r is not a whole number of zero or more" % (pkg_id, n))
        a = r.get("payment_amount_usd")
        if not isinstance(a, (int, float)) or isinstance(a, bool) or a <= 0:
            bad("%s: payment_amount_usd=%r is not a positive number" % (pkg_id, a))

    # ⚑ EVERY GOLD VALUE MUST BE STATED IN ITS OWN DOCUMENT. This is what stops gold being a
    # second opinion: a label nobody can read off the page is not a label, it is a claim.
    for pkg_id, r in sorted(by_id.items()):
        text = EX.load_doc(pkg_id)
        for field in ("package_id", "project_name", "pay_app_number", "period_through",
                      "prior_payment_cleared", "release_status", "coordinator_note"):
            if r.get(field) not in text:
                bad("%s: gold %s is not stated in the document" % (pkg_id, field))
        if r.get("first_gap_party") and r["first_gap_party"] not in text:
            bad("%s: gold first_gap_party is not a party the document lists" % pkg_id)
        if format(r["payment_amount_usd"], ",.2f") not in text:
            bad("%s: gold payment_amount_usd is not stated verbatim" % pkg_id)

    # ⚑ THE RULE ITSELF, ASSERTED RATHER THAN TRUSTED. Every reason gold uses must be a reason
    # src/extract.py's own coverage_status() can produce, and both halves of the two sharpest
    # cases must be present in the corpus at all.
    reasons = {}
    for r in by_id.values():
        reasons[r["first_gap_reason"]] = reasons.get(r["first_gap_reason"], 0) + 1
    unknown = set(reasons) - set(EX.GAP_REASONS) - {"none"}
    if unknown:
        bad("gold uses gap reason(s) the rule cannot produce: %s" % sorted(unknown))
    for reason in EX.GAP_REASONS:
        if not reasons.get(reason):
            bad("no gold row exercises the %r branch of the coverage rule -- a rule branch with "
                "no rows is an untested rule branch" % reason)
    print("  info  first-gap reasons in gold: %s"
          % "  ".join("%s=%d" % (k, v) for k, v in sorted(reasons.items())))

    # ⚑ THE SHARPEST CASE, ASSERTED DIRECTLY: a FINAL waiver can never be period_short, because
    # it carries no through-date. Re-run the rule over a synthetic final waiver whose through-date
    # is absent and whose everything else is fine, and it must come back covered.
    if _cov("unconditional_final", 100.0, None, "2026-01-05", None, 100.0, "2026-06-30",
            "no", "no") != "covered":
        bad("the rule reports a gap on a FINAL waiver with no through-date -- final waivers "
            "cover all work through completion and can never be period_short")
    # And the joint-check route: a conditional waiver on a joint-check party is stale even when
    # the package says the prior payment has NOT cleared.
    if _cov("conditional_progress", 100.0, "2026-06-30", "2026-07-02", None, 100.0, "2026-06-30",
            "no", "yes") != "conditional_stale":
        bad("the rule does not treat a joint check as clearing on issue -- a conditional waiver "
            "on a joint-check party must be stale even when the prior payment has not cleared")
    # And the priority order: notice-after-waiver outranks a perfectly good waiver.
    if _cov("unconditional_progress", 1000.0, "2026-12-31", "2026-01-10", "2026-02-20", 100.0,
            "2026-06-30", "no", "no") != "notice_after_waiver":
        bad("the rule lets a full-amount, in-period, unconditional waiver cover a claim asserted "
            "after it was signed -- notice_after_waiver must outrank everything below it")
    # And period outranks amount.
    if _cov("unconditional_progress", 10.0, "2026-05-31", "2026-06-25", None, 100.0,
            "2026-06-30", "no", "no") != "period_short":
        bad("the rule reports amount_short where the through-date already stops inside the "
            "period -- period_short outranks amount_short")

    n_gap = sum(1 for r in by_id.values() if r["parties_uncovered"] > 0)
    n_clear = len(by_id) - n_gap
    if n_gap == 0 or n_clear == 0:
        bad("gold has only one coverage class (%d clear, %d with a gap) -- the confusion matrix "
            "this kit exists to publish would be degenerate" % (n_clear, n_gap))
    else:
        print("  info  %d of %d packages carry at least one uncovered party" % (n_gap, len(by_id)))
        n_two = sum(1 for r in by_id.values() if r["parties_uncovered"] > 1)
        print("  info  %d of those carry TWO -- so the count field is not a disguised boolean"
              % n_two)
        if n_two == 0:
            bad("no package carries more than one uncovered party -- parties_uncovered would be "
                "a boolean wearing a number's type, and its exact-count grade would mean nothing")

    # The hold flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"parties_uncovered": r.get("parties_uncovered"),
                              "release_status": r.get("release_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code hold flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d packages have a gap AND are scheduled for release -- the hold flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the same lesson a sibling kit in this series paid for live:
    # its first keyword list fired on a negation inside a breezy note and mis-registered four
    # records. Every note template here is checked against the floor's own keyword list before
    # any run may spend.
    try:
        from evals.baseline import WORRIED_KEYWORDS
        from tools.build_corpus import ANXIOUS_NOTES, BREEZY_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def worried(note):
            return any(k in note.lower() for k in WORRIED_KEYWORDS)
        for note in BREEZY_NOTES:
            if worried(note):
                bad("the free floor reads a BREEZY note as worried -- a keyword in %r fires on "
                    "prose that says the opposite: %r"
                    % ([k for k in WORRIED_KEYWORDS if k in note.lower()], note))
        for note in ANXIOUS_NOTES:
            if not worried(note):
                bad("the free floor reads a worried note as settled -- no keyword matches: %r"
                    % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(BREEZY_NOTES) + len(ANXIOUS_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "the coverage rule it was written by" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
