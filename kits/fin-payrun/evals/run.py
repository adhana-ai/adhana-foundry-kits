"""Run the tracer over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>             # the real run, ONE call per invoice
    python -m evals.run --run-id t000 --stub               # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5           # a costed toe in the water

⚠︎ ONE CALL PER INVOICE INQUIRY, COUNTED BEFORE IT IS MADE -- same discipline as every sibling
kit's run.py. The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                   # noqa: E402
from src import adapters                           # noqa: E402
from src import config, payrun as C                  # noqa: E402
from src.payrun import MAX_TOKENS                     # noqa: E402
from src import prompt as P                             # noqa: E402
from evals import scoring as S                            # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It always answers `remitted` and drafts a reply claiming
    the payment already went out -- an honestly bad tracer, the worst-case version of exactly the
    failure this kit exists to catch. It exercises prompt -> call -> parse -> score end to end
    without a key. It is NOT a baseline; evals/baseline.py is."""
    marker = "VENDOR INQUIRY: "
    inquiry = user.split(marker, 1)[-1].splitlines()[0] if marker in user else ""
    reply = json.dumps({
        "current_stage": "remitted",
        "requires_ap_review": False,
        "stated_date": "2024-01-01",
        "reply": "This invoice has been paid -- payment was sent on 2024-01-01. (stub reply to: "
                 "%s)" % inquiry,
    })
    return {"text": reply, "input_tokens": len(user) // 4, "output_tokens": 60, "raw": {"stub": True}}


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
    gold = C.load_gold()
    invoices = C.invoices()
    if a.limit:
        invoices = invoices[:a.limit]

    print("run      : %s" % a.run_id)
    print("invoices : %d   calls: %d  (one per vendor inquiry)" % (len(invoices), len(invoices)))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    print("prompt   : %s" % a.prompt)
    print("max_tokens: %d" % MAX_TOKENS)
    if not a.stub:
        print(BUDGET.plan(len(invoices), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted -- nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(invoices))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    records, lat, tin, tout, failures = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, inv in enumerate(invoices, 1):
        t0 = time.time()
        r = C.check(cfg, inv, complete=complete, thinking=thinking, prompt=a.prompt)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        rec = {"invoice_id": inv["invoice_id"], "current_stage": r["current_stage"],
              "requires_ap_review": r["requires_ap_review"], "stated_date": r["stated_date"],
              "reply": r["reply"], "parsed": r["parsed"], "finish_reason": r.get("finish_reason"),
              "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
              "reasoning_tokens": r.get("reasoning_tokens"), "latency_ms": ms}
        if not r["parsed"]:
            rec["raw_text"] = r.get("raw", "")
        records.append(rec)
        print("  %2d/%d  %-16s -> %-24s %s"
              % (i, len(invoices), inv["invoice_id"], r["current_stage"] or "—",
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
        "invoices": len(records),
        "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "per_stage": scored["per_stage"],
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
    print("%-26s %s of %s  (%s%%)" % ("stage answered", o["stage_answered"],
                                     o["invoices_scored"], o["stage_answered_pct"]))
    print("%-26s %s%%" % ("stage accuracy", o["stage_accuracy_pct"]))
    print("%-26s %s%%" % ("requires_ap_review accuracy", o["review_accuracy_pct"]))
    print("%-26s %s of %s  (%s%%)" % ("FALSE PAID", o["false_paid"], o["false_paid_denominator"],
                                     o["false_paid_rate_pct"]))
    print("%-26s %s%%" % ("date accuracy", o["date_accuracy_pct"]))
    for s, ps in scored["per_stage"].items():
        print("  %-24s accuracy %s%%  (gold %s)" % (s, ps["accuracy_pct"], ps["gold_total"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
