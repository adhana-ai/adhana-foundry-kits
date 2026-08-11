"""Re-score a recorded run against the current ruler. Calls nothing. Costs nothing.

⚠︎ WHY THIS EXISTS, AND WHY IT IS NOT A SECOND RUN. "Run once" is a claim about how many times the
TASK was attempted and published — how many times a model was asked these questions. This file asks
no model anything. It reads the statements the model already produced, stored verbatim in the
result file, and applies the scorer to them again. The model's output is the evidence; the score is
an opinion about that evidence, and an opinion is allowed to be corrected.

What is NOT allowed, and what this file must never become: re-scoring until the number improves.
The guard against that is that every change to the ruler is a change to committed code with its
reason written down, and the ORIGINAL result file is kept beside the corrected one. Both are in the
repo. Anyone can diff them.

⚑ THE FIRST USE OF IT, RECORDED SO THE NEXT READER KNOWS WHAT IT IS FOR. Run r010-data-qa-flash
scored 70.0%. Two of its six failures were the harness's fault, not the model's:

  · `same()` compared ROW ORDER whenever either query happened to carry ORDER BY. A gold query may
    sort for presentation on a question that never asked for it, so a model returning the identical
    rows unsorted was marked wrong. Cost q-13 and q-17. Whether order is part of the answer is now
    declared per question in labelled.jsonl.
  · An empty model response was recorded as `refused_by_guard`, which reads as "the model tried to
    write to your database". It had returned nothing at all — 1,024 output tokens of reasoning and
    no content. It has its own cause now.

Neither change makes a wrong answer right. The first stops punishing a right one; the second moves
two failures to the stage that actually lost them, and they are still failures.
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels          # noqa: E402
from evals.run import score_row, summarise          # noqa: E402

RESULTS = os.path.join(HERE, "results")


def rescore(path, note):
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    labels = {r["id"]: r for r in load_labels()}
    before = copy.deepcopy(payload["summary"])
    changed = []

    for rec in payload["rows"]:
        row = labels.get(rec["id"])
        if row is None:
            continue                     # a question that has since left the labelled set
        was = (rec.get("correct"), rec.get("cause"))
        # The stored `sql` is what the model produced, after the same clean() the run applied.
        for k in ("correct", "cause", "guard_reason", "error", "rows_returned", "gold_rows",
                  "exec_ms"):
            rec.pop(k, None)
        rec.update(score_row(row, rec.get("sql", ""), None))
        now = (rec.get("correct"), rec.get("cause"))
        if was != now:
            changed.append({"id": rec["id"], "was": {"correct": was[0], "cause": was[1]},
                            "now": {"correct": now[0], "cause": now[1]}})

    payload["summary"] = summarise(payload["rows"])
    payload["rescored"] = {
        "note": note,
        "scored_by": "evals/rescore.py — no model was called; the recorded statements were "
                     "re-judged by the corrected ruler",
        "accuracy_before": before.get("accuracy"),
        "accuracy_after": payload["summary"].get("accuracy"),
        "causes_before": before.get("causes"),
        "causes_after": payload["summary"].get("causes"),
        "rows_changed": changed,
    }
    payload.setdefault("could_not_verify", []).append(
        "Execution match compares COLUMN SETS exactly. 'Which region has the most customers?' "
        "answered as `North` and as `North, 106` are both defensible and only one matches the "
        "gold. q-06 and q-18 are scored wrong for this reason and a person would accept both, so "
        "the accuracy here is a FLOOR on this model rather than a verdict on it. The rule is left "
        "strict deliberately: loosening it would mean guessing which columns a question implies.")
    return payload, changed, before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", help="results/eval-<run-id>.json")
    ap.add_argument("--note", default="ruler corrected; model outputs unchanged")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite; default writes <file>.rescored.json beside it")
    a = ap.parse_args()

    path = a.result if os.path.isabs(a.result) else os.path.join(HERE, a.result)
    payload, changed, before = rescore(path, a.note)

    print("re-scored %s — NO model calls" % os.path.relpath(path, HERE))
    print("  accuracy  %.1f%%  ->  %.1f%%"
          % (100 * (before.get("accuracy") or 0), 100 * (payload["summary"].get("accuracy") or 0)))
    print("  causes    %s" % (before.get("causes") or {}))
    print("        ->  %s" % (payload["summary"].get("causes") or {}))
    if changed:
        print("\n  rows whose verdict moved:")
        for c in changed:
            print("    %-6s %-22s -> %s"
                  % (c["id"], "%s/%s" % (c["was"]["correct"], c["was"]["cause"]),
                     "%s/%s" % (c["now"]["correct"], c["now"]["cause"])))
    out = path if a.in_place else path.replace(".json", ".rescored.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
