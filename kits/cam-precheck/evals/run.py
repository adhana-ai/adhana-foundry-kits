"""Run the pre-checker over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-cam-precheck        # the real run, one call per line
    python -m evals.run --run-id t000 --stub              # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-tone --baseline tone   # free, note-register floor, no model
    python -m evals.run --run-id b001-name --baseline name   # free, category-name floor, no model
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
        return {r["line_ref"]: r for r in (json.loads(line) for line in f if line.strip())}


def stub_complete(cfg, system, user, max_tokens=1024, thinking=None):
    """Enough of a reply to prove the wiring end to end, and deliberately not enough to score
    well: two verbatim fields regexed out of the prompt, no arithmetic at all. A stub that
    answered correctly would make a broken pipeline look healthy."""
    import re
    out = {}
    m = re.search(r"Statement Line\n-+\n(.+)", user)
    out["line_id"] = m.group(1).strip() if m else None
    m = re.search(r"Expense Class\n-+\n(.+)", user)
    out["expense_class"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "finish_reason": "stop",
            "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--baseline", choices=("tone", "name"), default=None)
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
    out_lengths = []
    failures = []
    first = None
    t_all = time.time()
    for i, line_ref in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(line_ref), fields, mode=a.baseline)
            else:
                r = EX.extract(cfg, EX.load_doc(line_ref), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": line_ref, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (line_ref, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": line_ref,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"), "max_tokens": MAX_TOKENS,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (line_ref, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if r.get("output_tokens"):
            out_lengths.append(r["output_tokens"])
        records[line_ref] = r["fields"]
        flags[line_ref] = r.get("needs_review")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), line_ref, lat[-1] if lat else 0))

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
        "model": "stub" if a.stub else (("rules-baseline-" + a.baseline) if a.baseline
                                        else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "lines": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        # ⚑ MAX_TOKENS IS A MEASUREMENT ON THIS KIT, SO THE RUN RECORDS WHAT IT ACTUALLY NEEDED.
        # A ceiling nobody can see the distance to is a guess wearing a number.
        "output_tokens_max": max(out_lengths) if out_lengths else None,
        "output_tokens_min": min(out_lengths) if out_lengths else None,
        "max_tokens": MAX_TOKENS,
        "replies_at_ceiling": sum(1 for n in out_lengths if n >= MAX_TOKENS),
        # ⚑ THIS KIT'S OWN DISCRIMINATOR. No sibling kit's result shape carries an
        # `arithmetic_accuracy_pct` -- no other one asks a model to compute a dollar figure through
        # four dependent stages and then grades the figure and the verdict it produced separately.
        "scores": dict(scored["overall"],
                       arithmetic_accuracy_pct=(None
                                                if flag_scored["arithmetic"]["accuracy"] is None
                                                else round(100.0 *
                                                           flag_scored["arithmetic"]["accuracy"],
                                                           2)),
                       verdict_accuracy_pct=round(100.0 * flag_scored["accuracy"], 2),
                       review_flag_recall_pct=(None if flag_scored["review_flag"]["recall"] is None
                                               else round(100.0 *
                                                          flag_scored["review_flag"]["recall"], 2))),
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "flag_scores": flag_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    cons = flag_scored["consistency"]
    rf = flag_scored["review_flag"]
    ar = flag_scored["arithmetic"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %d/%d  (%s)" % ("arithmetic within $%.2f" % ar["tolerance_usd"],
                                 ar["hits"], ar["cells"], ar["accuracy"]))
    print("%-34s %s" % ("line_ok accuracy", flag_scored["accuracy"]))
    print("%-34s %s" % ("wrongly-billed recall", flag_scored["recall"]))
    print("%-34s %d" % ("wrongly-billed lines missed", flag_scored["false_negative"]))
    print("%-34s acc %s  recall %s  precision %s"
          % ("needs_review vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-34s %d reply(s) disagreed with their own numbers; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_numbers"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    if out_lengths:
        print("%-34s %d..%d against a ceiling of %d"
              % ("output tokens", min(out_lengths), max(out_lengths), MAX_TOKENS))
    print("\ntraps (verdict right / n):")
    for name, t in sorted(flag_scored["traps"].items()):
        print("  %-32s %2d/%-2d   arithmetic %2d/%-2d"
              % (name, t["verdict_right"], t["n"], t["arithmetic_right"], t["n"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
