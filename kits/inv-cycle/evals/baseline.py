#!/usr/bin/env python3
"""The free floor: a simple, dumb rule -- the kind a person free-texting a quick classifier would
write in five minutes, not a model. No model, no key, no spend -- scored through the exact same
scorer the real run uses.

    python3 -m evals.baseline --run-id b000-pack-multiple

⚑ READ THIS BEFORE THE REAL RUN. It costs nothing and it is the number the paid run only means
something beside -- same discipline gap-brief's own baseline states for its own floor.

⚠︎ THIS FLOOR IS THE TRAP, WRITTEN OUT AS A RULE. "If the variance divides evenly by a common
case-pack size, call it uom_error" is exactly the pattern-match the use case's eval_intent exists
to catch a real model falling into -- so this floor gets every trap case wrong BY CONSTRUCTION,
and gets zero citation validity on every non-unresolved guess, because a five-minute rule has no
way to point at a specific log line that actually supports what it guessed.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import brief as B                 # noqa: E402
from src import segment as SEG               # noqa: E402
from evals import scoring as S                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def baseline_cause(event):
    """The dumb rule, in full: a clean case-pack multiple means uom_error, full stop -- no check
    for whether a log line actually shows a unit-of-measure mismatch. Failing that, any scan-type
    line present means unscanned_movement. Failing that, unresolved."""
    if SEG.is_case_pack_multiple(event["variance_qty"]):
        return "uom_error"
    if any(l["type"] == "scan" for l in event["log"]):
        return "unscanned_movement"
    return "unresolved"


def floor_answer(event):
    cause = baseline_cause(event)
    narrative = ("Variance of %+d units on %s at %s read as %s from the numbers alone -- no "
                "specific log line was checked." % (event["variance_qty"], event["item_id"],
                                                    event["location_id"], cause.replace("_", " ")))
    return {"cause": cause, "citations": [], "narrative": narrative}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-pack-multiple")
    a = ap.parse_args()

    events = B.events()
    gold = B.gold_by_id()
    events_by_id = {e["event_id"]: e for e in events}

    records = []
    for event in events:
        records.append({"event_id": event["event_id"], "answer": floor_answer(event)})

    scored = S.score(records, gold, events_by_id)
    out = {"run_id": a.run_id, "baseline": True, "model": "code floor: pack-multiple-guesses-uom",
          "events": len(records), "scores": scored["overall"], "per_event": scored["per_event"],
          "fabricated_examples": scored["fabricated_examples"], "confusion": scored["confusion"]}

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("%-32s %s" % ("run", a.run_id))
    print("%-32s %s%%" % ("cause accuracy (all)", o["cause_accuracy_pct"]))
    print("%-32s %s%%" % ("  -- on unresolved gold", o["cause_accuracy_unresolved_pct"]))
    print("%-32s %s%%" % ("  -- on traceable gold", o["cause_accuracy_traceable_pct"]))
    print("%-32s %s%%" % ("citation validity", o["citation_validity_pct"]))
    print("%-32s %s  (%s%%)" % ("FABRICATED CAUSE", o["fabricated_cause"],
                                o["fabricated_cause_rate_pct"]))
    print("%-32s %s / %s  (%s%%)" % ("UOM/TRANSFER CONFUSION", o["uom_transfer_confusion"],
                                     o["trap_total"], o["uom_transfer_confusion_rate_pct"]))
    print("%-32s %s%%" % ("narrative faithfulness", o["narrative_faithfulness_pct"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
