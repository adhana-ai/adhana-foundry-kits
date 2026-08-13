#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The paid run: every request through the loop, scored, written to results/.

⚠︎ THIS IS THE ONLY FILE HERE THAT SPENDS MONEY, AND IT IS THE ONLY KIT IN THIS REPO WHOSE SPEND IS
NOT A MULTIPLICATION. Everywhere else, calls = units of work. Here the model decides how many calls
each request takes, so `--dry-run` prints a RANGE — the floor if every request stops immediately
and the ceiling if every one hits the step cap — and the ceiling is the number to read.

    python3 -m evals.run --dry-run                     # what it would cost. 0 calls.
    python3 -m evals.run --run-id r015-tool-pick-flash # the real thing

⚑ `--limit` EXISTS FOR A SMOKE TEST AND IS NOT THE PUBLISHED RUN. A partial run is evidence about
the requests it covered and nothing else; `runlog.py` on the site side refuses a record whose
answered count is a minority of its dataset, which is the guard UC011 paid to learn.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import budget, config, loop, router, score as S, tools  # noqa: E402

REQUESTS = os.path.join(HERE, "data", "requests.jsonl")
RESULTS = os.path.join(HERE, "results")


def load():
    with open(REQUESTS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    reqs = load()
    if a.limit:
        reqs = reqs[:a.limit]
    cfg = config.load()

    lo, hi = len(reqs), len(reqs) * loop.MAX_STEPS
    # ⚑ THE MIDDLE NUMBER IS THE USEFUL ONE, AND IT IS DERIVED FROM THE LABELS RATHER THAN GUESSED.
    # A perfectly behaved model calls one tool per step in the labelled sequence and then says
    # DONE — so `len(truth) + 1` per request, capped. Min and max alone span 4x and tell a reader
    # nothing about what to expect; this is the figure that turns out to be wrong if the model
    # over-calls, which is itself one of the things the run measures.
    expect = sum(min(len(r["truth"]) + 1, loop.MAX_STEPS) for r in reqs)
    print("tool-pick — %d request(s), step cap %d" % (len(reqs), loop.MAX_STEPS))
    print("model calls: minimum %d (every request answers in one), EXPECTED %d if it behaves "
          "exactly as labelled, maximum %d (every request hits the cap)" % (lo, expect, hi))
    print("cap configured: %s   spent today: %d" % (budget.cap() or "NONE", budget.spent_today()))
    if a.dry_run:
        print("\n--dry-run: nothing was sent. Re-run with --run-id to spend.")
        return 0
    if not a.run_id:
        print("\nrefusing to run without --run-id: an unstamped record cannot be published.")
        return 2

    results = []
    t_start = time.time()
    for i, req in enumerate(reqs, 1):
        r = loop.run_one(cfg, req["text"])
        out = S.outcome(req, r["called"], replied=r["replied"])
        results.append({"id": req["id"], "trap": req["trap"], "text": req["text"],
                        "truth": list(req["truth"]), "decline": req.get("decline", False),
                        "got": r["called"], "outcome": out, "ended": r["ended"],
                        "capped": r["capped"], "replied": r["replied"],
                        "answer": r["answer"], "model_calls": r["model_calls"],
                        "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
                        "latency_ms": r["latency_ms"],
                        "finish_reasons": [s["finish_reason"] for s in r["steps"]],
                        "reasoning_chars": sum(s["reasoning_chars"] or 0 for s in r["steps"]),
                        "transcript": r["transcript"]})
        print("  %-5s %-13s %-22s -> %-21s %d call(s)%s"
              % (req["id"], req["trap"], " ".join(req["truth"]) or "none",
                 out, r["model_calls"], "  CAPPED" if r["capped"] else ""))

    s = S.tally(results)
    s["by_trap"] = S.by_trap(results)
    s["traps_handled"] = S.traps_handled(results)
    s["capped"] = sum(1 for r in results if r["capped"])
    lat = [r["latency_ms"] for r in results if r["replied"]]
    s["latency_p50_ms"] = statistics.median(lat) if lat else None
    s["latency_p95_ms"] = (sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else None)
    s["input_tokens_total"] = sum(r["input_tokens"] for r in results)
    s["output_tokens_total"] = sum(r["output_tokens"] for r in results)
    s["model_calls_total"] = sum(r["model_calls"] for r in results)
    s["model_calls_per_request"] = round(s["model_calls_total"] / max(1, s["requests"]), 3)
    s["wall_seconds"] = round(time.time() - t_start, 1)

    print("\nanswered %d of %d — every rate below is computed over those %d ONLY"
          % (s["answered"], s["requests"], s["answered"]))
    print("EXACT SEQUENCE %s   wrong tool %d   stopped early %d   kept going %d   "
          "should have declined %d   no verdict %d"
          % ("%.1f%%" % (100 * s["sequence_exact"]) if s["sequence_exact"] is not None else "n/a",
             s["counts"]["wrong_tool"], s["counts"]["stopped_early"], s["counts"]["kept_going"],
             s["counts"]["should_have_declined"], s["counts"]["no_verdict"]))
    print("MODEL calls %d (%.2f per request)   TOOL calls %d (mean %.2f, max %d)   "
          "wasted %d   capped %d"
          % (s["model_calls_total"], s["model_calls_total"] / max(1, s["requests"]),
             s["tool_calls_total"], s["tool_calls_per_request_mean"] or 0,
             s["tool_calls_per_request_max"] or 0, s["tool_calls_wasted"], s["capped"]))
    if s["answered"] <= s["requests"] - s["answered"]:
        print("⚠︎  MORE REQUESTS FAILED THAN ANSWERED. Those rates describe the exception, not the")
        print("   run, and the ingest will refuse this record. Read `finish_reasons` first.")

    print("\nby trap — which KIND of hard case it failed:")
    for trap, t in sorted(s["by_trap"].items(), key=lambda x: -x[1]["wrong"]):
        print("  %-14s %d/%d wrong   %s"
              % (trap, t["wrong"], t["requests"],
                 ", ".join("%s %d" % kv for kv in sorted(t["outcomes"].items()))))

    floor = router.sweep(reqs)
    best = max(floor, key=lambda r: r["summary"]["counts"]["correct"])
    print("\nthe free floor, on the same requests: %d of %d exact at cap %d, 0 calls"
          % (best["summary"]["counts"]["correct"], len(reqs), best["cap"]))

    os.makedirs(RESULTS, exist_ok=True)
    payload = {
        "kind": "tools",
        "run_id": a.run_id, "model": cfg["model"], "provider": cfg["provider"],
        "max_steps": loop.MAX_STEPS, "max_tokens": loop.MAX_TOKENS,
        "catalogue": [t["name"] for t in tools.CATALOGUE],
        "dataset": {"requests": len(reqs), "file": "data/requests.jsonl",
                    "by_trap": {k: v["requests"] for k, v in s["by_trap"].items()}},
        "corpus": {"requests": len(reqs), "notes": 6, "db": "data/shop.db",
                   "note": "generated by tools/build_corpus.py from a fixed seed, MIT"},
        "floor": {"best_cap": best["cap"],
                  "correct": best["summary"]["counts"]["correct"],
                  "sequence_exact": best["summary"]["sequence_exact"],
                  "note": "measured in results/baseline.json — run evals/baseline.py"},
        "summary": s, "rows": results,
        "could_not_verify": [
            "The step cap is %d. A model that would have answered correctly on its fifth call is "
            "recorded as capped, not as wrong, and nothing here measures how many those are — "
            "raising the cap is a second run." % loop.MAX_STEPS,
            "The tools are local, read-only and fast. Nothing here measures tool choice when a "
            "tool is slow, flaky or expensive, which is when the decision actually costs something.",
            "The corpus is invented, so it holds the five failure modes we thought to plant and no "
            "others. Real requests are not evenly divided between them.",
            "One model, one run. A second tier on the identical requests is not measured, and "
            "UC010's second tier scored LOWER while moving its failure from loud to silent.",
        ]}
    out = os.path.join(RESULTS, "eval-%s.json" % re.sub(r"[^a-z0-9._-]+", "-", a.run_id.lower()))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
