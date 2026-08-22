"""Run the reconciler over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<kit>                # the real run, one call per pack
    python -m evals.run --run-id t000 --stub               # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-tag --baseline       # free, tag floor, no model
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
        return {r["rec_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """A deliberately PARTIAL stub: it reads the two identifiers off the prompt and answers nothing
    else. It exists to prove the wiring end to end for free -- segment, select, prompt, parse,
    locate, score -- not to fake a result. A stub that answered everything would make the harness
    look correct on a corpus it never read."""
    import re
    out = {}
    m = re.search(r"Component\n-+\n(.+)", user)
    out["component_id"] = m.group(1).strip() if m else None
    m = re.search(r"Part Reference\n-+\n(.+)", user)
    out["part_reference"] = m.group(1).strip() if m else None
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
    for i, rec_id in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(rec_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(rec_id), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": rec_id, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (rec_id, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": rec_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"), "max_tokens": MAX_TOKENS,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (rec_id, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[rec_id] = r["fields"]
        flags[rec_id] = r.get("escalate")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), rec_id, lat[-1] if lat else 0))

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
        "model": "stub" if a.stub else ("tag-floor-baseline" if a.baseline else cfg.get("model")),
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
    esc = flag_scored["escalate"]
    tag = flag_scored["tag_agrees"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    totals = sum(1 for c in scored["cells"]
                 if c["field"] in ("trail_hours", "trail_cycles") and c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %d/%d" % ("reconstructed totals exact", totals, 2 * len(records)))
    print("%-34s %s of %s  (%s)" % ("life_status, five-class",
                                    flag_scored["life_status_correct"],
                                    flag_scored["life_status_of"],
                                    flag_scored["life_status_accuracy"]))
    print("%-34s acc %s  recall %s  precision %s" % ("cleared / NOT cleared",
                                                     flag_scored["accuracy"],
                                                     flag_scored["recall"],
                                                     flag_scored["precision"]))
    print("%-34s %d" % ("NOT-cleared packs called cleared", flag_scored["false_negative"]))
    print("%-34s acc %s  recall %s  precision %s" % ("tag_agrees vs gold", tag["accuracy"],
                                                     tag["recall"], tag["precision"]))
    print("%-34s acc %s  recall %s  precision %s" % ("escalate vs gold", esc["accuracy"],
                                                     esc["recall"], esc["precision"]))
    print("%-34s %d disagreed with their own life arithmetic, %d with their own tag comparison; "
          "%d of %d status errors were visible without gold"
          % ("consistency diagnostics",
             cons["replies_disagreeing_with_own_life_arithmetic"],
             cons["replies_disagreeing_with_own_tag_comparison"],
             cons["errors_visible_without_gold"], cons["life_status_errors"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
