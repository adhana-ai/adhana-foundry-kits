"""Run the resolver over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>             # the real run, ONE call per case
    python -m evals.run --run-id t000 --stub              # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5          # a costed toe in the water

⚠︎ ONE CALL PER CASE, COUNTED BEFORE IT IS MADE -- same discipline as every sibling kit's run.py.
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
from src import config, resolve as R                # noqa: E402
from src.resolve import MAX_TOKENS                  # noqa: E402
from src import prompt as P                          # noqa: E402
from evals import scoring as S                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It always answers `internal` with the discrepant line's own
    BOL/received values and a generic notice -- an honestly mediocre resolver that exercises
    prompt -> call -> parse -> score end to end without a key. It is NOT a baseline;
    evals/baseline.py is."""
    marker = "Lines:\n"
    block = user.split(marker, 1)[-1] if marker in user else user
    first_line = next((l for l in block.splitlines() if l.strip().startswith("SKU")), "")
    parts = first_line.split()
    sku = parts[0] if parts else "SKU-0000"
    reply = {"liable_party": "internal", "discrepant_sku": sku, "doc_a": "bol", "qty_a": 0,
            "doc_b": "received", "qty_b": 0, "delta": 0,
            "notice_text": "stub reply -- proves the wiring, not the call."}
    return {"text": json.dumps(reply), "input_tokens": len(user) // 4, "output_tokens": 40,
           "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--no-thinking", action="store_true",
                    help="disable provider-side reasoning. Off by default; see data-reconcile's "
                         "own note on why a provider default of ON can burn the output ceiling.")
    ap.add_argument("--prompt", default=P.DEFAULT_PROMPT,
                    help="which SYSTEM variant to send: %s" % ", ".join(sorted(P.SYSTEMS)))
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    gold = R.load_gold()
    cases = R.cases()
    if a.limit:
        cases = cases[:a.limit]

    print("run      : %s" % a.run_id)
    print("cases    : %d   calls: %d  (one per case)" % (len(cases), len(cases)))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    print("prompt   : %s" % a.prompt)
    if not a.stub:
        print(BUDGET.plan(len(cases), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted -- nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(cases))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    records, lat, tin, tout, failures = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        r = R.check(cfg, case, complete=complete, thinking=thinking, prompt=a.prompt)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        rec = {"case_id": case["case_id"], "liable_party": r["liable_party"],
              "discrepant_sku": r["discrepant_sku"], "doc_a": r["doc_a"], "doc_b": r["doc_b"],
              "qty_a": r["qty_a"], "qty_b": r["qty_b"], "delta": r["delta"],
              "notice_text": r["notice_text"], "parsed": r["parsed"],
              "finish_reason": r.get("finish_reason"),
              "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
              "reasoning_tokens": r.get("reasoning_tokens"), "latency_ms": ms}
        if not r["parsed"]:
            rec["raw_text"] = r.get("raw", "")
        records.append(rec)
        print("  %2d/%d  %-13s %-22s %s"
             % (i, len(cases), case["case_id"], r["liable_party"] or "—",
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
        "cases": len(records),
        "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "per_liable_party": scored["per_liable_party"],
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
    print("\n%-32s %s" % ("run", a.run_id))
    print("%-32s %s of %s  (%s%%)" % ("answered", o["answered"], o["cases_scored"],
                                     o["answered_pct"]))
    print("%-32s %s%%" % ("liable_party accuracy", o["liable_accuracy_pct"]))
    print("%-32s %s  (%s%% of gold insufficient_evidence)" % ("FALSE CONFIDENT CALL",
                                                              o["false_confident_call"],
                                                              o["false_confident_call_rate_pct"]))
    print("%-32s %s  (%s%% of trap cases)" % ("wrong_sku_exception_misread",
                                              o["wrong_sku_exception_misread"],
                                              o["wrong_sku_exception_misread_rate_pct"]))
    print("%-32s %s%%" % ("discrepant_sku accuracy", o["discrepant_sku_accuracy_pct"]))
    print("%-32s %s%%" % ("quantity_citation accuracy", o["quantity_citation_accuracy_pct"]))
    for lp, pl in scored["per_liable_party"].items():
        print("  %-22s accuracy %s%%  (gold %s)" % (lp, pl["accuracy_pct"], pl["gold_total"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
