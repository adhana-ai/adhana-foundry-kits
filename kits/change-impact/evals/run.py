"""Run the matcher over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>              # the real run, ONE call per message
    python -m evals.run --run-id t000 --stub               # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5           # a costed toe in the water

⚠︎ ONE CALL PER MESSAGE, COUNTED BEFORE IT IS MADE — same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                      # noqa: E402
from src import adapters                                # noqa: E402
from src import config, match as M, block                # noqa: E402
from src.match import MAX_TOKENS                          # noqa: E402
from src import prompt as P                                 # noqa: E402
from evals import scoring as S                                # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It always answers the FIRST candidate listed (or NONE with
    no candidates) with change_type=None -- an honestly mediocre checker that exercises
    block -> prompt -> call -> parse -> impact -> score end to end without a key. It is NOT a
    baseline; evals/baseline.py is."""
    marker = "CANDIDATES\n----------\n"
    cand_block = user.split(marker, 1)[-1].split("\n\nReturn a JSON", 1)[0] if marker in user else ""
    lines = [l for l in cand_block.splitlines() if l.strip().startswith("REC-")]
    match = lines[0].split(" -- ")[0].strip() if lines else "NONE"
    return {"text": json.dumps({"match": match, "change_type": None, "new_value": None,
                                "citation": None}),
           "input_tokens": len(user) // 4, "output_tokens": 20, "raw": {"stub": True}}


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
    gold = M.load_gold()
    vendors = M.vendors_by_id()
    vsku = M.records_by_vendor_sku()
    records = M.records_by_id()
    messages = M.load_messages()
    if a.limit:
        messages = messages[:a.limit]

    print("run      : %s" % a.run_id)
    print("messages : %d   (one call per message)" % len(messages))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    print("prompt   : %s" % a.prompt)
    if not a.stub:
        print(BUDGET.plan(len(messages), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted — nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(messages))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    rows, lat, tin, tout, failures = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, msg in enumerate(messages, 1):
        v = vendors[msg["vendor_id"]]
        t0 = time.time()
        r = M.check(cfg, msg, v, vsku, complete=complete, thinking=thinking, prompt=a.prompt)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        row = {"message_id": r["message_id"], "vendor_id": r["vendor_id"],
              "candidates": r["candidates"], "match": r["match"], "change_type": r["change_type"],
              "new_value": r["new_value"], "citation": r["citation"], "parsed": r["parsed"],
              "finish_reason": r.get("finish_reason"), "input_tokens": r.get("input_tokens"),
              "output_tokens": r.get("output_tokens"), "reasoning_tokens": r.get("reasoning_tokens"),
              "latency_ms": ms}
        if not r["parsed"]:
            row["raw_text"] = r.get("raw", "")
        rows.append(row)
        print("  %2d/%d  %-11s cands=%d  match=%-10s %s"
              % (i, len(messages), r["message_id"], len(r["candidates"]), str(r["match"]),
                 "" if r["parsed"] else "*** UNPARSEABLE ***"))

    scored = S.score(rows, gold, records)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    bstats = block.stats(messages, vendors, vsku, gold)

    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "messages": len(rows),
        "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "blocking_stats": bstats,
        "scores": scored["overall"],
        "per_change_type": scored["per_change_type"],
        "prompt_parts": [{"name": p_["name"], "chars": len(p_["text"])}
                        for p_ in (first["parts"] if first else [])],
        "raw_text": (first["raw"] if first else ""),
        "max_tokens": MAX_TOKENS,
        "thinking": thinking,
        "prompt_version": a.prompt,
        "records": rows,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-26s %s" % ("run", a.run_id))
    print("%-26s %s%%" % ("match accuracy", o["match_accuracy_pct"]))
    print("%-26s %s%%" % ("impact accuracy", o["impact_accuracy_pct"]))
    print("%-26s %s  (%s%% of gold real matches)" % ("false NONE", o["false_none"], o["false_none_rate_pct"]))
    print("%-26s %s  (%s%% of gold NONE cases)" % ("false match", o["false_match"], o["false_match_rate_pct"]))
    print("%-26s %s" % ("abstained UNSURE", o["abstained_unsure"]))
    print("%-26s %s / %s" % ("blocking recall", bstats["true_match_surviving_blocking"],
                             bstats["messages_with_a_true_match"]))
    for ct, pc in scored["per_change_type"].items():
        print("  %-14s match %s%%  impact %s%%  (n=%d)"
              % (ct, pc["match_accuracy_pct"], pc["impact_accuracy_pct"], pc["n"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
