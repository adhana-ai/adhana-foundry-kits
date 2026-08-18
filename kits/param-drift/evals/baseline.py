#!/usr/bin/env python3
"""The free floor: `src/formulas.py`'s rule-and-threshold decision, scored through the exact same
scorer the real run uses. No model, no key, no spend.

    python3 -m evals.baseline --run-id b000-rule-threshold-floor

⚑ READ THIS BEFORE THE REAL RUN. It costs nothing and it is the number the paid run only means
something beside -- same discipline every sibling kit's baseline states for its own floor.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import aggregate as A, formulas as F, triage as T          # noqa: E402
from evals import scoring as S                                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-rule-threshold-floor")
    a = ap.parse_args()

    params = T.load_parameters()
    gold = T.labels_by_id()
    params_by_id = T.parameters_by_id()
    wins = T.windows()

    rows = []
    for p in params:
        pid = p["parameter_id"]
        w = wins[pid]
        fx = A.facts(w)
        verdict, reasons = F.decide_floor(p["category"], p["configured_value"], fx["stats"])
        proposed = F.corrected_value(p["category"], fx["stats"])
        rows.append({"parameter_id": pid, "verdict": verdict, "replied": True,
                    "floor_reasons": reasons, "proposed_value": proposed,
                    "deviation": F.deviation(p["category"], p["configured_value"], fx["stats"])})

    scored = S.score(rows, gold, params_by_id)
    out = {"run_id": a.run_id, "baseline": True, "model": "rule-and-threshold floor",
          "n": len(rows), "scores": scored["overall"], "per_category": scored["per_category"],
          "per_trap": scored["per_trap"], "rows": scored["rows"]}

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("%-24s %s" % ("run", a.run_id))
    print("%-24s %s%%" % ("recall (detection)", o["recall_pct"]))
    print("%-24s %s%%" % ("precision", o["precision_pct"]))
    print("%-24s %s%%" % ("value agreement", o["value_agreement_pct"]))
    print("%-24s %s" % ("counts", o["counts"]))
    for cat, s in scored["per_category"].items():
        print("  %-16s recall %s%%  precision %s%%  value %s%%  (n=%d)"
              % (cat, s["recall_pct"], s["precision_pct"], s["value_agreement_pct"], s["n"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
