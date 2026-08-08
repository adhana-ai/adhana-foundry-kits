"""Classify every pair's changed span and write one result file. THE MODEL PATH SPENDS MONEY.

Usage:
    python -m evals.run --run-id b000 --baseline regex   # free, no key — the thing to beat
    python -m evals.run --run-id t000 --stub             # free, proves the wiring
    python -m evals.run --run-id r001-<model>             # the real run, one call per pair
    python -m evals.run --run-id r001-x --limit 5         # a costed toe in the water

⚠︎ ONE CALL PER PAIR, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed — same discipline as every other kit here.

⚑ THIS FILE DOES NOT SCORE. Unlike docs-route, there is no gold label to score against the moment
a single run finishes — see evals/score.py's opening note. A run here produces one model's
verdicts; `evals/compare.py` scores two of them against each other once both exist. Printing a
score this file cannot honestly produce would be the exact failure this split avoids.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                     # noqa: E402
from src import config, redline as RL, materiality as MT, diff as D  # noqa: E402
from evals import baseline as B                       # noqa: E402
from evals import score as SC                          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=400, thinking=None):
    """A deterministic fake provider: always 'material', just over the floor. Proves prompt /
    parse / guardrail end to end with no key — not a baseline, `--baseline regex` is that."""
    body = json.dumps({"materiality": MT.ORDER[0], "confidence": 0.9,
                       "why": "stub reply — no model was called"})
    return {"text": body, "input_tokens": len(user) // 4, "output_tokens": len(body) // 4,
            "raw": {"stub": True}}


def _baseline_records(fn, pair_list):
    out = {}
    for pair_id, v1_id, v2_id in pair_list:
        span = D.primary(RL.load_version(v1_id), RL.load_version(v2_id))
        if span is None:
            out[pair_id] = {"state": "no_change", "span": None, "materiality": None,
                            "escalated": False, "confidence": None, "why": "",
                            "input_tokens": 0, "output_tokens": 0}
            continue
        pred = fn(span)
        out[pair_id] = {"state": pred["state"], "span": span, "materiality": pred["materiality"],
                        "escalated": False, "confidence": pred["confidence"],
                        "why": pred.get("rule", ""), "input_tokens": 0, "output_tokens": 0}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--baseline", choices=sorted(B.BASELINES), default=None)
    ap.add_argument("--floor", type=float, default=RL.CONFIDENCE_FLOOR)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    pair_list = RL.pairs()
    if a.limit:
        pair_list = pair_list[:a.limit]
    if not pair_list:
        raise SystemExit("the corpus is empty. Run `python -m tools.fetch_corpus` then "
                         "`python -m tools.build_corpus` first.")

    free = bool(a.baseline) or a.stub
    if not free:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free, or "
                             "--baseline regex to see what there is to beat.")
        print(BUDGET.plan(len(pair_list), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(len(pair_list))

    t_all = time.time()
    if a.baseline:
        fn, note = B.BASELINES[a.baseline]
        records = _baseline_records(fn, pair_list)
        lat, tin, tout, failures = [], 0, 0, []
        print("baseline %r — %s (no provider, no cost)" % (a.baseline, note))
    else:
        complete = stub_complete if a.stub else None
        records, lat, tin, tout, failures = {}, [], 0, 0, []
        for i, (pair_id, v1_id, v2_id) in enumerate(pair_list, 1):
            t0 = time.time()
            try:
                rec = RL.decide(cfg, RL.load_version(v1_id), RL.load_version(v2_id),
                                complete=complete, floor=a.floor)
            except Exception as exc:
                failures.append({"pair_id": pair_id, "error": "%s: %s" % (type(exc).__name__, exc)})
                print("  %3d/%d  %-14s FAILED  %s" % (i, len(pair_list), pair_id, exc))
                continue
            ms = int((time.time() - t0) * 1000)
            lat.append(ms)
            tin += rec.get("input_tokens") or 0
            tout += rec.get("output_tokens") or 0
            records[pair_id] = rec
            print("  %3d/%d  %s %7d ms" % (i, len(pair_list), RL.summary_line(pair_id, rec), ms))

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
    outcome_counts = SC.outcomes(records)

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "kind": "pipeline",
        "stub": bool(a.stub),
        "baseline": a.baseline,
        "model": "stub" if a.stub else ("baseline-%s" % a.baseline if a.baseline
                                        else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "pairs": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "confidence_floor": None if a.baseline else a.floor,
        "outcomes": outcome_counts,
        "records": records,
        "max_tokens": RL.MAX_TOKENS,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n%-30s %s" % ("run", a.run_id))
    print("%-30s %d of %d" % ("pairs classified", len(records), len(pair_list)))
    for o, n in sorted(outcome_counts.items()):
        print("  %-28s %d" % (o, n))
    print("-> %s" % os.path.relpath(path, HERE))
    print("\nNext: run a second model (or --baseline regex), then "
         "python -m evals.compare --a <run-id> --b <run-id>")


if __name__ == "__main__":
    main()
