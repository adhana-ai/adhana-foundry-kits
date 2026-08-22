"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                      # noqa: E402
from src.extract import CAUSES                     # noqa: E402
from src.extract import classify as _classify      # noqa: E402
from src.extract import compute as _compute        # noqa: E402
from src.extract import expected_invoiced as _exp  # noqa: E402
from src.extract import increment as _inc          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ NOTHING IN THIS CORPUS IS NULLABLE, AND THAT IS AN INVARIANT RATHER THAN AN ACCIDENT. Every
# quantity is stated on every record, including the zero ones -- a line with no unrated usage says
# "0", it does not omit the section. So "null anywhere in gold" is a defect, full stop, and there
# is no per-field nullable set to keep in step with the corpus generator.
QUANTITIES = ("mediated_quantity", "invoiced_quantity", "unrated_quantity",
              "prior_period_quantity", "confirmed_duplicate_quantity")

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
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
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- nothing in this corpus is nullable, a zero is "
                "stated as 0" % (f["name"], n_null))

    for line_ref, r in sorted(by_id.items()):
        for q in QUANTITIES:
            v = r.get(q)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                bad("%s: %s=%r is not a non-negative whole number" % (line_ref, q, v))
        if (r.get("mediated_quantity") or 0) <= 0:
            bad("%s: mediated_quantity is not positive" % line_ref)

    # ⚑ GOLD MUST AGREE WITH ITS OWN ARITHMETIC. This is the check that makes the whole kit honest:
    # the label is not a second opinion about the analyst's note, it is the classification.
    disagree = []
    for line_ref, r in sorted(by_id.items()):
        want = _classify(r.get("service_type"), r.get("mediated_quantity"),
                         r.get("invoiced_quantity"), r.get("unrated_quantity"),
                         r.get("prior_period_quantity"), r.get("confirmed_duplicate_quantity"))
        if want != r.get("variance_cause"):
            disagree.append(line_ref)
    if disagree:
        bad("%d gold row(s) label a cause their own quantities do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE BLOCKS MUST FIT INSIDE THE MEDIATED TOTAL. Written as an assertion rather than trusted
    # from the generator, because if it ever stops holding the arithmetic on the page is nonsense
    # (a negative billable quantity) while every score still computes cleanly.
    overflow = [s for s, r in by_id.items()
                if (r["unrated_quantity"] + r["prior_period_quantity"]
                    + r["confirmed_duplicate_quantity"]) > r["mediated_quantity"]]
    if overflow:
        bad("%d row(s) have blocks that do not fit inside the mediated total: %s"
            % (len(overflow), overflow[:5]))

    # ⚑ NO ROW MAY SATISFY TWO CAUSE BRANCHES. `duplicate_records` and `late_records` are told
    # apart only by WHICH block a positive gap matches, so two blocks within one increment of each
    # other make the label a coin toss that scores perfectly either way.
    ambiguous = []
    for line_ref, r in sorted(by_id.items()):
        inc = _inc(r.get("service_type"))
        d, p = r["confirmed_duplicate_quantity"], r["prior_period_quantity"]
        if d and p and abs(d - p) < inc:
            ambiguous.append(line_ref)
    if ambiguous:
        bad("%d row(s) carry a confirmed-duplicate block and a prior-period block within one "
            "increment of each other -- the same gap matches both branches: %s"
            % (len(ambiguous), ambiguous[:5]))

    # ⚑ SMS HAS NO ROUNDING TOLERANCE, ASSERTED RATHER THAN TRUSTED. The increment is one message,
    # so a `rounding` label on an SMS line would be a cause the rule cannot produce.
    sms_round = [s for s, r in by_id.items()
                 if r.get("service_type") == "sms" and r.get("variance_cause") == "rounding"]
    if sms_round:
        bad("%d SMS row(s) are labelled `rounding`, which the increment of 1 makes impossible: %s"
            % (len(sms_round), sms_round))
    else:
        n_sms = sum(1 for r in by_id.values() if r.get("service_type") == "sms")
        print("  info  %d SMS row(s), none of them labelled rounding -- the increment is 1 message"
              % n_sms)

    # ⚑ EVERY CAUSE MUST BE PRESENT, AND NONE MAY DOMINATE. A six-way grade whose corpus carries
    # four of the six is a four-way grade with two categories nobody measured.
    counts = {c: sum(1 for r in by_id.values() if r.get("variance_cause") == c) for c in CAUSES}
    absent = [c for c, n in counts.items() if n == 0]
    if absent:
        bad("%d cause(s) do not occur in gold at all: %s -- the six-way grade would be publishing "
            "categories nobody measured" % (len(absent), absent))
    else:
        print("  info  cause mix: %s" % "  ".join("%s=%d" % (c, counts[c]) for c in CAUSES))

    # ⚑ THE THREE PLANTED TRAPS, COUNTED. Each one is a number that ends up on the published page,
    # so it is measured here rather than asserted there.
    trap_a = sum(1 for r in by_id.values()
                 if r["prior_period_quantity"] > 0 and r["variance_cause"] == "none")
    trap_b = sum(1 for r in by_id.values() if r["variance_cause"] == "none"
                 and r["confirmed_duplicate_quantity"] == 0)
    trap_c = sum(1 for r in by_id.values()
                 if r["unrated_quantity"] > 0 and r["variance_cause"] == "none")
    if min(trap_a, trap_c) == 0:
        bad("a planted trap has no instances in gold (prior-period-and-correct=%d, "
            "unrated-and-correct=%d) -- the corpus is not testing what the page says it tests"
            % (trap_a, trap_c))
    else:
        print("  info  trap A: %d row(s) state prior-period usage and are still correctly invoiced"
              % trap_a)
        print("  info  trap C: %d row(s) carry unrated usage and are still correctly invoiced"
              % trap_c)

    # ⚑ AND THE SUSPECT/CONFIRMED GAP, which is trap B and is read off the DOCUMENT rather than off
    # gold -- the suspect figure is deliberately not an extracted field, so gold does not carry it.
    over = zeroed = 0
    for line_ref, r in sorted(by_id.items()):
        text = EX.load_doc(line_ref)
        import re
        m = re.search(r"Duplicate Suspects\n-+\n\s*(-?\d+)", text)
        if not m:
            bad("%s: no Duplicate Suspects section in the document" % line_ref)
            continue
        suspects = int(m.group(1))
        if suspects < r["confirmed_duplicate_quantity"]:
            bad("%s: the document flags fewer duplicate suspects (%d) than review confirmed (%d)"
                % (line_ref, suspects, r["confirmed_duplicate_quantity"]))
        if suspects > r["confirmed_duplicate_quantity"]:
            over += 1
            if r["confirmed_duplicate_quantity"] == 0:
                zeroed += 1
    print("  info  trap B: %d row(s) flag more duplicate suspects than review confirmed; %d "
          "confirmed none of them" % (over, zeroed))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"variance_cause": r.get("variance_cause"),
                              "invoice_status": r.get("invoice_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code credit flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d lines over-bill the customer AND the invoice is already issued -- "
              "the credit flag" % (n_flag, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the same lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside a calm note and mis-registered four records.
    #
    # ⚠︎ AND BECAUSE THIS FLOOR IS SIX-WAY RATHER THAN BINARY, ONE MORE THING IS CHECKED: that no
    # template matches TWO registers. A binary floor cannot have that failure; a five-entry keyword
    # table can, and it would show up as a silent dependence on the order of the table rather than
    # as a wrong answer anybody could see.
    try:
        from evals.baseline import NOTE_KEYWORDS, cause_from_note
        from tools.build_corpus import NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        n_templates = 0
        for register, templates in NOTES.items():
            for note in templates:
                n_templates += 1
                got = cause_from_note(note)
                if got != register:
                    bad("the free floor reads a %r note as %r: %r" % (register, got, note))
                low = note.lower()
                hits = [c for c, keys in NOTE_KEYWORDS if any(k in low for k in keys)]
                if len(hits) > 1:
                    bad("a note template matches %d registers (%s), so the floor's answer depends "
                        "on the order of its own keyword table: %r" % (len(hits), hits, note))
        if not problems:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as, and no template matches two" % n_templates)

    # ⚑ AND THE ROUNDING BOUNDARY, ASSERTED AT THE EDGE rather than trusted: for every row, a gap
    # of exactly one increment must NOT be classified as rounding, and a gap of one less must be.
    edge_bad = []
    for line_ref, r in sorted(by_id.items()):
        inc = _inc(r["service_type"])
        exp = _exp(r["service_type"], r["mediated_quantity"], r["prior_period_quantity"],
                   r["confirmed_duplicate_quantity"])
        if inc == 1:
            continue                                # no sub-increment gap exists on SMS
        inside = _classify(r["service_type"], r["mediated_quantity"], exp + inc - 1,
                           r["unrated_quantity"], r["prior_period_quantity"],
                           r["confirmed_duplicate_quantity"])
        at = _classify(r["service_type"], r["mediated_quantity"], exp + inc,
                       r["unrated_quantity"], r["prior_period_quantity"],
                       r["confirmed_duplicate_quantity"])
        if inside != "rounding" or at == "rounding":
            edge_bad.append(line_ref)
    if edge_bad:
        bad("%d row(s) do not respect the rounding boundary (a gap of increment-1 must be "
            "rounding, a gap of exactly the increment must not): %s" % (len(edge_bad), edge_bad[:5]))
    else:
        print("  info  the rounding boundary holds on every non-SMS row: a gap one unit under the "
              "increment is rounding, a gap of exactly the increment is not")

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d field(s), gold consistent with the corpus and with "
          "its own arithmetic" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
