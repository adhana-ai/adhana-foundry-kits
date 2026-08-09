#!/usr/bin/env python3
"""What you get without a model. Run this BEFORE reading any score the kit produces.

    python3 -m evals.baseline

⚑ THE FLOOR COMES FIRST, ALWAYS. A decision accuracy means nothing until you know what guessing
scores, and on an intake task the guess is not 50/50: these conversations end the moment the
checklist fills, so the two answers are not equally common. Publishing a model number without the
floor beside it is how a task that a constant beats gets reported as a success.

⚠︎ AND ON THIS KIT THE FLOOR ALREADY CHANGED THE CORPUS. Taking every user turn gave a case set
that was 75% already-complete, where "always stop" scored 75% while reading nothing at all. That
was measured here, and it is why tools/build_corpus.py now ends each dialogue at the turn its
checklist fills. The floor is not a formality; it found a defect in the dataset construction before
a single paid call was made.

Three floors, none of which sends a request:

    always-stop     claim the checklist is full on every turn
    always-ask      never stop
    copy-nothing    return an empty collection — the honest null. It never stops, so its decision
                    score equals always-ask; the difference is in the FACT columns, where it takes
                    every `missed` and never a `wrong`.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import judge                                                      # noqa: E402
from src import slots                                                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Follows src.slots.CORPUS, so the floors and the gold can never come from different
# corpora — which is the one way this switch could produce a number nobody could read.
GOLD = os.path.join(HERE, "data", "gold%s.jsonl" % slots._SUFFIX)


def cases(split=None):
    if not os.path.exists(GOLD):
        raise slots.NotBuilt(
            "data/gold.jsonl is not built. This kit's corpus is CC BY-SA 4.0 and fetched, not "
            "committed:\n    python3 -m tools.fetch_corpus\n    python3 -m tools.build_corpus")
    out = []
    for line in open(GOLD, encoding="utf-8"):
        c = json.loads(line)
        if split in (None, c["split"]):
            out.append(c)
    return out


def _always_stop(case):
    """Claim every required fact, with a value gold would accept where one exists.

    ⚠︎ IT IS GIVEN THE BENEFIT OF THE DOUBT ON PURPOSE. Handing it gold's own values means its
    decision score is the highest a constant can reach, so it is the hardest floor to beat rather
    than a straw man. Where gold has nothing it invents a token, which the scorer counts `wrong` —
    which is exactly what claiming an unstated fact IS.
    """
    got = {}
    for s in slots.required(case["intent"]):
        g = case["gold_slots"].get(s)
        got[s] = g[0] if g else "assumed"
    return {"collected": got, "notes": ""}


def _always_ask(case):
    """Collect everything gold has, and never enough to stop. Perfect extraction, no decision."""
    need = slots.required(case["intent"])
    got = {s: case["gold_slots"][s][0] for s in need if s in case["gold_slots"]}
    if len(got) == len(need) and need:
        got.pop(need[-1])            # withhold one, so it can never decide to stop
    return {"collected": got, "notes": ""}


def _copy_nothing(case):
    return {"collected": {}, "notes": ""}


FLOORS = (("always-stop", _always_stop),
          ("always-ask", _always_ask),
          ("copy-nothing", _copy_nothing))


def main():
    split = sys.argv[1] if len(sys.argv) > 1 else "held-out"
    cs = cases(None if split == "all" else split)
    print("%d case(s), split=%s  (%d stop / %d ask by gold)\n"
          % (len(cs), split, sum(1 for c in cs if c["gold_complete"]),
             sum(1 for c in cs if not c["gold_complete"])))
    print("%-14s %8s %8s %8s %8s %10s %9s" %
          ("floor", "correct", "wrong", "missed", "open", "decision", "early"))
    rows_out = {}
    for name, fn in FLOORS:
        t = judge.totals([judge.score(c, fn(c)) for c in cs])
        rows_out[name] = t
        print("%-14s %8d %8d %8d %8d %9.1f%% %9d"
              % (name, t["correct"], t["wrong"], t["missed"], t["open"],
                 100 * t["decision_rate"], t["stopped_early"]))
    best = max(rows_out.values(), key=lambda t: t["decision_rate"])
    print("\nThe floor to beat on the decision is %.1f%%. A model that does not clear it has not "
          "read anything." % (100 * best["decision_rate"]))
    print("Note the `early` column: always-stop is wrong in the direction that costs the most, on "
          "every case where the conversation was not finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
