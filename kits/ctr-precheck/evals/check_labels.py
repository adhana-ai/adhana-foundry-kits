"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import rulebook as RB                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402
from src.extract import defect_set as _defect_set   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ FIVE NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   linked_record_id                  null where the log says every entry is booked to one record.
#   missing_identification_elements   null where all five required elements are on the draft.
#   miscoded_transaction_ids          null where every included entry carries the log's own code.
#   log_qualifying_total              null where a qualifying amount was NEVER CAPTURED -- and that
#                                     is exactly the `insufficient_information` class, so the
#                                     invariant below is two-way.
#   identification_captured_on        nullable by schema; never null on this corpus, and the check
#                                     below says so rather than assuming it.
NULLABLE = {"linked_record_id", "missing_identification_elements", "miscoded_transaction_ids",
            "log_qualifying_total"}

# Each seeded defect class needs a floor, so that a run's score on it is measured rather than
# anecdotal. Three is the smallest number this estate treats as a measurement.
MIN_PER_DEFECT = 3
# The false-alarm rate is the number this kit leads with, so its denominator gets a bigger floor:
# a rate over six rows moves 17 points per row and is not a number anybody should quote.
MIN_CLEAN = 12

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
        bad("%d pack(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no pack: %s" % (len(orphan), sorted(orphan)[:5]))

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
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ EVERY DEFECT CODE IN GOLD MUST BE ONE THE SHIPPED RULEBOOK CARRIES. A code the rulebook has
    # never heard of would be scored against a vocabulary the model was never shown, silently.
    for case_id, r in sorted(by_id.items()):
        s = _defect_set(r.get("defects_found"))
        if s is None:
            bad("%s: gold carries no defect answer at all -- a clean filing must say 'none'"
                % case_id)
            continue
        raw = [p.strip() for p in str(r["defects_found"]).split(",") if p.strip()]
        if raw != ["none"] and len(s) != len(raw):
            bad("%s: gold names a defect code the rulebook does not carry: %r"
                % (case_id, r["defects_found"]))

    # ⚑ THE NULLABILITY INVARIANT, BOTH WAYS: an uncomputable total is exactly the
    # insufficient_information class, and nothing else produces one on this corpus.
    wrong_ii = [s for s, r in by_id.items()
                if (r.get("log_qualifying_total") is None)
                != (_defect_set(r.get("defects_found")) == {"insufficient_information"})]
    if wrong_ii:
        bad("%d row(s) where a null qualifying total and defects=='insufficient_information' "
            "disagree: %s" % (len(wrong_ii), sorted(wrong_ii)[:5]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK PASS. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the preparer's note, it is the rulebook.
    disagree = []
    for case_id, r in sorted(by_id.items()):
        want = sorted(RB.assess(r["draft_reported_total"], r["log_qualifying_total"],
                                r["draft_window_applied"], r["linked_record_id"],
                                r["draft_includes_linked_record"],
                                r["missing_identification_elements"],
                                r["identification_captured_on"], r["gaming_day"],
                                r["miscoded_transaction_ids"])["defects"])
        got = sorted(_defect_set(r.get("defects_found")) or set())
        if want != got:
            disagree.append(case_id)
    if disagree:
        bad("%d gold row(s) name a defect list their own values do not produce: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ EVERY SEEDED DEFECT CLASS NEEDS A FLOOR, ASSERTED RATHER THAN TRUSTED.
    counts = {}
    for r in by_id.values():
        for c in (_defect_set(r.get("defects_found")) or set()):
            counts[c] = counts.get(c, 0) + 1
    for c in RB.DEFECTS:
        n = counts.get(c, 0)
        if n < MIN_PER_DEFECT:
            bad("only %d row(s) carry %r -- a defect class needs at least %d to be measured rather "
                "than anecdotal" % (n, c, MIN_PER_DEFECT))
    print("  info  seeded defects: %s"
          % "  ".join("%s=%d" % (c, counts.get(c, 0)) for c in RB.DEFECTS))

    # ⚑ THE CLEAN BUCKET IS THE FALSE-ALARM DENOMINATOR AND IT IS CHECKED HARDEST.
    clean = [s for s, r in by_id.items() if not (_defect_set(r.get("defects_found")) or set())]
    if len(clean) < MIN_CLEAN:
        bad("only %d clean pack(s) -- the false-alarm rate this kit leads with needs a denominator "
            "of at least %d, or one row moves it further than anybody should quote"
            % (len(clean), MIN_CLEAN))
    else:
        print("  info  %d clean pack(s) -- the false-alarm rate's denominator, %.1f points a row"
              % (len(clean), 100.0 / len(clean)))

    # ⚑ AND EVERY CLEAN PACK MUST CARRY FALSE-ALARM BAIT, OR THE RATE MEASURES NOTHING. A clean
    # pack whose log holds nothing but the entries on the draft is a pack no checker could get
    # wrong, and eighteen of those would publish a flattering zero that says nothing at all.
    unbaited = []
    for case_id in sorted(clean):
        r = by_id[case_id]
        text = EX.load_doc(case_id)
        log = text.split("Cage Transaction Log")[-1].split("Other Patron Records")[0]
        included = text.split("Transactions Included On The Draft")[-1]
        included = included.split("Patron Identification")[0]
        log_ids = {line.split()[0] for line in log.splitlines()
                   if line.strip().startswith("TXN-")}
        draft_ids = {line.split()[0] for line in included.splitlines()
                     if line.strip().startswith("TXN-")}
        if not (log_ids - draft_ids) and not r.get("linked_record_id"):
            unbaited.append(case_id)
    if unbaited:
        bad("%d clean pack(s) carry no false-alarm bait at all -- nothing in the log that a "
            "careless checker could mistake for a missed aggregation: %s"
            % (len(unbaited), unbaited[:5]))
    else:
        print("  info  every clean pack carries at least one entry the draft correctly left out")

    # ⚑ NO GRADER MAY BE DEGENERATE. A recompute flag that is constant would score perfectly and
    # mean nothing.
    n_flag = sum(1 for r in by_id.values() if _compute({"defects_found": r.get("defects_found")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code recompute flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d packs need the totals recomputed before anyone submits"
              % (n_flag, len(by_id)))

    n_arith = sum(1 for r in by_id.values()
                  if r["log_qualifying_total"] is not None
                  and r["log_qualifying_total"] != r["draft_reported_total"])
    if n_arith < MIN_PER_DEFECT:
        bad("only %d pack(s) have a qualifying total that differs from the drafted one -- the "
            "arithmetic grade would be measuring nothing" % n_arith)
    else:
        print("  info  %d pack(s) have a qualifying total the draft does not state, so the "
              "arithmetic cell cannot be answered by copying" % n_arith)

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the lesson a sibling kit in this series paid for live: its first
    # keyword list fired on a negation inside a relaxed note and mis-registered four rows.
    try:
        from evals.baseline import ANXIOUS_KEYWORDS
        from tools.build_corpus import CONFIDENT_NOTES, ANXIOUS_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def anxious(note):
            return any(k in note.lower() for k in ANXIOUS_KEYWORDS)
        for note in CONFIDENT_NOTES:
            if anxious(note):
                bad("the free floor reads a CONFIDENT note as anxious -- a keyword in %r fires on "
                    "prose that says the opposite: %r"
                    % ([k for k in ANXIOUS_KEYWORDS if k in note.lower()], note))
        for note in ANXIOUS_NOTES:
            if not anxious(note):
                bad("the free floor reads an anxious note as confident -- no keyword matches: %r"
                    % note)
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(CONFIDENT_NOTES) + len(ANXIOUS_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d pack(s), %d field(s), gold consistent with the corpus and with its own "
          "rulebook pass" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
