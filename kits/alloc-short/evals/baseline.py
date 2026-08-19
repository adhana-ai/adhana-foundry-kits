#!/usr/bin/env python3
"""The free floor: itemize every flagged event it is handed, always say 'unknown', echo
promo_protected/customer_protected straight off the input, and narrate with only the numbers it
was given. No model, no key, no spend -- scored through the exact same scorer the real run uses.

    python3 -m evals.baseline --run-id b000-always-unknown

⚑ READ THIS BEFORE THE REAL RUN. It costs nothing and it is the number the paid run only means
something beside -- same discipline every sibling kit's baseline states for its own floor.

⚠︎ WHY THIS FLOOR IS NOT TRIVIAL TO BEAT. Itemizing (flag completeness) and echoing the two
protection booleans are both pure copying, so this floor gets both for free. What it CANNOT do is
tell a traceable cause from an untraceable one -- it always says unknown, so its cause-tag
agreement on gold's traceable events is 0% by construction. That gap is exactly what a real model
is paid to close.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import allocate as A          # noqa: E402
from src import pack as PACK              # noqa: E402
from src import draft as D                 # noqa: E402
from evals import scoring as S               # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def floor_answer(packed):
    events = [{"event_id": e["event_id"], "cause": "unknown", "citation_1": "", "citation_2": "",
              "promo_protected": e["promo_protected"], "customer_protected": e["customer_protected"],
              "note": "code floor: no cause claimed"}
             for e in packed["events"]]
    n = len(packed["events"])
    if n == 0:
        narrative = "No flagged events this week."
    else:
        largest = max(packed["events"], key=lambda e: e["total_ask"] - e["available_units"])
        gap = largest["total_ask"] - largest["available_units"]
        narrative = ("%d flagged event%s this week. The largest shortfall is %s, short by %d "
                    "units against %d units requested. Cause is not assessed by this floor -- "
                    "every event is reported as unknown pending review."
                    % (n, "" if n == 1 else "s", largest["sku"], gap, largest["total_ask"]))
    return {"events": events, "narrative": narrative}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-always-unknown")
    a = ap.parse_args()

    sessions = D.sessions()
    notes = D.notes_by_id()
    gold = D.gold_by_id()

    records = []
    for session in sessions:
        sid = session["session_id"]
        flagged = A.flagged_events(session)
        packed, pack_meta = PACK.pack(session, notes.get(sid, []), flagged)
        answer = floor_answer(packed)
        records.append({"session_id": sid, "packed": packed, "pack_meta": pack_meta,
                        "events_flagged": len(flagged), "events_answered": len(answer["events"]),
                        "answer": answer})

    scored = S.score(records, gold, notes)
    out = {"run_id": a.run_id, "baseline": True, "model": "code floor: always-unknown",
          "sessions": len(records), "scores": scored["overall"], "per_session": scored["per_session"],
          "fabricated_examples": scored["fabricated_examples"]}

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("%-32s %s" % ("run", a.run_id))
    print("%-32s %s%%" % ("flag completeness (recall)", o["flag_completeness_recall_pct"]))
    print("%-32s %s%%" % ("flag completeness (precision)", o["flag_completeness_precision_pct"]))
    print("%-32s %s%%" % ("cause-tag agreement (all)", o["cause_tag_agreement_pct"]))
    print("%-32s %s%%" % ("  -- on unknown gold", o["cause_tag_agreement_unknown_pct"]))
    print("%-32s %s%%" % ("  -- on traceable gold", o["cause_tag_agreement_traceable_pct"]))
    print("%-32s %s  (%s%%)" % ("FABRICATED CAUSE", o["fabricated_cause"],
                                o["fabricated_cause_rate_pct"]))
    print("%-32s %s%%" % ("narrative faithfulness", o["narrative_faithfulness_pct"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
