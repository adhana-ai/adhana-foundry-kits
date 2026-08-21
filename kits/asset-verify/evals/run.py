"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per statement
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline    # free, rules-and-regex, no model

⚠︎ ONE CALL PER STATEMENT, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import adapters                        # noqa: E402
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
    """A deterministic fake provider. Reads the header lines straight out of the prompt and
    returns null for everything else -- exercises the whole pipeline for free."""
    import re
    out = {}
    m = re.search(r"Statement Holder\n-+\n(.+)", user)
    out["account_holder"] = m.group(1).strip() if m else None
    m = re.search(r"Institution\n-+\n(.+)", user)
    out["institution"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--baseline", action="store_true",
                    help="run the rules-and-regex extractor instead of a model: no key, no spend")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
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
    records, flags, reserves, lat = {}, {}, {}, []
    tin = tout = 0
    failures = []
    first = None
    t_all = time.time()
    for i, stmt_id in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(stmt_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(stmt_id), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": stmt_id, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (stmt_id, str(exc)[:90]))
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
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[stmt_id] = r["fields"]
        flags[stmt_id] = r.get("large_deposit_flag")
        reserves[stmt_id] = r.get("computed_reserve_value")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), stmt_id, lat[-1] if lat else 0))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(flags, golds)

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
    print("\n%-22s %s" % ("run", a.run_id))
    print("%-22s %d/%d  (%s)" % ("extraction accuracy",
                                 sum(1 for c in scored["cells"]
                                     if c["stated"] and c["verdict"] == "hit"),
                                 o["extraction_cells"], o["extraction_accuracy"]))
    print("%-22s %d/%d  (%s)" % ("refusal accuracy", o["refusal_cells"] - o["hallucinations"],
                                 o["refusal_cells"], o["refusal_accuracy"]))
    print("%-22s %s" % ("large-deposit recall", flag_scored["recall"]))
    print("%-22s %d" % ("false negatives", flag_scored["false_negative"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
