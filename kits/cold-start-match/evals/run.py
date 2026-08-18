"""Run the matcher over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>              # the real run, ONE call per request
    python -m evals.run --run-id t000 --stub               # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5           # a costed toe in the water

⚠︎ ONE CALL PER REQUEST, COUNTED BEFORE IT IS MADE -- same discipline as every sibling kit's
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
from src import block, config, match as M               # noqa: E402
from src import prompt as P                                # noqa: E402
from evals import scoring as S                               # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It always answers LIKE_ITEM for the first candidate listed
    and NOT_LIKE_ITEM for the rest -- an honestly mediocre checker that exercises block -> prompt
    -> call -> parse -> decide -> forecast end to end with no key. It is NOT a baseline;
    evals/baseline.py is."""
    marker = "CANDIDATES ("
    block_ = user.split(marker, 1)[-1] if marker in user else ""
    ids = [ln.split(" -- ")[0].strip() for ln in block_.splitlines() if ln.strip().startswith("ITM-")]
    verdicts = [{"item_id": iid, "verdict": "LIKE_ITEM" if i == 0 else "NOT_LIKE_ITEM",
               "reason": "stub"} for i, iid in enumerate(ids)]
    return {"text": json.dumps({"verdicts": verdicts}),
           "input_tokens": len(user) // 4, "output_tokens": 20 * max(1, len(ids)),
           "raw": {"stub": True}}


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
    gold = M.load_gold()
    history = M.load_history()
    requests = M.load_requests()
    if a.limit:
        requests = requests[:a.limit]

    print("run      : %s" % a.run_id)
    print("requests : %d   (one call per request)" % len(requests))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    if not a.stub:
        print(BUDGET.plan(len(requests), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted — nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(requests))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    rows_by_request, lat, tin, tout, failures = {}, [], 0, 0, 0
    first = None
    per_request_records = []
    t_all = time.time()
    for i, req in enumerate(requests, 1):
        t0 = time.time()
        r = M.check(cfg, req, history, complete=complete, thinking=thinking)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        rows_by_request[req["request_id"]] = r["per_candidate"]
        per_request_records.append({
            "request_id": r["request_id"], "category": r["category"],
            "candidates": r["candidates"], "per_candidate": r["per_candidate"],
            "like_item_ids": r["like_item_ids"], "draft": r["draft"], "parsed": r["parsed"],
            "finish_reason": r.get("finish_reason"), "input_tokens": r.get("input_tokens"),
            "output_tokens": r.get("output_tokens"), "reasoning_tokens": r.get("reasoning_tokens"),
            "latency_ms": ms})
        if not r["parsed"]:
            per_request_records[-1]["raw_text"] = r.get("raw", "")
        print("  %2d/%d  %-10s cands=%2d  like=%-2d  decision=%-20s %s"
             % (i, len(requests), r["request_id"], len(r["candidates"]),
                len(r["like_item_ids"]), r["draft"]["decision"],
                "" if r["parsed"] else "*** UNPARSEABLE ***"))

    scored = S.score(rows_by_request, gold)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    bstats = block.stats(requests, history, gold)

    drafts = [rec["draft"] for rec in per_request_records]
    from src import forecast as F
    dtally = F.tally(drafts)

    out = {
        "run_id": a.run_id, "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "requests": len(rows_by_request), "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "blocking_stats": bstats,
        "scores": scored["overall"],
        "draft_tally": dtally,
        "prompt_parts": [{"name": p_["name"], "chars": len(p_["text"])}
                        for p_ in (first["parts"] if first else [])],
        "raw_text": (first["raw"] if first else ""),
        "max_tokens": P.MAX_TOKENS,
        "thinking": thinking,
        "records": per_request_records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-26s %s" % ("run", a.run_id))
    print("%-26s %s%%" % ("precision", o["precision_pct"]))
    print("%-26s %s%%" % ("recall", o["recall_pct"]))
    print("%-26s %s%%" % ("f1", o["f1_pct"]))
    print("%-26s %s" % ("false merge", o["false_positive"]))
    print("%-26s %s" % ("missed match", o["false_negative"]))
    print("%-26s %s" % ("no verdict", o["no_verdict"]))
    print("%-26s %s / %s" % ("blocking recall", bstats["true_like_item_pairs_surviving"],
                             bstats["true_like_item_pairs"]))
    print("%-26s %s" % ("draft ready", dtally["counts"]["draft_ready"]))
    print("%-26s %s" % ("insufficient comps", dtally["counts"]["insufficient_comps"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
