#!/usr/bin/env python3
"""The free floor: itemize every material exception it is handed, always say 'unknown', echo
unreliable_evidence straight off the input, and narrate with only the numbers it was given. No
model, no key, no spend -- scored through the exact same scorer the real run uses.

    python3 -m evals.baseline --run-id b000-always-unknown

⚑ READ THIS BEFORE THE REAL RUN. It costs nothing and it is the number the paid run only means
something beside -- same discipline every sibling kit's baseline states for its own floor.

⚠︎ WHY THIS FLOOR IS NOT TRIVIAL TO BEAT. Itemizing (exception completeness) and echoing
unreliable_evidence are both pure copying, so this floor gets both for free. What it CANNOT do is
tell a traceable cause from an untraceable one -- it always says unknown, so its cause-tag
agreement on gold's traceable exceptions is 0% by construction. That gap is exactly what a real
model is paid to close.
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
    items = [{"item_id": it["item_id"], "cause": "unknown", "citation_1": "", "citation_2": "",
             "unreliable_evidence": it["unreliable_evidence"],
             "note": "code floor: no cause claimed"}
            for it in packed["items"]]
    n = len(packed["items"])
    if n == 0:
        narrative = "No material exceptions this batch."
    else:
        largest = max(packed["items"], key=lambda it: abs(it["delta_units"] or 0))
        narrative = ("%d material exception%s this batch. The largest is %s, with a spread of %s "
                    "units (%s%%) against the statistical forecast. Cause is not assessed by this "
                    "floor -- every exception is reported as unknown pending review."
                    % (n, "" if n == 1 else "s", largest["item_label"],
                       abs(largest["delta_units"]) if largest["delta_units"] is not None else "n/a",
                       largest["delta_pct"] if largest["delta_pct"] is not None else "n/a"))
    return {"items": items, "narrative": narrative}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-always-unknown")
    a = ap.parse_args()

    batches = B.batches()
    notes = B.notes_by_id()
    gold = B.gold_by_id()

    records = []
    for batch in batches:
        bid = batch["batch_id"]
        exceptions = SEG.material_exceptions(batch)
        packed, pack_meta = PACK.pack(batch, notes.get(bid, []), exceptions)
        answer = floor_answer(packed)
        records.append({"batch_id": bid, "packed": packed, "pack_meta": pack_meta,
                        "items_material": len(exceptions), "items_answered": len(answer["items"]),
                        "answer": answer})

    scored = S.score(records, gold, notes)
    out = {"run_id": a.run_id, "baseline": True, "model": "code floor: always-unknown",
          "batches": len(records), "scores": scored["overall"], "per_batch": scored["per_batch"],
          "fabricated_examples": scored["fabricated_examples"]}

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("%-34s %s" % ("run", a.run_id))
    print("%-34s %s%%" % ("exception completeness (recall)", o["exception_completeness_recall_pct"]))
    print("%-34s %s%%" % ("exception completeness (precision)", o["exception_completeness_precision_pct"]))
    print("%-34s %s%%" % ("cause-tag agreement (all)", o["cause_tag_agreement_pct"]))
    print("%-34s %s%%" % ("  -- on unknown gold", o["cause_tag_agreement_unknown_pct"]))
    print("%-34s %s%%" % ("  -- on traceable gold", o["cause_tag_agreement_traceable_pct"]))
    print("%-34s %s  (%s%%)" % ("FABRICATED CAUSE", o["fabricated_cause"],
                                o["fabricated_cause_rate_pct"]))
    print("%-34s %s%%" % ("unreliable-evidence echo", o["unreliable_evidence_echo_pct"]))
    print("%-34s %s%%" % ("narrative faithfulness", o["narrative_faithfulness_pct"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
