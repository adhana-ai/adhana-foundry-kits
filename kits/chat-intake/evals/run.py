#!/usr/bin/env python3
"""Run the kit over the labelled cases and write one result file.

    python3 -m evals.baseline held-out          # first. Always.
    python3 -m evals.run --n 40 --run-id r001-<model>

⚠︎ THIS SPENDS MONEY AND IT IS THE OPERATOR'S CALL TO FIRE IT. One call per case. `--n` is required
rather than defaulted to "all", because 298 held-out cases at one call each is a bill nobody asked
for, and a harness whose default is "everything" gets run by accident exactly once.

⚑ THE FLOOR IS PRINTED BEFORE THE RESULT, IN THE SAME OUTPUT. On this task always-stop already
scores 54.4% on held-out, so a model at 60% has barely read anything. Making somebody go and look
that up in another file is how a number gets quoted on its own.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import baseline, judge                                            # noqa: E402
from src import budget, config, intake, prompt, slots                                # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True, help="how many cases. No default on purpose.")
    ap.add_argument("--split", default="held-out", choices=("held-out", "sample", "all"))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--dry-run", action="store_true", help="build every prompt, send nothing")
    a = ap.parse_args()

    cfg = config.load()
    if not a.dry_run and not config.has_key(cfg):
        print("No API_KEY configured. Set one in .env, or use --dry-run to see the prompts.",
              file=sys.stderr)
        return 1

    cases = baseline.cases(None if a.split == "all" else a.split)
    # Deterministic subset: the first n by case_id, so two runs of the same size compare like for
    # like. Sampling at random would make every re-run a different experiment.
    cases = sorted(cases, key=lambda c: c["case_id"])[:a.n]
    if not cases:
        print("no cases — run tools.build_corpus", file=sys.stderr)
        return 1

    print("floor, on the same %d case(s):" % len(cases))
    for name, fn in baseline.FLOORS:
        t = judge.totals([judge.score(c, fn(c)) for c in cases])
        print("  %-14s decision %5.1f%%   stopped early %d"
              % (name, 100 * t["decision_rate"], t["stopped_early"]))
    if a.dry_run:
        # ⚠︎ IT PRINTS THE PROMPT, NOT A DESCRIPTION OF THE PROMPT. The first version of this
        # branch echoed a docstring line, which told a reader nothing they could check. The whole
        # value of a dry run is seeing the exact bytes a paid run would send.
        built = [prompt.render(c["intent"], c["turns"]) for c in cases]
        chars = sum(len(b) for b in built)
        print("\n--dry-run: %d prompt(s) built, nothing sent. %d chars total, ~%d per call."
              % (len(built), chars, chars // len(built)))
        print("\n--- case %s, verbatim ---\n%s\n--- ends ---" % (cases[0]["case_id"], built[0]))
        return 0

    print("\nmodel %s via %s" % (cfg["model"] or "(unset)", cfg["provider"]))
    rows, records, t0 = [], [], time.time()
    for i, c in enumerate(cases, 1):
        budget.record(cfg.get("model", ""), "chat-intake")
        started = time.time()
        out = intake.turn(cfg, c["intent"], c["turns"])
        out["latency_ms"] = int(1000 * (time.time() - started))
        parsed = {"collected": out["collected"], "notes": out["notes"]} if out["parsed"] else None
        row = judge.score(c, parsed)
        row["latency_ms"] = out["latency_ms"]
        rows.append(row)
        records.append({"case_id": c["case_id"], "intent": c["intent"],
                        "turns": len(c["turns"]), "decision": out["decision"],
                        "collected": out["collected"], "gold": c["gold_slots"],
                        "gold_complete": c["gold_complete"], "parsed": out["parsed"],
                        "input_tokens": out["input_tokens"],
                        "output_tokens": out["output_tokens"],
                        "latency_ms": out["latency_ms"]})
        print("  %3d/%d  %-16s %-4s %s" % (i, len(cases), c["case_id"], out["decision"],
                                           "ok" if row["decision_ok"] else "WRONG"))

    t = judge.totals(rows)
    lat = sorted(r["latency_ms"] for r in rows)
    out = {
        "run_id": a.run_id,
        "kit": "chat-intake",
        "split": a.split,
        "model": cfg["model"],
        "provider": cfg["provider"],
        "dataset_version": "SGD Banks_1, train, held-out carved by sha256(dialogue_id) < 0.20",
        "grader": "pure code — evals/judge.py, == against the dataset's own dialogue state. "
                  "No judge model, so the eval costs nothing to re-run.",
        "elapsed_s": round(time.time() - t0, 1),
        "latency_p50_ms": lat[len(lat) // 2] if lat else None,
        "latency_p95_ms": lat[int(len(lat) * 0.95)] if lat else None,
        "input_tokens": sum(r["input_tokens"] or 0 for r in records),
        "output_tokens": sum(r["output_tokens"] or 0 for r in records),
        "totals": t,
        "floors": {name: judge.totals([judge.score(c, fn(c)) for c in cases])
                   for name, fn in baseline.FLOORS},
        "checklist": slots.intents(),
        "records": records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    p = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    json.dump(out, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print("\ndecision %.1f%%   stopped early %d   kept asking %d   unparsed %d"
          % (100 * t["decision_rate"], t["stopped_early"], t["kept_asking"], t["unparsed"]))
    print("facts: %d correct / %d wrong / %d missed / %d open"
          % (t["correct"], t["wrong"], t["missed"], t["open"]))
    print("-> %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
