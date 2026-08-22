"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels

⚠︎ ON A SAFETY-ADJACENT KIT THIS FILE IS NOT A FORMALITY. Every number this kit publishes is a
claim about arithmetic, and the labels are that arithmetic. So the checks below do not trust the
generator's own variables at all -- the trail totals are RE-READ off the corpus text and re-summed
here, and every derived label is re-derived from the figures the document itself states.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                          # noqa: E402
from src.extract import compute as _compute            # noqa: E402
from src.extract import life_status as _life           # noqa: E402
from src.extract import tag_agreement as _tag          # noqa: E402
from src.extract import LIFE_STATUSES                  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ NO FIELD IN THIS CORPUS IS LEGITIMATELY NULL, and that is a property worth asserting rather
# than assuming: every pack states every figure, so a null in gold is a generator bug and a null in
# a reply is a miss. A kit with a nullable field says which one and why; this one has none.
NULLABLE = set()

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["rec_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate rec_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d document(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for rec_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (rec_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- no field in this corpus is nullable"
                % (f["name"], n_null))

    for rec_id, r in sorted(by_id.items()):
        for k in ("life_limit_hours", "life_limit_cycles", "tag_hours", "tag_cycles",
                  "trail_hours", "trail_cycles"):
            v = r.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                bad("%s: %s=%r is not a positive whole number" % (rec_id, k, v))

    # ⚑ THE CHECK THE WHOLE KIT RESTS ON: the trail total is RE-SUMMED off the document's own
    # stated periods, not taken from the generator. If a label is not recoverable by a reader with
    # nothing but the page, it is not a label, it is a second opinion.
    for rec_id, r in sorted(by_id.items()):
        text = EX.load_doc(rec_id)
        h = c = 0
        for m in re.finditer(r"accrued (\d+) hours / (\d+) cycles", text):
            h += int(m.group(1))
            c += int(m.group(2))
        if (h, c) != (r.get("trail_hours"), r.get("trail_cycles")):
            bad("%s: the periods the document states sum to %d/%d, gold says %s/%s"
                % (rec_id, h, c, r.get("trail_hours"), r.get("trail_cycles")))
        if ("accrual NOT RECORDED" in text) != (r.get("record_gap") == "yes"):
            bad("%s: the declared gap and the trail text disagree" % rec_id)

    # ⚑ GOLD MUST AGREE WITH ITS OWN ARITHMETIC. This is the check that makes the kit honest: the
    # label is not a second opinion about the tag, it is the comparison.
    disagree = [rec_id for rec_id, r in sorted(by_id.items())
                if _life(r.get("trail_hours"), r.get("trail_cycles"), r.get("life_limit_hours"),
                         r.get("life_limit_cycles"), r.get("record_gap")) != r.get("life_status")]
    if disagree:
        bad("%d gold row(s) label a life status their own figures do not support: %s"
            % (len(disagree), disagree[:5]))

    tag_bad = [rec_id for rec_id, r in sorted(by_id.items())
               if _tag(r.get("tag_hours"), r.get("tag_cycles"), r.get("trail_hours"),
                       r.get("trail_cycles")) != r.get("tag_agrees")]
    if tag_bad:
        bad("%d gold row(s) label a tag agreement their own figures do not support: %s"
            % (len(tag_bad), tag_bad[:5]))

    # ⚑ THE SHARPEST CASE, ASSERTED RATHER THAN TRUSTED: a declared gap must NOT be allowed to
    # override an exceedance the surviving records already establish. Every gapped row whose
    # surviving totals are at or past a limit must carry an exceeded status, never
    # `cannot_determine`.
    gap_rows = [r for r in by_id.values() if r.get("record_gap") == "yes"]
    gap_over = [r for r in gap_rows
                if r["trail_hours"] >= r["life_limit_hours"]
                or r["trail_cycles"] >= r["life_limit_cycles"]]
    wrong = [r["rec_id"] for r in gap_over if r["life_status"] == "cannot_determine"]
    if wrong:
        bad("%d gapped row(s) are already at or past a limit and still labelled "
            "cannot_determine: %s" % (len(wrong), wrong))
    elif not gap_over:
        bad("no gapped row exercises the exceedance-outranks-the-gap priority order -- the "
            "sharpest case in this corpus would go untested")
    else:
        print("  info  %d of %d gapped row(s) are ALREADY past a limit -- the case where the "
              "exceedance check outranks the gap check" % (len(gap_over), len(gap_rows)))

    # ⚑ THE BOUNDARY, ASSERTED: exactly at the published limit is exceeded, not within limits.
    on_boundary = [r for r in by_id.values()
                   if r["trail_hours"] == r["life_limit_hours"]
                   or r["trail_cycles"] == r["life_limit_cycles"]]
    boundary_bad = [r["rec_id"] for r in on_boundary if r["life_status"] == "within_limits"]
    if boundary_bad:
        bad("%d row(s) sit exactly ON a published limit and are still labelled within_limits: %s"
            % (len(boundary_bad), boundary_bad))
    elif not on_boundary:
        bad("no row sits exactly on a published limit -- the inclusive boundary is untested")
    else:
        print("  info  %d row(s) sit EXACTLY on a published limit, none of them within_limits"
              % len(on_boundary))

    # ⚑ THE OVERHAUL TRAP HAS TO BE PRESENT, and it has to be reachable: an overhaul line with no
    # accrual after it would not punish a reader who restarted the count there.
    overhaul = 0
    for rec_id in sorted(by_id):
        text = EX.load_doc(rec_id)
        if "overhaul completed" not in text:
            continue
        overhaul += 1
        after = text.split("overhaul completed", 1)[1]
        before = text.split("overhaul completed", 1)[0]
        if "accrued" not in before or "accrued" not in after:
            bad("%s: the overhaul line does not sit between two accruing periods, so restarting "
                "the count there would cost nothing" % rec_id)
    if not overhaul:
        bad("no row carries an overhaul line -- the reset-one-counter trap is untested")
    else:
        print("  info  %d row(s) carry an overhaul line with accruing periods on both sides"
              % overhaul)

    # ⚑ EVERY PACK'S PERIODS MUST RUN AT DIFFERENT HOURS-PER-CYCLE RATIOS, or the "sum them
    # separately" rule would be satisfied by scaling one total off the other.
    same_ratio = []
    for rec_id in sorted(by_id):
        pairs = re.findall(r"accrued (\d+) hours / (\d+) cycles", EX.load_doc(rec_id))
        ratios = {round(int(h) / float(c), 2) for h, c in pairs}
        if len(ratios) < len(pairs):
            same_ratio.append(rec_id)
    if same_ratio:
        bad("%d row(s) have two periods at the same hours-per-cycle ratio: %s"
            % (len(same_ratio), same_ratio[:5]))

    # Non-degeneracy: a grader whose truth is constant scores perfectly and means nothing.
    n_not_cleared = sum(1 for r in by_id.values() if r["life_status"] != "within_limits")
    if n_not_cleared in (0, len(by_id)):
        bad("gold has only one cleared/not-cleared class (%d of %d not cleared) -- the confusion "
            "matrix this kit exists to publish would be degenerate" % (n_not_cleared, len(by_id)))
    else:
        print("  info  %d of %d packs are NOT cleared by the trail; the five classes are %s"
              % (n_not_cleared, len(by_id),
                 ", ".join("%s=%d" % (s, sum(1 for r in by_id.values()
                                             if r["life_status"] == s))
                           for s in LIFE_STATUSES)))

    n_tag_no = sum(1 for r in by_id.values() if r["tag_agrees"] == "no")
    if n_tag_no in (0, len(by_id)):
        bad("gold's tag agreement is constant (%d of %d disagree)" % (n_tag_no, len(by_id)))
    else:
        print("  info  %d of %d tags disagree with the total the trail substantiates" % (n_tag_no,
                                                                                         len(by_id)))

    n_flag = sum(1 for r in by_id.values() if _compute(r))
    if n_flag in (0, len(by_id)):
        bad("the pure-code escalate flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d packs carry a discrepancy AND are up for return to service -- "
              "the escalate flag" % (n_flag, len(by_id)))

    # ⚑ THE REVIEWER NOTE MUST NEVER BE ABLE TO BE EVIDENCE. A note that stated a figure or a
    # status word would let a reader leaning on the note be right by accident, and the planted
    # ambiguity would stop measuring anything. Written into the gate from the start rather than
    # found live, on the lesson a sibling kit in this series paid for with four mis-registered
    # records.
    try:
        from tools.build_corpus import CALM_NOTES, WORRIED_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  note-register check skipped: %s" % exc)
    else:
        banned = ("hour", "cycle", "limit", "exceed", "within", "gap", "tag")
        for note in CALM_NOTES + WORRIED_NOTES:
            low = note.lower()
            if any(ch.isdigit() for ch in low):
                bad("a reviewer note states a figure and could be read as evidence: %r" % note)
            for w in banned:
                if w in low:
                    bad("a reviewer note states %r and could be read as evidence: %r" % (w, note))
        used = {r["reviewer_note"] for r in by_id.values()}
        if not used <= set(CALM_NOTES + WORRIED_NOTES):
            bad("gold carries a reviewer note that is not one of the declared templates")
        if not problems:
            print("  info  all %d note templates are free of figures and status words, so the "
                  "note can never be evidence about anything"
                  % (len(CALM_NOTES) + len(WORRIED_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d pack(s), %d field(s), gold consistent with the corpus text and with "
          "its own arithmetic" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
