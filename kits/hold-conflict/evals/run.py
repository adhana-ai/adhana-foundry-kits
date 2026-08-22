"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-hold-conflict --yes        # the real run, one call per review
    python -m evals.run --run-id t000 --stub                     # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-holds --baseline holds     # free, over-cautious floor
    python -m evals.run --run-id b001-notes --baseline notes     # free, tone floor
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
        return {r["case_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def rescore(path):
    """Re-score a result file that already exists, from its own recorded cells. FREE -- nothing is
    called and nothing is re-extracted.

    ⚑ WHY THIS EXISTS. evals/judge.py's binding-hold grader counted an UNANSWERED record as a
    correct "nothing binds", because gold's value there is null and so was the missing reply. Run
    r002 lost one record to a client-side socket timeout and the grader published 55 of 55 over 54
    replies. Fixing the grader after two paid runs leaves a choice between re-spending 110 calls
    and shipping a result file scored by code that no longer exists.

    Neither is necessary: every result file already carries `cells`, one row per (record, field)
    with the model's own returned value, so the reply set is recoverable exactly. This rebuilds it
    and re-runs the SAME judge the harness runs, in process, then rewrites the score blocks and
    prints what moved. It is deterministic and re-runnable, so a reader can reproduce the
    published number from the committed file with no key.

    ⚠︎ WHAT IT CANNOT REBUILD, STATED RATHER THAN QUIETLY APPROXIMATED: `span` is recorded as a
    boolean per cell, not as offsets. The judge only ever tests it for truthiness, so the span
    rate comes out identical -- but this is not a general-purpose replay and must never grow into
    one. A grader that needs anything the cells do not carry needs a re-run, not a wider rebuild.
    """
    d = json.load(open(path, encoding="utf-8"))
    fields = EX.load_fields()
    records = {}
    for c in d.get("cells") or []:
        records.setdefault(c["doc"], {})[c["field"]] = {
            "value": c["got"], "spannable": c.get("spannable", True),
            "span": {"section": "recorded"} if c.get("span") else None}
    flags = {doc: EX.compute({k: v["value"] for k, v in rec.items()})
             for doc, rec in records.items()}

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, golds)
    before = dict(d.get("scores") or {})
    d["scores"] = dict(scored["overall"],
                       hold_identification_accuracy=flag_scored["binding_hold"]["accuracy"],
                       eligibility_accuracy=flag_scored["accuracy"],
                       frozen_recall=flag_scored["recall"])
    d["by_field"] = scored["by_field"]
    d["cells"] = scored["cells"]
    d["flag_scores"] = flag_scored
    d["rescored_from_cells"] = True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)

    print("rescored %s from its own %d recorded cells" % (os.path.basename(path), len(d["cells"])))
    for k in sorted(set(before) | set(d["scores"])):
        if before.get(k) != d["scores"].get(k):
            print("  %-34s %s -> %s" % (k, before.get(k), d["scores"].get(k)))
    bh = flag_scored["binding_hold"]
    print("  binding hold: %d correct, %d unanswered, of %d gold records"
          % (bh["correct"], bh.get("unanswered", 0), bh["of"]))


def stub_complete(cfg, system, user, max_tokens=1024, thinking=None):
    """Enough of a reply to prove the wiring end to end, for free: two verbatim fields read
    straight back out of the prompt. It answers nothing that needed reasoning, which is exactly
    what makes a stub run's low score readable as "the wiring works" rather than "the model is
    bad"."""
    import re
    out = {}
    m = re.search(r"Record Series\n-+\n(.+)", user)
    out["series_id"] = m.group(1).strip() if m else None
    m = re.search(r"Record Category\n-+\n(.+)", user)
    out["record_category"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", default=None,
                    help="re-score an existing results/eval-*.json from its own recorded cells. "
                         "Free: nothing is called. See rescore().")
    if "--rescore" in sys.argv:
        a = ap.parse_known_args()[0]
        return rescore(a.rescore)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--baseline", nargs="?", const="holds", default=None,
                    choices=["holds", "notes"])
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="override src.extract.MAX_TOKENS -- used once, to MEASURE what this "
                         "shape of reply actually costs before the ceiling was set")
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
    out_tokens_all = []
    failures = []
    first = None
    t_all = time.time()
    for i, case_id in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(case_id), fields, floor=a.baseline)
            else:
                r = EX.extract(cfg, EX.load_doc(case_id), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": case_id, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (case_id, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= ceiling
            failures.append({"doc": case_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, ceiling),
                             "output_tokens": r.get("output_tokens"), "max_tokens": ceiling,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (case_id, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if r.get("output_tokens"):
            out_tokens_all.append(r["output_tokens"])
        records[case_id] = r["fields"]
        flags[case_id] = r.get("needs_review")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), case_id, lat[-1] if lat else 0))

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
        "model": "stub" if a.stub else (("rules-baseline-%s" % a.baseline) if a.baseline
                                        else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "baseline_floor": a.baseline,
        "records": len(records),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        # ⚑ THE CEILING MEASUREMENT, RECORDED BY EVERY RUN. MAX_TOKENS is not a guess in this kit
        # and the evidence has to survive in the run record, not in a commit message.
        "output_tokens_max": max(out_tokens_all) if out_tokens_all else None,
        "output_tokens_min": min(out_tokens_all) if out_tokens_all else None,
        "scores": dict(scored["overall"],
                       hold_identification_accuracy=flag_scored["binding_hold"]["accuracy"],
                       eligibility_accuracy=flag_scored["accuracy"],
                       frozen_recall=flag_scored["recall"]),
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "flag_scores": flag_scored,
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
    bh = flag_scored["binding_hold"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %d/%d  (%s)" % ("binding hold identified", bh["correct"], bh["of"],
                                 bh["accuracy"]))
    print("%-34s %s" % ("eligibility accuracy", flag_scored["accuracy"]))
    print("%-34s %s" % ("frozen-series recall", flag_scored["recall"]))
    print("%-34s %d" % ("frozen series released in error", flag_scored["false_negative"]))
    print("%-34s acc %s  recall %s  precision %s"
          % ("needs_review vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-34s %d reply(s) disagreed with their own values; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_values"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    print("\nby class (the corpus's own claim about WHY each record is what it is):")
    for klass in sorted(flag_scored["by_class"]):
        d = flag_scored["by_class"][klass]
        print("  %-24s verdict %2d/%-2d   binding hold %2d/%-2d"
              % (klass, d["verdict_correct"], d["n"], d["hold_correct"], d["n"]))
    if out_tokens_all:
        print("\noutput tokens: min %d  max %d  cap %d"
              % (min(out_tokens_all), max(out_tokens_all), ceiling))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
