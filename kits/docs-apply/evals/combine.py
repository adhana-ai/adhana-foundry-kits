#!/usr/bin/env python3
"""Score a THIRD system built from the two already recorded, for $0.00.

    python3 evals/combine.py

⚑ THIS IS A RE-SCORE, NOT A RUN. Nothing is called. It reads the two committed result files and
asks what a system that used both would have scored — the rules editor doing the mechanical work,
and the model consulted only as a veto. That distinction matters and this repo protects it: the
outputs are the evidence, a score is an opinion about them, and an opinion may be corrected. What
it must never become is re-scoring until the number improves, so this file is committed with its
rule written down and both parents' records are kept.

THE RULE, AND IT IS DELIBERATELY THE SIMPLEST ONE THAT COULD WORK:

    apply the edit only if BOTH systems would apply it; if either declines, decline.

Nothing cleverer, because anything cleverer would be fitted to these 60 rows. The question being
answered is narrow: does the model's comprehension add anything to a rules editor that is already
perfect at the mechanical half?
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from evals.score import score_all, load_requests, load_doc  # noqa: E402
from evals import baseline as FLOOR  # noqa: E402


def main():
    rows = load_requests(HERE)
    model = json.load(open(os.path.join(HERE, "results", "eval-r001-docs-apply-flash.json"),
                           encoding="utf-8"))
    # What the MODEL decided, per document, read off the committed record.
    model_wrote = {r["doc_id"]: r["wrote"] for r in model["rows"]}
    failed = {f["doc_id"] for f in model["failures"]}

    produced, veto = {}, 0
    for r in rows:
        did = r["doc_id"]
        before = load_doc(HERE, "corpus", did)
        floor_out = FLOOR.apply_request(before, r["request"])
        if floor_out is None:
            produced[did] = None                      # the floor already declines: decline
            continue
        if did in failed:
            # ⚑ A REPLY THE MODEL BROKE IS NOT A VETO. Treating an unparseable reply as "declined"
            # would let the combined system harvest refusal credit from a transport failure —
            # the same trap the scorer refuses for the model alone.
            produced[did] = floor_out
            continue
        if not model_wrote.get(did, True):
            produced[did] = None                      # the model declined: veto the floor's edit
            veto += 1
            continue
        produced[did] = floor_out

    res = score_all(rows, produced, HERE)
    res.update({
        "run_id": "c001-docs-apply-combined", "stub": False,
        "model": "rules-baseline + deepseek-v4-flash veto", "provider": "none",
        "documents": len(rows), "answered": len(rows), "failures": [],
        "latency_p50_ms": 0, "latency_p95_ms": 0, "wall_seconds": 0.0,
        "input_tokens_total": 0, "output_tokens_total": 0,
        "derived_from": ["b000-docs-apply-rules", "r001-docs-apply-flash"],
        "note": ("A re-score of two committed runs, not a third run. Zero calls, zero tokens: the "
                 "token and latency figures are zeros because nothing was called, not because "
                 "nothing was measured. The model calls it depends on were already paid for in "
                 "r001-apply."),
        "vetoes_used": veto,
    })
    out = os.path.join(HERE, "results", "eval-c001-docs-apply-combined.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    sc = res["scores"]
    print("c001-docs-apply-combined  applied %.1f%%  clean %.1f%%  collateral %d  refusal %.1f%%  unsafe %d "
          "(%d veto(es) used)"
          % (100 * sc["edit_applied"], 100 * sc["edit_clean"], sc["collateral_lines"],
             100 * sc["refusal_accuracy"], sc["unsafe_writes"], veto))
    for fam, v in res["by_family"].items():
        print("   %-14s %d/%d = %.1f%%" % (fam, v["correct"], v["n"], v["pct"]))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
