"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-commission-audit          # the real run, one call per claim
    python -m evals.run --run-id t000 --stub                    # no key, no spend, proves wiring
    python -m evals.run --run-id b000-rules --baseline          # free, tone floor, no model
"""
import argparse
import json
import os
import sys
import time

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
        return {r["claim_ref"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """Two fields off the prompt text, so the wiring is provable for free. It is deliberately NOT
    a second implementation of the extractor -- a stub that answers well hides the run."""
    import re
    out = {}
    m = re.search(r"Claim Line\n-+\n(.+)", user)
    out["claim_id"] = m.group(1).strip() if m else None
    m = re.search(r"Folio Status\n-+\n(.+)", user)
    out["folio_status"] = m.group(1).strip() if m else None
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
    records, flags, lat = {}, {}, []
    tin = tout = 0
    failures = []
    first = None
    t_all = time.time()
    for i, claim_ref in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(claim_ref), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(claim_ref), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": claim_ref, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (claim_ref, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": claim_ref,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"), "max_tokens": MAX_TOKENS,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (claim_ref, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[claim_ref] = r["fields"]
        flags[claim_ref] = r.get("needs_recovery")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), claim_ref, lat[-1] if lat else 0))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None   # noqa: E731

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "claims": len(records),
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
    rf = flag_scored["recovery_flag"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-32s %s" % ("run", a.run_id))
    print("%-32s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-32s %s" % ("claim_valid accuracy", flag_scored["accuracy"]))
    print("%-32s %s" % ("unowed-claim recall", flag_scored["recall"]))
    print("%-32s %d" % ("unowed claims missed", flag_scored["false_negative"]))
    print("%-32s acc %s  recall %s  precision %s"
          % ("needs_recovery vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-32s %d reply(s) disagreed with their own values; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_numbers"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    print("by case:")
    for k, v in flag_scored["by_case"].items():
        print("  %-22s %2d/%-2d  %s" % (k, v["correct"], v["n"], v["accuracy"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
