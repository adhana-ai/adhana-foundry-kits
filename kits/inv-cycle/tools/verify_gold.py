#!/usr/bin/env python3
"""Assert that data/gold.jsonl was DERIVED, never typed. For every event, re-run
src/segment.py::classify() on its own log and variance_qty and check the result -- cause,
citations, and the confirmed_note's own claimed cause -- against what tools/build_corpus.py wrote.
A mismatch here means some scenario builder planted a flag that classify()'s precedence order
doesn't actually resolve the way the builder assumed, which is exactly the class of bug this
script exists to catch before the corpus ships.

    python3 tools/verify_gold.py

Exits 1 and prints every disagreement found; exits 0 and prints a one-line pass otherwise.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")

from src import segment as SEG                                 # noqa: E402
from tools.build_corpus import confirmed_note                    # noqa: E402


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def main():
    events = {e["event_id"]: e for e in _read_jsonl(os.path.join(DATA, "events.jsonl"))}
    gold = _read_jsonl(os.path.join(DATA, "gold.jsonl"))

    problems = []
    for g in gold:
        eid = g["event_id"]
        event = events.get(eid)
        if not event:
            problems.append("%s: no matching event in events.jsonl" % eid)
            continue

        fx = SEG.classify(event)          # re-derive, from scratch, from the log alone
        if fx["cause"] != g["cause"]:
            problems.append("%s: gold cause %r != re-derived cause %r"
                            % (eid, g["cause"], fx["cause"]))
        if fx["citations"] != g["citations"]:
            problems.append("%s: gold citations %r != re-derived citations %r"
                            % (eid, g["citations"], fx["citations"]))

        # Every non-'unresolved' citation must ACTUALLY support the derived cause -- the same
        # rule evals/scoring.py grades a live model's citations by, checked here against gold's
        # own citations so a planted flag can never silently point at the wrong line.
        for idx in fx["citations"]:
            if not SEG.line_supports_cause(event, idx, fx["cause"]):
                problems.append("%s: citation %d does not actually support cause %r"
                                % (eid, idx, fx["cause"]))

        # The confirmed_note -- the narrative's own claimed cause -- is templated FROM the
        # derived cause and citation, not hand-typed. CONFIRM_TEMPLATES is keyed by cause, so
        # regenerating it the identical way and requiring byte-equality is what proves the stored
        # note actually names the cause classify() reached, rather than some other one typed by
        # hand: a wrong template pick or a hand-edited note would fail this line.
        expected_note = confirmed_note(fx["cause"], event, fx["citations"])
        if expected_note != g["confirmed_note"]:
            problems.append("%s: gold confirmed_note does not match a fresh re-derivation"
                            % eid)

        # is_trap must itself be a derived property, never a separately-typed flag.
        expected_trap = (fx["cause"] == "unrecorded_transfer"
                        and SEG.is_case_pack_multiple(event["variance_qty"]))
        if bool(g.get("is_trap")) != expected_trap:
            problems.append("%s: gold is_trap=%r != re-derived %r"
                            % (eid, g.get("is_trap"), expected_trap))

    if problems:
        print("FAIL -- %d disagreement(s) between data/gold.jsonl and a fresh re-derivation:\n"
             % len(problems))
        for p in problems:
            print("  - %s" % p)
        sys.exit(1)

    print("OK -- all %d gold rows match a fresh classify() re-derivation from their own "
         "transaction history log and variance_qty." % len(gold))


if __name__ == "__main__":
    main()
