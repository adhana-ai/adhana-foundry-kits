#!/usr/bin/env python3
"""Run the model over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id t000 --stub                     # no key, no spend, proves wiring
    python -m evals.run --run-id r001-<model>                    # THE REAL RUN, one call/parameter
    python -m evals.run --run-id r001-x --limit 5                 # a costed toe in the water

⚠︎ ONE CALL PER PARAMETER, COUNTED BEFORE IT IS MADE -- same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                      # noqa: E402
from src import config, triage as T                     # noqa: E402
from src.prompt import MAX_TOKENS                          # noqa: E402
from evals import scoring as S                               # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider: always FLAGs, citing the fact block verbatim. Not a
    baseline -- evals/baseline.py is; this only exercises the pipeline end to end with no key."""
    return {"text": json.dumps({"verdict": "FLAG", "reason": "stub: exercising the pipeline only"}),
           "input_tokens": len(user) // 4, "output_tokens": 12, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--no-thinking", action="store_true",
                    help="disable provider-side reasoning. Off by default.")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    params = T.load_parameters()
    if a.limit:
        params = params[:a.limit]
    gold = T.labels_by_id()
    params_by_id = T.parameters_by_id()
    wins = T.windows()

    print("run       : %s" % a.run_id)
    print("parameters: %d   (one call per parameter)" % len(params))
    print("model     : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking  : %s" % ("disabled" if a.no_thinking else "provider default"))
    if not a.stub:
        print(BUDGET.plan(len(params), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted -- nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(params))

    from src.adapters import THINKING_OFF
    thinking = THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    rows, lat, tin, tout, no_verdict = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, p in enumerate(params, 1):
        pid = p["parameter_id"]
        w = wins[pid]
        t0 = time.time()
        r = T.check(cfg, p, w, complete=complete, thinking=thinking)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["replied"]:
            no_verdict += 1
        if first is None and r["replied"]:
            first = r
        row = {"parameter_id": pid, "category": r["category"], "verdict": r["verdict"],
              "reason": r["reason"], "replied": r["replied"], "proposed_value": r["proposed_value"],
              "deviation": r["deviation"], "floor_verdict": r["floor_verdict"],
              "floor_reasons": r["floor_reasons"], "finish_reason": r.get("finish_reason"),
              "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
              "reasoning_chars": r.get("reasoning_chars"), "latency_ms": ms}
        if not r["replied"]:
            row["raw_text"] = r.get("raw_text", "")
        rows.append(row)
        print("  %2d/%d  %-9s %-13s verdict=%-5s floor=%-5s %s"
              % (i, len(params), pid, r["category"], str(r["verdict"]), r["floor_verdict"],
                 "" if r["replied"] else "*** NO VERDICT ***"))

    scored = S.score(rows, gold, params_by_id)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    out = {
        "run_id": a.run_id, "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "parameters": len(rows), "no_verdict": no_verdict,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"], "per_category": scored["per_category"],
        "per_trap": scored["per_trap"],
        "prompt_parts": [{"name": pp["name"], "chars": len(pp["text"])}
                        for pp in (first["parts"] if first else [])],
        "raw_text": (first["raw_text"] if first else ""),
        "max_tokens": MAX_TOKENS, "thinking": thinking,
        "rows": rows,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("\n%-24s %s" % ("run", a.run_id))
    print("%-24s %s%%" % ("recall (detection)", o["recall_pct"]))
    print("%-24s %s%%" % ("precision", o["precision_pct"]))
    print("%-24s %s%%" % ("value agreement", o["value_agreement_pct"]))
    print("%-24s %s" % ("no_verdict", no_verdict))
    for cat, s in scored["per_category"].items():
        print("  %-16s recall %s%%  precision %s%%  value %s%%  (n=%d)"
              % (cat, s["recall_pct"], s["precision_pct"], s["value_agreement_pct"], s["n"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
