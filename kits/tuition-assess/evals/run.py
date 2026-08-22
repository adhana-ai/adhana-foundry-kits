"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-tuition-assess          # the real run, one call per record
    python -m evals.run --run-id t000 --stub                  # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline        # free, tone floor, no model
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
        return {r["stmt_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    import re
    out = {}
    m = re.search(r"Student Account\n-+\n(.+)", user)
    out["student_account_id"] = m.group(1).strip() if m else None
    m = re.search(r"Residency Tier\n-+\n(.+)", user)
    out["residency_tier"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="override the ceiling for a calibration run; the shipped value is a "
                         "MEASUREMENT and this is how it was measured")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    docs = EX.documents()
    if a.limit:
        docs = docs[:a.limit]

    ceiling = a.max_tokens or MAX_TOKENS
    if a.max_tokens:
        EX.MAX_TOKENS = a.max_tokens

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
    out_tokens, finishes = [], {}
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
        why = r.get("finish_reason")
        if why:
            finishes[why] = finishes.get(why, 0) + 1
        if not r.get("parsed", True):
            cut = (why == "length") or (r.get("output_tokens") or 0) >= ceiling
            failures.append({"doc": stmt_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, ceiling),
                             "output_tokens": r.get("output_tokens"), "max_tokens": ceiling,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (stmt_id, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if r.get("output_tokens") is not None:
            out_tokens.append(r["output_tokens"])
        records[stmt_id] = r["fields"]
        flags[stmt_id] = r.get("needs_review")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), stmt_id, lat[-1] if lat else 0))

    golds = load_gold()
    if a.limit:
        golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, golds)
    reason_scored = J.score_reasons(records, golds)
    sizes = J.variance_sizes(records, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        # ⚑ THE COUNT KEY IS `assessments`, NOT `documents`. One row of this corpus is one student
        # account's tuition assessment for one term; calling it a document would publish the wrong
        # noun everywhere downstream reads this file.
        "assessments": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        # ⚑ THE EVIDENCE BEHIND MAX_TOKENS, RECORDED ON EVERY RUN. A ceiling nobody measures is a
        # ceiling that silently truncates the day the corpus grows a longer note.
        "output_tokens_max": max(out_tokens) if out_tokens else None,
        "output_tokens_min": min(out_tokens) if out_tokens else None,
        "finish_reasons": finishes,
        "scores": scored["overall"],
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "flag_scores": flag_scored,
        "reason_scores": reason_scored,
        "variance_sizes": sizes,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": ceiling,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    cons = flag_scored["consistency"]
    rf = flag_scored["review_flag"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %s" % ("assessment_correct accuracy", flag_scored["accuracy"]))
    print("%-34s %s" % ("mis-assessment recall", flag_scored["recall"]))
    print("%-34s %d" % ("mis-assessments missed", flag_scored["false_negative"]))
    print("%-34s %s of %s  (%s)" % ("variance_reason on real variances", reason_scored["correct"],
                                    reason_scored["of"], reason_scored["accuracy"]))
    print("%-34s %d of %d" % ("reason named on a correct record", reason_scored["named_on_correct"],
                              reason_scored["named_on_correct_of"]))
    print("%-34s acc %s  recall %s  precision %s"
          % ("needs_review vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-34s %d reply(s) disagreed with their own numbers; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_numbers"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    print("%-34s max %s, min %s output tokens (cap %d); finish: %s"
          % ("ceiling headroom", out["output_tokens_max"], out["output_tokens_min"], ceiling,
             finishes or "n/a"))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
