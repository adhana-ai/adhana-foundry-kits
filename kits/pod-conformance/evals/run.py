"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per record
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline   # free, tone floor, no model
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from src.extract import MAX_TOKENS             # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["stmt_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    import re
    out = {}
    m = re.search(r"Shipment\n-+\n(.+)", user)
    out["shipment_id"] = m.group(1).strip() if m else None
    m = re.search(r"Carrier\n-+\n(.+)", user)
    out["carrier_name"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    docs = EX.documents()
    if a.limit:
        docs = docs[:a.limit]

    if not a.stub and not a.baseline:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free.")
        print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(len(docs))

    complete = stub_complete if a.stub else None

    def process_one(item):
        i, stmt_id = item
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(stmt_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(stmt_id), fields, complete=complete)
        except Exception as exc:
            return i, stmt_id, None, str(exc)[:300], time.time() - t0
        return i, stmt_id, r, None, time.time() - t0

    records, flags, lat = {}, {}, []
    tin = tout = 0
    failures = []
    first = None
    t_all = time.time()

    # ⚑ CONCURRENT, LIVE RUNS ONLY — added 2026-08-21, operator direction. --stub and --baseline
    # are already free/instant (no HTTP call) and stay sequential (workers=1); a live run is ~110
    # real HTTP calls and was the long pole in a kit build. `EX.extract` is a pure function with no
    # shared mutable state, and `complete()` in src/adapters already retries transient failures
    # (429/5xx) with backoff, so nothing new was added here for that — concurrency just makes
    # hitting that path more likely than the old one-at-a-time loop ever did. `pool.map` preserves
    # doc order for the prints/`first` sample below even though completion order is not
    # guaranteed. EVAL_WORKERS is the one knob to raise if a real run shows headroom.
    #
    # ⚑ THE DEFAULT WENT 5 -> 12 ON 2026-08-22, AND THE REASON IS THAT THE OLD REASON EXPIRED.
    # It was 5 because no concurrency ceiling was documented anywhere in this repo, and a
    # guessed-high default is how a shared key gets rate-limited for everybody using it. A ceiling
    # is documented now, it is account-level, and it is two orders of magnitude above this number —
    # so 5 had stopped being conservative and had merely become stale. 12 is still far below the
    # limit: it is chosen to be polite to whichever provider a forker points this at, not to be the
    # most the wire will carry. If you hold the key and know your own ceiling, raise it with the
    # environment variable and change nothing else.
    workers = 1 if (a.stub or a.baseline) else int(os.environ.get("EVAL_WORKERS", "12"))
    items = list(enumerate(docs, 1))
    if workers > 1:
        print("  running %d docs with %d concurrent workers" % (len(items), workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, stmt_id, r, err, dt in pool.map(process_one, items):
            if err is not None:
                failures.append({"doc": stmt_id, "error": err})
                print("  !! %-10s %s" % (stmt_id, err))
                continue
            if not r.get("parsed", True):
                why = r.get("finish_reason")
                cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
                failures.append({"doc": stmt_id,
                                 "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                          % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                             r.get("output_tokens") or 0, MAX_TOKENS),
                                 "output_tokens": r.get("output_tokens"), "max_tokens": MAX_TOKENS,
                                 "finish_reason": why, "at_ceiling": cut,
                                 "raw_text": (r.get("raw_text") or "")[:4000]})
                print("  !! %-10s reply did not parse (finish_reason=%s)" % (stmt_id, why))
                continue
            lat.append(int(dt * 1000))
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
            records[stmt_id] = r["fields"]
            flags[stmt_id] = r.get("needs_review")
            if first is None:
                first = r
            print("  %3d/%-3d %-10s %d ms" % (i, len(docs), stmt_id, lat[-1] if lat else 0))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "flag_scores": flag_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": MAX_TOKENS,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    cons = flag_scored["consistency"]
    rf = flag_scored["review_flag"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-32s %s" % ("run", a.run_id))
    print("%-32s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-32s %s" % ("delivery_complete accuracy", flag_scored["accuracy"]))
    print("%-32s %s" % ("incomplete-delivery recall", flag_scored["recall"]))
    print("%-32s %d" % ("incomplete deliveries missed", flag_scored["false_negative"]))
    print("%-32s acc %s  recall %s  precision %s"
          % ("needs_review vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-32s %d reply(s) disagreed with their own numbers; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_numbers"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
