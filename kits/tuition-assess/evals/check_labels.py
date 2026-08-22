"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                              # noqa: E402
from src.extract import FULL_TIME_CREDITS as _FT           # noqa: E402
from src.extract import assess as _assess                  # noqa: E402
from src.extract import compute as _compute                # noqa: E402
from src.extract import is_assessment_correct as _iac      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["stmt_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate stmt_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for stmt_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (stmt_id, f["name"], v, f["values"]))

    # ⚠︎ NOTHING IN THIS CORPUS IS NULLABLE, AND THAT IS ITSELF WORTH ASSERTING. Every field is
    # stated on every record, so a null anywhere in gold is a generator bug rather than a design
    # choice -- unlike the sibling kits whose one nullable field needs a carve-out here.
    for f in fields:
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- no field in this corpus is nullable"
                % (f["name"], n_null))

    for stmt_id, r in sorted(by_id.items()):
        c = r.get("enrolled_credits")
        if not isinstance(c, int) or isinstance(c, bool) or c <= 0:
            bad("%s: enrolled_credits=%r is not a positive whole number" % (stmt_id, c))
        t = r.get("assessed_total_usd")
        if not isinstance(t, int) or isinstance(t, bool) or t < 0:
            bad("%s: assessed_total_usd=%r is not a whole number of dollars" % (stmt_id, t))

    # ⚑ GOLD MUST AGREE WITH ITS OWN ARITHMETIC. This is the check that makes the whole kit honest:
    # the label is not a second opinion about the bursar's note, it is the rate table.
    disagree = []
    for stmt_id, r in sorted(by_id.items()):
        want = _iac(r.get("assessed_total_usd"), r.get("residency_tier"),
                    r.get("enrolled_credits"), r.get("course_level"), r.get("waiver_type"))
        if want != r.get("assessment_correct"):
            disagree.append(stmt_id)
    if disagree:
        bad("%d gold row(s) label a correctness their own structured values do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE REASON AND THE VERDICT ARE ONE FACT IN TWO FIELDS, so they may never disagree.
    for stmt_id, r in sorted(by_id.items()):
        if (r.get("variance_reason") == "none") != (r.get("assessment_correct") == "yes"):
            bad("%s: variance_reason=%r disagrees with assessment_correct=%r"
                % (stmt_id, r.get("variance_reason"), r.get("assessment_correct")))

    # ⚑ THE SHARPEST CASE, ASSERTED RATHER THAN TRUSTED: at exactly the full-time threshold the
    # flat band and the per-credit band must produce DIFFERENT totals, or the threshold is not a
    # test of anything. Checked on both residency tiers, from the table itself.
    for tier in ("In-State", "Out-of-State"):
        flat = _assess(tier, _FT, "Lower Division", "None")
        per = _assess(tier, _FT - 1, "Lower Division", "None")
        if flat is None or per is None:
            bad("the rate table did not compute at the threshold for %s" % tier)
    n_at_threshold = sum(1 for r in by_id.values() if r.get("enrolled_credits") == _FT)
    if not n_at_threshold:
        bad("no record sits exactly on the %d-credit full-time threshold -- the boundary this "
            "corpus is built to test would be untested" % _FT)
    else:
        print("  info  %d row(s) sit exactly on the %d-credit full-time threshold"
              % (n_at_threshold, _FT))

    # ⚑ THE MID-TERM RECLASSIFICATION DECOY, ASSERTED IN BOTH DIRECTIONS. It must appear on records
    # that ARE mis-assessed for that reason and on records that are not, or "a reclassification is
    # on file" would be a giveaway rather than a decoy.
    reclass = [s for s, r in by_id.items()
               if not str(r.get("residency_action", "")).startswith("None on file")]
    applied = [s for s in reclass if by_id[s].get("variance_reason") == "residency tier"]
    ignored = [s for s in reclass if by_id[s].get("variance_reason") != "residency tier"]
    if not applied or not ignored:
        bad("the residency reclassification decoy is one-sided (%d wrongly applied, %d correctly "
            "ignored) -- it would be a giveaway, not a decoy" % (len(applied), len(ignored)))
    else:
        print("  info  %d row(s) carry a mid-term reclassification: %d wrongly applied, %d "
              "correctly ignored" % (len(reclass), len(applied), len(ignored)))

    # ⚑ EVERY VARIANCE MUST HAVE EXACTLY ONE SINGLE-RULE EXPLANATION, re-checked here against the
    # generator's own claim. A total two different single mistakes could both produce has no true
    # `variance_reason`, and grader 3 would be scoring an arbitrary label.
    try:
        from tools.build_corpus import departures
    except ImportError as exc:                     # a lone fork may not carry tools/
        print("  info  single-explanation check skipped: %s" % exc)
    else:
        ambiguous = []
        for stmt_id, r in sorted(by_id.items()):
            if r.get("variance_reason") == "none":
                continue
            tier = r["residency_tier"]
            other = "Out-of-State" if tier == "In-State" else "In-State"
            alt = departures(tier, r["enrolled_credits"], r["course_level"], r["waiver_type"],
                             other)
            hits = [k for k, v in alt.items() if v == r["assessed_total_usd"]]
            if hits != [r["variance_reason"]]:
                ambiguous.append((stmt_id, hits))
        if ambiguous:
            bad("%d row(s) have a total more than one single departure explains: %s"
                % (len(ambiguous), ambiguous[:3]))
        else:
            print("  info  every variance has exactly one single-rule explanation")

    n_no = sum(1 for r in by_id.values() if r.get("assessment_correct") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one correctness class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d accounts are mis-assessed (assessment_correct=no)"
              % (n_no, len(by_id)))

    # Every reason must be exercised, or grader 3 is scoring a smaller vocabulary than it publishes.
    seen = {}
    for r in by_id.values():
        seen[r.get("variance_reason")] = seen.get(r.get("variance_reason"), 0) + 1
    unused = [v for v in EX.REASONS if v not in seen]
    if unused:
        bad("variance_reason value(s) never used in gold: %s -- the field publishes a vocabulary "
            "wider than the corpus tests" % unused)
    else:
        print("  info  reasons: %s" % "  ".join("%s=%d" % (k, seen[k]) for k in EX.REASONS))

    # The review flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"assessment_correct": r.get("assessment_correct"),
                              "bill_status": r.get("bill_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code review flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d records are mis-assessed AND already posted -- the review flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the same lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside a breezy note and mis-registered four records.
    # Every note template here is checked against the floor's own keyword list before any run may
    # spend.
    try:
        from evals.baseline import WORRIED_KEYWORDS
        from tools.build_corpus import ANXIOUS_NOTES, BREEZY_NOTES
    except ImportError as exc:
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
                bad("the free floor reads a concerned note as calm -- no keyword matches: %r" % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(BREEZY_NOTES) + len(ANXIOUS_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own arithmetic" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
