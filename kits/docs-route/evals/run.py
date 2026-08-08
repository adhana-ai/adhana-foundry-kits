"""Route every document in the corpus and write one result file. THE MODEL PATH SPENDS MONEY.

Usage:
    python -m evals.run --run-id b000 --baseline null       # free, no key — the floor
    python -m evals.run --run-id b001 --baseline keyword    # free, no key — the thing to beat
    python -m evals.run --run-id t000 --stub                # free, proves the wiring
    python -m evals.run --run-id r001-<model>               # the real run, one call per document
    python -m evals.run --run-id r001-x --limit 5           # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed.

⚑ AND UNLIKE UC003, THIS RUN PRODUCES A SCORE. The difference is not effort, it is the label: the
Office of the Federal Register assigned every document a type before this kit existed, so there is
a gold answer that nobody here wrote and `==` is a legitimate verdict. UC003's briefs have no such
answer and wait on a person. Both are honest; they are different problems, and the kit board says
which is which rather than making the ungradable one look unfinished.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters                          # noqa: E402
from src import budget as BUDGET                  # noqa: E402
from src import config, route as R, taxonomy as TX  # noqa: E402
from evals import baseline as B                   # noqa: E402
from evals import score as SC                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=400, thinking=None):
    """A deterministic fake provider: always the same queue, at a confidence just over the floor.
    It exercises prompt/parse/guardrail/score end to end without a key. It is NOT a baseline —
    `--baseline null` is that, and it is scored on the board rather than hidden in a stub."""
    body = json.dumps({"queue": TX.ORDER[0], "confidence": 0.9,
                       "why": "stub reply — no model was called"})
    return {"text": body, "input_tokens": len(user) // 4, "output_tokens": len(body) // 4,
            "raw": {"stub": True}}


def _baseline_records(fn, docs):
    """Drive a baseline through the SAME record shape a model run produces, including the
    guardrail's `escalated` field, so score.py cannot tell them apart and cannot treat them
    differently. A baseline scored by a different path is a second measurement, not a comparison."""
    out = {}
    for doc_id in docs:
        pred = fn(R.load_doc(doc_id))
        out[doc_id] = {"model_queue": pred["queue"], "routed_to": pred["queue"],
                       "escalated": False, "state": pred["state"],
                       "confidence": pred["confidence"], "why": pred.get("rule", ""),
                       "floor": None, "input_tokens": 0, "output_tokens": 0}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--baseline", choices=sorted(B.BASELINES), default=None,
                    help="run a zero-cost baseline instead of a model")
    ap.add_argument("--floor", type=float, default=R.CONFIDENCE_FLOOR,
                    help="confidence below which a decision is escalated instead of routed")
    ap.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    a = ap.parse_args()

    cfg = config.load()
    docs = R.documents()
    if a.limit:
        docs = docs[:a.limit]
        # ⚠︎ A --limit SUBSET IS NOT THE EVAL SET, AND THE FIRST PROBE PROVED IT LOUDLY.
        # `--limit 5` took the five lowest document numbers, all five happened to be proposed
        # rules, and the harness printed "null baseline 100.0%" — arithmetically right and
        # completely misleading, because on a single-class subset answering that class always
        # wins. The corpus is balanced; any prefix of it is not. Said here, on every limited run,
        # because the number that misleads is printed whether or not anyone remembers this.
        print("⚠︎  --limit %d takes a PREFIX of the corpus, not a sample. The shipped corpus is "
              "balanced %d per class; a prefix is not, so every rate below describes this subset "
              "and none of them belong on the board." % (a.limit, len(R.documents()) // len(TX.ORDER)))
    if not docs:
        raise SystemExit("the corpus is empty. Run `python -m tools.fetch_corpus` then "
                         "`python -m tools.build_corpus` first.")

    free = bool(a.baseline) or a.stub
    if not free:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free, or "
                             "--baseline keyword to see what there is to beat.")
        print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(len(docs))

    t_all = time.time()
    if a.baseline:
        fn, note = B.BASELINES[a.baseline]
        records = _baseline_records(fn, docs)
        lat, tin, tout, failures = [], 0, 0, []
        print("baseline %r — %s (no provider, no cost)" % (a.baseline, note))
    else:
        complete = stub_complete if a.stub else None
        records, lat, tin, tout, failures = {}, [], 0, 0, []
        for i, doc_id in enumerate(docs, 1):
            t0 = time.time()
            try:
                rec = R.decide(cfg, R.load_doc(doc_id), complete=complete, floor=a.floor)
            except Exception as exc:
                failures.append({"doc_id": doc_id, "error": "%s: %s" % (type(exc).__name__, exc)})
                print("  %3d/%d  %-14s FAILED  %s" % (i, len(docs), doc_id, exc))
                continue
            ms = int((time.time() - t0) * 1000)
            lat.append(ms)
            tin += rec.get("input_tokens") or 0
            tout += rec.get("output_tokens") or 0
            records[doc_id] = rec
            print("  %3d/%d  %s %7d ms" % (i, len(docs), R.summary_line(doc_id, rec), ms))

    scored = SC.score(records)
    # ⚑ THE PER-CALL TIMINGS ARE KEPT, NOT ONLY AGGREGATED — 2026-08-08. Every one of these
    # was measured above and then thrown away the moment it had been folded into a p50 and a p95,
    # so the result file could publish the two percentiles with no distribution behind them. A p95
    # on its own cannot say whether the tail is one slow call or a fat one; the array can. Snapshot
    # taken BEFORE the sort, so call order survives and a warm-up effect stays visible — sorting in
    # place is what would have made this a distribution and not a history.
    #
    # It is written at the TOP LEVEL rather than onto each per-document record on purpose: those
    # records are what score.py grades, and adding a key to a graded structure to carry telemetry
    # is how a timing turns into a phantom extracted field. Costs one array and no provider call.
    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "kind": "pipeline",
        "stub": bool(a.stub),
        "baseline": a.baseline,
        "model": "stub" if a.stub else ("baseline-%s" % a.baseline if a.baseline
                                        else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        # The guardrail's setting, on the record. A run scored at one floor and read as though it
        # were another is the same species of error as a run whose corpus changed underneath it.
        "confidence_floor": None if a.baseline else a.floor,
        "taxonomy": {q: TX.label_of(q) for q in TX.ORDER},
        "null_baseline_accuracy": B.null_score(scored["gold_per_class"]),
        "scores": scored,
        # ⚑ THE FLOOR SWEEP, ON THE RECORD. Without it a run publishes what the DEFAULT floor did
        # and nothing about whether any floor could have done better — and on r001 the answer was
        # that none could, which is the finding.
        "floor_sweep": SC.floor_sweep(records) if not a.baseline else [],
        "records": records,
        "max_tokens": R.MAX_TOKENS,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n" + SC.matrix_text(scored))
    if not a.baseline:
        print("\n" + SC.sweep_text(out["floor_sweep"]))
    print("\n%-30s %s" % ("run", a.run_id))
    print("%-30s %d of %d" % ("documents routed", len(records), len(docs)))
    print("%-30s %.1f%% (answering one queue every time earns this)"
          % ("null baseline", out["null_baseline_accuracy"]))
    print("%-30s %.1f%%" % ("accuracy, all documents", 100 * (scored["accuracy"] or 0)))
    print("%-30s %.1f%%" % ("accuracy, when it answered", 100 * (scored["accuracy_when_answered"] or 0)))
    print("%-30s %.1f%%" % ("withheld for a person", 100 * (scored["withheld_rate"] or 0)))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
