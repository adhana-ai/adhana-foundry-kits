"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                      # noqa: E402
from src import rulebook as RB                     # noqa: E402
from src import segment, select as selector        # noqa: E402
from src.extract import compute as _compute        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# Floors, so each hard case is MEASURED rather than anecdotal. Every one of these is a reading a
# careless reviewer falls into on its own.
MIN_PRICED_SILENT = 40        # a fee of its own, nothing said -> not_determined
MIN_FREE_BUT_DISTINCT = 10    # priced at nothing and still distinct
MIN_FREE_BUNDLED = 20         # priced at nothing, nothing said -> bundled
MIN_WITHDRAWN = 8             # a struck line whose clause is still in the pack
MIN_RATE_CARD = 8
MIN_CARRYOVER = 8

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    ifields = {f["name"]: f for f in fields["fields"]}
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["contract_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate contract_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))
    missing = docs - set(by_id)
    if missing:
        bad("%d pack(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no pack: %s" % (len(orphan), sorted(orphan)[:5]))

    all_items = [(cid, o) for cid, r in sorted(by_id.items()) for o in r["obligations"]]

    # ---- every value in the allowed vocabulary, and nothing null --------------------------------
    for cid, o in all_items:
        for name, f in ifields.items():
            v = o.get(name)
            if v is None or v == "":
                bad("%s/%s: %s is null -- no field is nullable in this corpus"
                    % (cid, o.get("item_code"), name))
            elif f.get("values") and v not in f["values"]:
                bad("%s/%s: %s=%r is not one of %s"
                    % (cid, o.get("item_code"), name, v, f["values"]))

    # ---- ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK LOOKUP ---------------------------------------
    # This is the check that makes the whole kit honest: the label is not somebody's opinion about
    # a contract, it is the shipped rulebook run over the three facts the pack states.
    disagree = []
    for cid, o in all_items:
        d = RB.decide(o["charge"], o["dependency"], o["timing"])
        if d["separation"] != o["separation"] or d["pattern"] != o["pattern"]:
            disagree.append("%s/%s" % (cid, o["item_code"]))
    if disagree:
        bad("%d gold line(s) label a call their own facts do not produce: %s"
            % (len(disagree), disagree[:5]))

    # ---- ⚑ EVERY GOLD VALUE MUST BE READABLE OFF THE PACK IT LABELS ----------------------------
    for cid in sorted(by_id):
        text = EX.load_doc(cid)
        g = by_id[cid]
        if g["contract_id"] not in text:
            bad("%s: contract_id is not stated in its own pack" % cid)
        codes = {o["item_code"] for o in g["obligations"]}
        for o in g["obligations"]:
            if o["item_code"] not in text or o["item_label"] not in text:
                bad("%s/%s: the line is not stated in its own pack" % (cid, o["item_code"]))
        for d in g.get("decoys") or []:
            if d["item_code"] in codes:
                bad("%s: decoy %s collides with an ordered line" % (cid, d["item_code"]))
            if d["item_code"] not in text:
                bad("%s: decoy %s is not in the pack at all" % (cid, d["item_code"]))

    # ---- ⚑ THE HARD CASES, ASSERTED RATHER THAN TRUSTED ----------------------------------------
    priced_silent = [(c, o) for c, o in all_items
                     if o["charge"] == "separate_fee" and o["dependency"] == "silent"]
    for c, o in priced_silent:
        if o["separation"] != "not_determined":
            bad("%s/%s: a priced line with nothing said about separability must be "
                "not_determined, gold says %r" % (c, o["item_code"], o["separation"]))
    if len(priced_silent) < MIN_PRICED_SILENT:
        bad("only %d line(s) pair a fee of their own with silence about separability -- the "
            "over-confidence trap needs at least %d to be measured rather than anecdotal"
            % (len(priced_silent), MIN_PRICED_SILENT))
    else:
        print("  info  %d line(s) carry a fee of their own and say NOTHING about separability -- "
              "the paperwork does not settle them" % len(priced_silent))

    free_distinct = [(c, o) for c, o in all_items
                     if o["charge"] == "no_separate_charge" and o["separation"] == "distinct"]
    for c, o in free_distinct:
        if o["dependency"] != "separately_available":
            bad("%s/%s: a free line is only distinct when the contract SAYS it can be taken "
                "alone" % (c, o["item_code"]))
    if len(free_distinct) < MIN_FREE_BUT_DISTINCT:
        bad("only %d line(s) are priced at nothing and still distinct -- the case where the money "
            "column and the answer point opposite ways needs at least %d"
            % (len(free_distinct), MIN_FREE_BUT_DISTINCT))
    else:
        print("  info  %d line(s) are priced at NOTHING and are still distinct" % len(free_distinct))

    free_bundled = [(c, o) for c, o in all_items
                    if o["charge"] == "no_separate_charge" and o["dependency"] == "silent"]
    for c, o in free_bundled:
        if o["separation"] != "bundled":
            bad("%s/%s: a free line with nothing said must be bundled on this rulebook, gold says "
                "%r" % (c, o["item_code"], o["separation"]))
    if len(free_bundled) < MIN_FREE_BUNDLED:
        bad("only %d line(s) are priced at nothing with nothing said -- one clause away from the "
            "case above, and it needs at least %d" % (len(free_bundled), MIN_FREE_BUNDLED))
    else:
        print("  info  %d line(s) are priced at nothing with nothing said -- bundled, one clause "
              "away from the case above" % len(free_bundled))

    kinds = {}
    for r in by_id.values():
        for d in r.get("decoys") or []:
            kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    for kind, floor in (("withdrawn", MIN_WITHDRAWN), ("rate_card", MIN_RATE_CARD),
                        ("carryover", MIN_CARRYOVER)):
        if kinds.get(kind, 0) < floor:
            bad("only %d %r decoy(s) -- the phantom-obligation grader needs at least %d of each "
                "kind to say anything" % (kinds.get(kind, 0), kind, floor))
    if not problems:
        print("  info  decoys: %s (%d codes that must NOT reach a worksheet)"
              % ("  ".join("%s=%d" % kv for kv in sorted(kinds.items())), sum(kinds.values())))

    # ---- ⚑ NO GRADER MAY BE DEGENERATE ---------------------------------------------------------
    for call, allowed in (("separation", RB.SEPARATIONS), ("pattern", RB.PATTERNS)):
        counts = {}
        for _c, o in all_items:
            counts[o[call]] = counts.get(o[call], 0) + 1
        for v in allowed:
            if not counts.get(v):
                bad("gold has no %r rows for %s -- that grader would be degenerate" % (v, call))
        print("  info  %-10s %s" % (call + ":",
                                    "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in allowed)))

    n_flag = sum(1 for r in by_id.values() if _compute(r["obligations"]))
    if n_flag in (0, len(by_id)):
        bad("the pure-code review flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d packs carry a PRICED line whose separation AND delivery pattern "
              "the paperwork settles neither of -- the review flag" % (n_flag, len(by_id)))
        for cid, r in by_id.items():
            if _compute(r["obligations"]) != r["needs_drafting_review"]:
                bad("%s: gold's needs_drafting_review disagrees with compute() over its own lines"
                    % cid)

    # ---- ⚑ SELECTION MUST SEND THE DECOYS AND MUST NOT SEND THE CUSTOMER ------------------------
    # Both halves, because each fails silently in the opposite direction: dropping a decoy section
    # would mark the model's homework for it, and sending the customer section would put a named
    # account and a billing reference on the wire for no field at all.
    for cid in sorted(by_id):
        secs = segment.sections(EX.load_doc(cid))
        sent = {s["name"] for s in selector.sent(secs)}
        present = {s["name"] for s in secs}
        for never in selector.NEVER_SENT:
            if never in sent:
                bad("%s: section %r reaches the model and no field asks for it" % (cid, never))
        for needed in (selector.RATE_CARD, selector.CARRYOVER, selector.NOTES):
            if needed in present and needed not in sent:
                bad("%s: section %r is in the pack and is NOT sent -- the identification grader "
                    "would be measuring selection, not the model" % (cid, needed))
    if not problems:
        print("  info  selection sends every decoy section and never sends %s"
              % ", ".join(selector.NEVER_SENT))

    # ---- ⚑ THE FREE FLOOR MUST BE A FAITHFUL READER OF BOTH REGISTERS --------------------------
    # Written in from the start, on the lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside the opposite register and mis-classified four
    # records for days.
    try:
        from evals.baseline import (PREREQ_STEMS, SEPARABLE_STEMS, PERIOD_STEMS, EVENT_STEMS)
        from tools.build_corpus import (PREREQ_SENTENCES, SEPARABLE_SENTENCES,
                                        PERIOD_SENTENCES, EVENT_SENTENCES, TERM_MONTHS)
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def hits(text, stems):
            low = text.lower()
            return [s for s in stems if s in low]

        prereq = [s for group in PREREQ_SENTENCES.values() for s in group]
        period = [t % m for t in PERIOD_SENTENCES for m in TERM_MONTHS]
        checks = [("prerequisite", prereq, PREREQ_STEMS,
                   [SEPARABLE_STEMS, PERIOD_STEMS, EVENT_STEMS]),
                  ("separable", SEPARABLE_SENTENCES, SEPARABLE_STEMS,
                   [PREREQ_STEMS, PERIOD_STEMS, EVENT_STEMS]),
                  ("period", period, PERIOD_STEMS,
                   [PREREQ_STEMS, SEPARABLE_STEMS, EVENT_STEMS]),
                  ("event", EVENT_SENTENCES, EVENT_STEMS,
                   [PREREQ_STEMS, SEPARABLE_STEMS, PERIOD_STEMS])]
        for label, sentences, own, others in checks:
            for s in sentences:
                if not hits(s, own):
                    bad("the free floor reads a %s sentence as stating nothing -- no keyword "
                        "matches: %r" % (label, s))
                for other in others:
                    if hits(s, other):
                        bad("the free floor reads a %s sentence in the wrong register -- %r fires "
                            "on %r" % (label, hits(s, other), s))
        if not problems:
            print("  info  the free floor classifies all %d sentence templates to the register "
                  "they were written in"
                  % (len(prereq) + len(SEPARABLE_SENTENCES) + len(period) + len(EVENT_SENTENCES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d pack(s), %d line(s), %d field(s) -- gold consistent with the corpus "
          "and with its own rulebook lookup"
          % (len(docs), len(all_items), len(ifields)))


if __name__ == "__main__":
    main()
