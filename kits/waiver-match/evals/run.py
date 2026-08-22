"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-waiver-match           # the real run, one call per package
    python -m evals.run --run-id t000 --stub                 # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline       # free, tone floor, no model
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
        return {r["pkg_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """A provider that is not there. It answers the two fields a regex can honestly read off the
    prompt and nulls the rest, which is enough to prove every downstream step -- parse, span,
    the pure-code flag, the self-check and all four graders -- without a key and without spend."""
    import re
    out = {}
    m = re.search(r"Package\n-+\n(.+)", user)
    out["package_id"] = m.group(1).strip() if m else None
    m = re.search(r"Period Through\n-+\n(.+)", user)
    out["period_through"] = m.group(1).strip() if m else None
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
    records, flags, checks, lat = {}, {}, {}, []
    tin = tout = 0
    out_tokens_all = []
    failures = []
    first = None
    t_all = time.time()
    for i, pkg_id in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(pkg_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(pkg_id), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": pkg_id, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (pkg_id, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": pkg_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"), "max_tokens": MAX_TOKENS,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (pkg_id, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if r.get("output_tokens"):
            out_tokens_all.append(r["output_tokens"])
        records[pkg_id] = r["fields"]
        flags[pkg_id] = r.get("needs_hold")
        checks[pkg_id] = r.get("self_check") or {}
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), pkg_id, lat[-1] if lat else 0))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, checks, golds)

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
        # ⚑ THE CEILING IS A MEASUREMENT, SO THE EVIDENCE FOR IT SHIPS WITH THE RUN. The largest
        # reply this run produced, against the cap it was produced under, is the whole basis for
        # MAX_TOKENS being what it is -- a cap defended by a remembered number is a guess.
        "output_tokens_max": max(out_tokens_all) if out_tokens_all else None,
        "output_tokens_min": min(out_tokens_all) if out_tokens_all else None,
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
    hf = flag_scored["hold_flag"]
    at = flag_scored["attribution"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %s" % ("coverage-gap accuracy", flag_scored["accuracy"]))
    print("%-34s %s" % ("uncovered-package recall", flag_scored["recall"]))
    print("%-34s %d" % ("packages with a gap, missed", flag_scored["false_negative"]))
    print("%-34s %d/%d exact" % ("uncovered COUNT", flag_scored["count_exact"], len(docs)))
    print("%-34s party %d/%d  reason %d/%d  both %d/%d"
          % ("gap attribution", at["party_correct"], at["scored_on"],
             at["reason_correct"], at["scored_on"], at["both_correct"], at["scored_on"]))
    if at["reason_confusion"]:
        print("%-34s %s" % ("  reason confusions",
                            "  ".join("%s x%d" % (k, v)
                                      for k, v in at["reason_confusion"].items())))
    print("%-34s acc %s  recall %s  precision %s"
          % ("needs_hold vs gold", hf["accuracy"], hf["recall"], hf["precision"]))
    print("%-34s %d reply(s) disagreed with themselves (%d named a party the package does not "
          "list); %d of %d verdict errors were visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_themselves"],
             cons["replies_naming_a_party_not_in_the_package"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    if out_tokens_all:
        print("%-34s %d..%d against a cap of %d"
              % ("output tokens", min(out_tokens_all), max(out_tokens_all), MAX_TOKENS))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
