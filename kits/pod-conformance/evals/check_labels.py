"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                     # noqa: E402
from src.extract import compute as _compute       # noqa: E402
from src.extract import is_complete as _ic        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ NOTHING IS NULLABLE IN THIS CORPUS, AND THAT IS A PROPERTY OF THE RECORD RATHER THAN A
# convenience. A proof-of-delivery scan either produced a value for a structured field or the
# delivery was never scanned; there is no equivalent here of the sibling kit's one-sided
# specification, where a null is the right answer. Every field is stated on every record, so a
# null anywhere in gold is a generator bug.
NULLABLE = set()

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

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- every field is stated on every record here"
                % (f["name"], n_null))

    for stmt_id, r in sorted(by_id.items()):
        for name in ("ordered_quantity", "delivered_quantity"):
            v = r.get(name)
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                bad("%s: %s=%r is not a positive whole number of units" % (stmt_id, name, v))

    # ⚑ GOLD MUST AGREE WITH ITS OWN COMPARISON. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the driver's note, it is the comparison.
    disagree = []
    for stmt_id, r in sorted(by_id.items()):
        want = _ic(r.get("delivered_quantity"), r.get("ordered_quantity"), r.get("condition_code"))
        if want != r.get("delivery_complete"):
            disagree.append(stmt_id)
    if disagree:
        bad("%d gold row(s) label a completeness their own quantities and condition code do not "
            "support: %s" % (len(disagree), disagree[:5]))

    # ⚑ THE SCAN TIMESTAMP MUST SIT ON THE DELIVERY DATE IT CLAIMS. Parsed here rather than
    # string-compared, so a timestamp that is a plausible-looking string and not a real instant
    # fails rather than passing on a prefix match.
    bad_ts = []
    for stmt_id, r in sorted(by_id.items()):
        try:
            d = datetime.date.fromisoformat(r.get("delivery_date") or "")
            ts = datetime.datetime.fromisoformat(r.get("pod_timestamp") or "")
        except ValueError:
            bad_ts.append(stmt_id)
            continue
        if ts.date() != d:
            bad_ts.append(stmt_id)
    if bad_ts:
        bad("%d row(s) have a pod_timestamp that is not a real instant on their own delivery "
            "date: %s" % (len(bad_ts), bad_ts[:5]))

    n_no = sum(1 for r in by_id.values() if r.get("delivery_complete") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one completeness class (%d yes, %d no) — the confusion matrix this "
            "kit exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d deliveries did not arrive as booked (delivery_complete=no)"
              % (n_no, len(by_id)))

    # The review flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"delivery_complete": r.get("delivery_complete"),
                              "recipient_signature_present":
                                  r.get("recipient_signature_present")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code review flag is constant across gold (%d of %d) — it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d records are incomplete AND unsigned — the review flag"
              % (n_flag, len(by_id)))
        over = sum(1 for r in by_id.values()
                   if r.get("delivered_quantity", 0) > r.get("ordered_quantity", 0))
        print("  info  %d record(s) delivered MORE units than were ordered — still not complete "
              "under the published rule" % over)

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so.
    #
    # ⚠︎ WHY IT EXISTS. evals/baseline.py decides completeness from the driver's note alone, and
    # the gap between that and a model is the number this kit publishes. That gap only means what
    # the page says it means if the floor actually detects the register the note was written in.
    # It did not: a keyword list containing "flagging" fired on a breezy note reading "nothing
    # worth flagging" -- a negation -- and mis-registered four records, TWO of which the corpus
    # had deliberately made ambiguous, so the bug returned the right answer for the wrong reason
    # and the floor's error count read 24 against a design of 22. Nothing would have caught that:
    # both numbers are plausible, and a floor scoring slightly worse than designed looks like a
    # floor working.
    #
    # So the property is asserted rather than inspected. Every note the generator can emit is
    # classified by the floor's own keyword list and must land on the register it was authored as.
    # Free, and it runs before anything spends.
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
                bad("the free floor reads an ANXIOUS note as calm -- no keyword matches: %r" % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(BREEZY_NOTES) + len(ANXIOUS_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own comparison" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
