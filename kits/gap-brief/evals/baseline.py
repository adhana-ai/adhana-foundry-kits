#!/usr/bin/env python3
"""The free floor: itemize every material gap it is handed, always say 'unknown', echo
missing_view straight off the input, and narrate with only the numbers it was given. No model, no
key, no spend -- scored through the exact same scorer the real run uses.

    python3 -m evals.baseline --run-id b000-always-unknown

⚑ READ THIS BEFORE THE REAL RUN. It costs nothing and it is the number the paid run only means
something beside -- same discipline every sibling kit's baseline states for its own floor.

⚠︎ WHY THIS FLOOR IS NOT TRIVIAL TO BEAT. Itemizing (gap completeness) and echoing missing_view
are both pure copying, so this floor gets both for free. What it CANNOT do is tell a traceable
cause from an untraceable one -- it always says unknown, so its cause-tag agreement on gold's
traceable gaps is 0% by construction. That gap is exactly what a real model is paid to close.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import segment as SEG          # noqa: E402
from src import pack as PACK              # noqa: E402
from src import brief as B                 # noqa: E402
from evals import scoring as S               # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def floor_answer(packed):
    gaps = [{"item_id": g["item_id"], "cause": "unknown", "citation_1": "", "citation_2": "",
            "missing_view": g["missing_view"] is not None, "note": "code floor: no cause claimed"}
           for g in packed["gaps"]]
    n = len(packed["gaps"])
    if n == 0:
        narrative = "No material gaps this cycle."
    else:
        largest = max(packed["gaps"], key=lambda g: g["delta_usd"])
        narrative = ("%d material gap%s this cycle. The largest is %s, with a spread of $%.2f "
                    "(%s%%) between its plan views. Cause is not assessed by this floor -- every "
                    "gap is reported as unknown pending review."
                    % (n, "" if n == 1 else "s", largest["item_label"], largest["delta_usd"],
                       largest["delta_pct"]))
    return {"gaps": gaps, "narrative": narrative}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-always-unknown")
    a = ap.parse_args()

    cycles = B.cycles()
    notes = B.notes_by_id()
    gold = B.gold_by_id()

    records = []
    for cycle in cycles:
        cid = cycle["cycle_id"]
        gaps = SEG.material_gaps(cycle)
        packed, pack_meta = PACK.pack(cycle, notes.get(cid, []), gaps)
        answer = floor_answer(packed)
        records.append({"cycle_id": cid, "packed": packed, "pack_meta": pack_meta,
                        "gaps_material": len(gaps), "gaps_answered": len(answer["gaps"]),
                        "answer": answer})

    scored = S.score(records, gold, notes)
    out = {"run_id": a.run_id, "baseline": True, "model": "code floor: always-unknown",
          "cycles": len(records), "scores": scored["overall"], "per_cycle": scored["per_cycle"],
          "fabricated_examples": scored["fabricated_examples"]}

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("%-32s %s" % ("run", a.run_id))
    print("%-32s %s%%" % ("gap completeness (recall)", o["gap_completeness_recall_pct"]))
    print("%-32s %s%%" % ("gap completeness (precision)", o["gap_completeness_precision_pct"]))
    print("%-32s %s%%" % ("cause-tag agreement (all)", o["cause_tag_agreement_pct"]))
    print("%-32s %s%%" % ("  -- on unknown gold", o["cause_tag_agreement_unknown_pct"]))
    print("%-32s %s%%" % ("  -- on traceable gold", o["cause_tag_agreement_traceable_pct"]))
    print("%-32s %s  (%s%%)" % ("FABRICATED CAUSE", o["fabricated_cause"],
                                o["fabricated_cause_rate_pct"]))
    print("%-32s %s%%" % ("missing-view echo", o["missing_view_echo_pct"]))
    print("%-32s %s%%" % ("narrative faithfulness", o["narrative_faithfulness_pct"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
