"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                     # noqa: E402
from src.extract import compute as _compute       # noqa: E402
from src.extract import is_rate_correct as _irc    # noqa: E402
from src.extract import correct_rate_code as _crc  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ peak_demand_kw IS THE ONE NULLABLE FIELD IN THIS CORPUS, AND ITS NULLABILITY IS A RULE, NOT A
# CONVENIENCE: Residential accounts are not demand-metered, so it is null on every Residential row
# and stated on every other one. That is checked directly below rather than folded into a generic
# per-field nullable set, because "null sometimes" is a weaker and less useful property than
# "null exactly when service_class is Residential".
NULLABLE = {"peak_demand_kw"}

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
            bad("%s is null in %d gold row(s) -- only peak_demand_kw is nullable in this corpus"
                % (f["name"], n_null))

    # ⚑ THE NULLABILITY INVARIANT ITSELF. Null iff Residential; a value on every other row.
    wrong_null = [s for s, r in by_id.items()
                  if (r.get("peak_demand_kw") is None) != (r.get("service_class") == "Residential")]
    if wrong_null:
        bad("%d row(s) have peak_demand_kw nullness that disagrees with service_class=='Residential': "
            "%s" % (len(wrong_null), sorted(wrong_null)[:5]))

    for stmt_id, r in sorted(by_id.items()):
        v = r.get("metered_usage_kwh")
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            bad("%s: metered_usage_kwh=%r is not a positive whole number" % (stmt_id, v))
        d = r.get("peak_demand_kw")
        if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d <= 0):
            bad("%s: peak_demand_kw=%r is not a positive whole number or null" % (stmt_id, d))

    # ⚑ GOLD MUST AGREE WITH ITS OWN COMPARISON. This is the check that makes the whole kit
    # honest: the label is not a second opinion about the account note, it is the comparison.
    disagree = []
    for stmt_id, r in sorted(by_id.items()):
        want = _irc(r.get("applied_rate_code"), r.get("service_class"), r.get("meter_type"),
                   r.get("metered_usage_kwh"), r.get("peak_demand_kw"))
        if want != r.get("rate_correct"):
            disagree.append(stmt_id)
    if disagree:
        bad("%d gold row(s) label a correctness their own structured values do not support: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE SHARPEST CASE, ASSERTED RATHER THAN TRUSTED: every interval-metered row at or above
    # 15,000 kWh must compute to TOU-8 regardless of its demand reading, even when demand alone
    # would look like a GS-2 case.
    override_bad = []
    for stmt_id, r in sorted(by_id.items()):
        if r.get("meter_type") == "interval" and (r.get("metered_usage_kwh") or 0) >= 15000:
            if _crc(r.get("service_class"), r.get("meter_type"), r.get("metered_usage_kwh"),
                   r.get("peak_demand_kw")) != "TOU-8":
                override_bad.append(stmt_id)
    if override_bad:
        bad("%d row(s) are interval-metered at >= 15000 kWh but the rule did not compute TOU-8: %s"
            % (len(override_bad), override_bad[:5]))
    else:
        n_override = sum(1 for r in by_id.values()
                         if r.get("meter_type") == "interval"
                         and (r.get("metered_usage_kwh") or 0) >= 15000)
        print("  info  %d row(s) exercise the TOU-8-outranks-demand override" % n_override)

    # ⚑ THE BOUNDARY, ASSERTED: exactly 50 kW qualifies for GS-2, not GS-1.
    n_at_50 = sum(1 for r in by_id.values() if r.get("peak_demand_kw") == 50)
    at_50_wrong = [s for s, r in by_id.items()
                  if r.get("peak_demand_kw") == 50
                  and _crc(r.get("service_class"), r.get("meter_type"),
                          r.get("metered_usage_kwh"), r.get("peak_demand_kw")) != "GS-2"]
    if at_50_wrong:
        bad("%d row(s) at exactly 50 kW did not compute to GS-2: %s" % (len(at_50_wrong), at_50_wrong))
    else:
        print("  info  %d row(s) sit exactly on the 50 kW boundary, all correctly GS-2" % n_at_50)

    n_no = sum(1 for r in by_id.values() if r.get("rate_correct") == "no")
    n_yes = len(by_id) - n_no
    if n_no == 0 or n_yes == 0:
        bad("gold has only one correctness class (%d yes, %d no) -- the confusion matrix this kit "
            "exists to publish would be degenerate" % (n_yes, n_no))
    else:
        print("  info  %d of %d accounts are misrated (rate_correct=no)" % (n_no, len(by_id)))

    # The review flag has to be non-degenerate too, for exactly the same reason.
    n_flag = sum(1 for r in by_id.values()
                 if _compute({"rate_correct": r.get("rate_correct"),
                             "bill_status": r.get("bill_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code review flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d records are misrated AND already sent -- the review flag"
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
                bad("the free floor reads a concerned note as calm -- no keyword matches: %r" % note)
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
