"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per document
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 3        # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed. "Run once, for real" is the published claim of every kit
here, so the thing that spends must say what it is about to spend first.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, extract as EX          # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["nct_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """A deterministic fake provider. It reads the header lines straight out of the prompt and
    returns null for everything else — so it exercises segment/select/prompt/parse/judge end to
    end and posts an honest, mediocre score. It is NOT a baseline: see --baseline for that."""
    import re
    out = {}
    m = re.search(r"NCT Number:\s*(\S+)", user)
    out["nct_id"] = m.group(1) if m else None
    m = re.search(r"Brief Title:\s*(.+)", user)
    out["brief_title"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--baseline", action="store_true",
                    help="run the rules-and-regex extractor instead of a model: no key, no spend, "
                         "scored by the same judge so the two are comparable")
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
        print("about to make %d live call(s) with model %r via %s"
              % (len(docs), cfg.get("model"), cfg.get("provider")))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")

    complete = stub_complete if a.stub else None
    records, lat, tin, tout, failures = {}, [], 0, 0, []
    t_all = time.time()
    for i, nct in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = {"fields": B.extract(EX.load_doc(nct), fields), "sections_used": [],
                     "prompt_parts": [], "input_tokens": 0, "output_tokens": 0, "raw_text": ""}
            else:
                r = EX.extract(cfg, EX.load_doc(nct), fields, complete=complete)
        except Exception as exc:
            # A failed document is RECORDED, not retried into a bill and not dropped. A run that
            # silently skips its failures reports a rate for the documents that happened to work.
            failures.append({"doc": nct, "error": str(exc)[:300]})
            print("  !! %-14s %s" % (nct, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            # Counted where every other lost document is counted. It cost money and produced no
            # answer -- exactly like a 503 -- and scoring it as nine misses would publish a
            # parsing defect as a model quality figure, which is what run 1 did.
            failures.append({"doc": nct, "error": "reply did not parse as JSON (truncated?) — "
                                                  "%d output tokens" % (r.get("output_tokens") or 0)})
            print("  !! %-14s reply did not parse" % nct)
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[nct] = r["fields"]
        if i == 1:
            first = r
        print("  %3d/%-3d %-14s %d ms" % (i, len(docs), nct, lat[-1]))

    golds = load_gold()
    scored = J.score(fields, records, golds)
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
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if records else [])],
        "sections_used": (first["sections_used"] if records else []),
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
    print("%-22s %d" % ("hallucinations", o["hallucinations"]))
    print("%-22s %s of %s returned" % ("values with a span",
                                       o["values_with_span"], o["values_returned"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
