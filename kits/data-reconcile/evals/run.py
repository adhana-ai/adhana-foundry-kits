"""Run the reconciler over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>             # the real run, ONE call per order
    python -m evals.run --run-id t000 --stub              # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5          # a costed toe in the water

⚠︎ ONE CALL PER ORDER, COUNTED BEFORE IT IS MADE — same discipline as every sibling kit's run.py.
The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                  # noqa: E402
from src import adapters                          # noqa: E402
from src import config, reconcile as R             # noqa: E402
from src.reconcile import MAX_TOKENS               # noqa: E402
from src import prompt as P                         # noqa: E402
from evals import scoring as S                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It answers `clean` to every check and cites the agreement's
    first line for it. That is an honestly mediocre checker — it exercises prompt -> call -> parse
    -> score end to end without a key. It is NOT a baseline; evals/baseline.py is."""
    marker = "AGREEMENT\n---------\n"
    agr = user.split(marker, 1)[-1] if marker in user else user
    first_line = next((l for l in agr.splitlines() if l.strip()), "")
    checks = [{"check": c, "verdict": "clean", "citation": first_line, "expected": None,
              "actual": None} for c in P.CHECKS]
    return {"text": json.dumps({"checks": checks}),
           "input_tokens": len(user) // 4, "output_tokens": 30 * len(P.CHECKS),
           "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--no-thinking", action="store_true",
                    help="disable provider-side reasoning. Off by default; see docs-comply's "
                         "own note on why a provider default of ON can burn the output ceiling.")
    ap.add_argument("--prompt", default=P.DEFAULT_PROMPT,
                    help="which SYSTEM variant to send: %s" % ", ".join(sorted(P.SYSTEMS)))
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    gold = R.load_gold()
    orders = R.orders()
    if a.limit:
        orders = orders[:a.limit]

    print("run      : %s" % a.run_id)
    print("orders   : %d   checks per order: %d   total checks: %d"
          % (len(orders), len(P.CHECKS), len(orders) * len(P.CHECKS)))
    print("calls    : %d  (one per order — all %d checks are batched)"
          % (len(orders), len(P.CHECKS)))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    print("prompt   : %s" % a.prompt)
    if not a.stub:
        print(BUDGET.plan(len(orders), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted — nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(orders))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    records, lat, tin, tout, failures = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, order in enumerate(orders, 1):
        agreement_text = R.load_agreement(order["supplier_id"])
        t0 = time.time()
        r = R.check(cfg, order, agreement_text, complete=complete, thinking=thinking,
                   prompt=a.prompt)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        rec = {"order_id": order["order_id"], "supplier_id": order["supplier_id"],
              "checks": r["checks"], "answered": r["answered"], "asked": r["asked"],
              "parsed": r["parsed"], "finish_reason": r.get("finish_reason"),
              "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
              "reasoning_tokens": r.get("reasoning_tokens"), "latency_ms": ms}
        if not r["parsed"]:
            rec["raw_text"] = r.get("raw", "")
        records.append(rec)
        print("  %2d/%d  %-10s %d/%d answered  %s"
              % (i, len(orders), order["order_id"], r["answered"], r["asked"],
                 "" if r["parsed"] else "*** UNPARSEABLE ***"))

    scored = S.score(records, gold)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "orders": len(records),
        "checks_per_order": len(P.CHECKS),
        "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "per_check": scored["per_check"],
        "matrix": scored["matrix"],
        "prompt_parts": [{"name": p_["name"], "chars": len(p_["text"])}
                        for p_ in (first["parts"] if first else [])],
        "raw_text": (first["raw"] if first else ""),
        "max_tokens": MAX_TOKENS,
        "thinking": thinking,
        "prompt_version": a.prompt,
        "records": records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-26s %s" % ("run", a.run_id))
    print("%-26s %s of %s  (%s%%)" % ("answered", o["answered"], o["checks_scored"],
                                     o["answered_pct"]))
    print("%-26s %s%%" % ("accuracy (answered)", o["accuracy_pct"]))
    print("%-26s %s  (%s%% of gold defects)" % ("FALSE CLEAN", o["false_clean"],
                                                o["false_clean_rate_pct"]))
    print("%-26s %s  (%s%% of gold clean)" % ("false alarm", o["false_alarm"],
                                              o["false_alarm_rate_pct"]))
    for c, pc in scored["per_check"].items():
        print("  %-12s accuracy %s%%  (gold %s)" % (c, pc["accuracy_pct"], pc["gold_total"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
