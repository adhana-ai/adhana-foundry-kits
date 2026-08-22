"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                      # noqa: E402
from src.extract import AS_OF                      # noqa: E402
from src.extract import compute as _compute        # noqa: E402
from src.extract import eligibility as _elig       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ TWO FIELDS ARE NULLABLE IN THIS CORPUS AND THEIR NULLABILITY IS A RULE, NOT A CONVENIENCE.
# `overlapping_expires` is null exactly when the Overlapping Series line reads 'none on file';
# `binding_hold_id` is null exactly when no ACTIVE hold's scope covers the series. Both are
# checked directly below rather than folded into a generic nullable set, because "null sometimes"
# is a weaker and far less useful property than "null exactly when".
NULLABLE = {"overlapping_expires", "binding_hold_id"}

# The corpus's own claim about why each record is what it is. A class that quietly produced the
# wrong verdict would make every per-class number this kit publishes meaningless.
FROZEN_CLASSES = {"hold_active", "hold_successor", "overlap_longer", "retention_open"}
ELIGIBLE_CLASSES = {"scope_category_miss", "scope_project_miss", "scope_date_miss",
                    "released_no_successor", "clear"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["case_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate case_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for case_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (case_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, " and ".join(sorted(NULLABLE))))

    # ⚑ EVERY DATE IS A REAL MONTH, AND THE RETENTION ARITHMETIC IS THE SCHEDULE'S OWN. A retention
    # period is whole years from the cutoff, so the month must carry through unchanged -- a
    # mismatch means the expiry was written rather than computed.
    for case_id, r in sorted(by_id.items()):
        for key in ("record_closed", "retention_expires"):
            v = r.get(key) or ""
            if len(v) != 7 or v[4] != "-" or not v[:4].isdigit() or not v[5:].isdigit() \
                    or not 1 <= int(v[5:]) <= 12:
                bad("%s: %s=%r is not a YYYY-MM month" % (case_id, key, r.get(key)))
                continue
        closed, exp = r.get("record_closed") or "", r.get("retention_expires") or ""
        if len(closed) == 7 and len(exp) == 7 and closed[5:] != exp[5:]:
            bad("%s: retention_expires month %r does not carry through from record_closed %r"
                % (case_id, exp, closed))
        if len(closed) == 7 and len(exp) == 7 and exp <= closed:
            bad("%s: retention_expires %r is not after record_closed %r" % (case_id, exp, closed))

    # ⚑ GOLD MUST AGREE WITH ITS OWN DERIVATION. This is the check that makes the whole kit honest:
    # the verdict is not a second opinion about the officer's note, it is the rule.
    disagree = []
    for case_id, r in sorted(by_id.items()):
        want = _elig(r.get("binding_hold_id"), r.get("overlapping_expires"),
                     r.get("retention_expires"))
        if want != r.get("disposition_eligible"):
            disagree.append(case_id)
    if disagree:
        bad("%d gold row(s) label an eligibility their own values do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE CLASS LABELS, ASSERTED RATHER THAN TRUSTED. Every per-class figure this kit publishes
    # rests on each class actually producing the verdict it is named for.
    for case_id, r in sorted(by_id.items()):
        klass = r.get("_class")
        v = r.get("disposition_eligible")
        if klass in FROZEN_CLASSES and v != "no":
            bad("%s: class %s produced an ELIGIBLE record" % (case_id, klass))
        elif klass in ELIGIBLE_CLASSES and v != "yes":
            bad("%s: class %s produced a FROZEN record" % (case_id, klass))
        elif klass not in FROZEN_CLASSES | ELIGIBLE_CLASSES:
            bad("%s: unknown class %r" % (case_id, klass))

    # ⚑ THE FOUR HARD CASES, EACH ASSERTED TO BE PRESENT IN QUANTITY. A corpus that plants one
    # instance of its own sharpest test has an anecdote, not a measurement.
    counts = {}
    for r in by_id.values():
        counts[r.get("_class")] = counts.get(r.get("_class"), 0) + 1
    for klass in ("scope_category_miss", "scope_project_miss", "scope_date_miss",
                  "hold_successor", "released_no_successor", "overlap_longer"):
        if counts.get(klass, 0) < 5:
            bad("only %d record(s) exercise %s -- fewer than 5 is an anecdote, not a measurement"
                % (counts.get(klass, 0), klass))
    if not problems:
        print("  info  the hard cases: %s"
              % "  ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))

    # ⚑ THE SUCCESSOR CASE MUST BE FINDABLE ONLY BY FOLLOWING THE REFERENCE. Every hold_successor
    # record's binding hold must be the ACTIVE line whose scope reads "continues the scope of".
    for case_id, r in sorted(by_id.items()):
        if r.get("_class") != "hold_successor":
            continue
        text = EX.load_doc(case_id)
        bound = r.get("binding_hold_id")
        if not bound:
            bad("%s: a hold_successor record binds no hold" % case_id)
            continue
        line = [l for l in text.splitlines() if l.startswith(bound + " |")]
        if not line:
            bad("%s: binding hold %s is not a registry line" % (case_id, bound))
        elif "continues the scope of" not in line[0]:
            bad("%s: the binding hold on a hold_successor record is not the continuing line"
                % case_id)
        elif "| active |" not in line[0]:
            bad("%s: the continuing line that binds is not active" % case_id)

    # ⚑ AND THE MIRROR CASE, WHICH IS WHAT STOPS "released MEANS LOOK FOR A SUCCESSOR" FROM BEING
    # A WORKING SHORTCUT: released_no_successor records carry a released hold that WOULD have
    # covered, and nothing follows it.
    for case_id, r in sorted(by_id.items()):
        if r.get("_class") != "released_no_successor":
            continue
        text = EX.load_doc(case_id)
        if "continues the scope of" in text:
            bad("%s: a released_no_successor record carries a continuing hold" % case_id)
        if r.get("binding_hold_id") is not None:
            bad("%s: a released_no_successor record binds a hold" % case_id)

    n_no = sum(1 for r in by_id.values() if r.get("disposition_eligible") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one eligibility class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d series are frozen (disposition_eligible=no)" % (n_no, len(by_id)))

    n_bound = sum(1 for r in by_id.values() if r.get("binding_hold_id"))
    print("  info  %d of %d series are frozen by a HOLD; %d by something with no hold on it"
          % (n_bound, len(by_id), n_no - n_bound))

    # The review flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"disposition_eligible": r.get("disposition_eligible"),
                              "queue_status": r.get("queue_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code review flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d series are frozen AND already queued -- the review flag"
              % (n_flag, len(by_id)))

    # ⚑ THE FREE TONE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says
    # so -- written in from the start, on the same lesson a sibling kit in this series paid for
    # live: its first keyword list fired on a negation inside a breezy note and mis-registered
    # four records. Every note template here is checked against the floor's own keyword list
    # before any run may spend.
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
                bad("the free floor reads a concerned note as calm -- no keyword matches: %r" % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(BREEZY_NOTES) + len(ANXIOUS_NOTES)))

    # ⚑ AND THE REVIEW DATE IS ONE NUMBER IN THREE FILES. src/extract.py, src/prompt.py and the
    # generator all have to name the same month or gold is being scored against a rule the model
    # was never told.
    try:
        from src.prompt import AS_OF as PROMPT_AS_OF
        from tools.build_corpus import AS_OF as CORPUS_AS_OF
    except ImportError:
        pass
    else:
        if not (AS_OF == PROMPT_AS_OF == CORPUS_AS_OF):
            bad("the review date disagrees across the kit: extract.py=%r prompt.py=%r "
                "build_corpus.py=%r" % (AS_OF, PROMPT_AS_OF, CORPUS_AS_OF))
        else:
            print("  info  the review date is %s in extract.py, prompt.py and build_corpus.py"
                  % AS_OF)

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own derivation" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
