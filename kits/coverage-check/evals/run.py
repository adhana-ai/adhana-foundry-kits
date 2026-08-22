"""Run the adjudicator over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-coverage-check          # the real run, one call per claim
    python -m evals.run --run-id t000-stub --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline        # free, opinion floor, no model
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
DATASET_VERSION = "coverage-check-2026-08-22-55claims"


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["claim_ref"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024, thinking=None):
    """A deliberately shallow stand-in: it copies two sections back and answers nothing that needs
    the rule. It exists to prove the wiring end to end for $0.00, not to look like a good run."""
    import re
    out = {}
    m = re.search(r"Claim\n-+\n(.+)", user)
    out["claim_id"] = m.group(1).strip() if m else None
    m = re.search(r"Coverage Plan\n-+\n(.+)", user)
    out["coverage_plan"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "finish_reason": "stop",
            "raw": {"stub": True}}


def _pct(v):
    return None if v is None else round(100.0 * v, 2)


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
    truncated = 0
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
        if r.get("finish_reason") == "length":
            truncated += 1
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
        flags[claim_ref] = r.get("needs_review")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), claim_ref, lat[-1] if lat else 0))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    flag_scored = J.score_flags(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    o = scored["overall"]
    nf = flag_scored["narrative_finding"]
    rf = flag_scored["review_flag"]
    br = flag_scored["by_branch"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")

    # ⚑ `coded_cause_trap_accuracy_pct` IS THIS RESULT SHAPE'S DISCRIMINATOR. No other kit's result
    # carries a "did the reply read the technician's story or the dealer's coded cause" figure,
    # because no other kit puts a coded classification and a free-text description of the same
    # event side by side and grades which one the reply believed.
    scores = {
        "extraction_cells": o["extraction_cells"],
        "extraction_accuracy": o["extraction_accuracy"],
        "extraction_accuracy_pct": _pct(o["extraction_accuracy"]),
        "refusal_cells": o["refusal_cells"],
        "refusal_accuracy": o["refusal_accuracy"],
        "hallucinations": o["hallucinations"],
        "values_returned": o["values_returned"],
        "values_with_span": o["values_with_span"],
        "non_spannable_fields": o["non_spannable_fields"],
        "span_rate": o["span_rate"],
        "span_rate_pct": _pct(o["span_rate"]),
        "coverage_accuracy_pct": _pct(flag_scored["accuracy"]),
        "coverage_denial_recall_pct": _pct(flag_scored["recall"]),
        "coverage_denial_precision_pct": _pct(flag_scored["precision"]),
        "coverage_unanswered": flag_scored["unanswered"],
        "narrative_finding_accuracy_pct": _pct(nf["accuracy"]),
        "coded_cause_trap_accuracy_pct": _pct(nf["cause_code_trap_accuracy"]),
        "coded_cause_trap_of": nf["cause_code_trap_of"],
        "plan_limit_trap_accuracy_pct": _pct((br.get("inside_terms") or {}).get("accuracy")),
        "plan_limit_trap_of": (br.get("inside_terms") or {}).get("of"),
        "recovery_flag_accuracy_pct": _pct(rf["accuracy"]),
        "recovery_flag_recall_pct": _pct(rf["recall"]),
        "recovery_flag_precision_pct": _pct(rf["precision"]),
        "month_arithmetic_disagreements":
            flag_scored["consistency"]["replies_disagreeing_with_own_dates"],
        "self_consistency_disagreements":
            flag_scored["consistency"]["replies_disagreeing_with_own_values"],
    }

    # ⚑ A RUN THAT CALLED NO PROVIDER HAS NO PROVIDER MEASUREMENTS, AND A STRUCTURAL ZERO IS NOT A
    # MEASUREMENT. The free floor makes no request: it has no latency, no tokens, no completion
    # ceiling and nothing that could be truncated. Publishing 0 for all of them would put the
    # baseline on the board as the fastest, cheapest, most reliable run on record -- true in the
    # sense that nothing happened, and false in every sense a reader would take it. Absent is the
    # third state; a sibling kit in this series paid for learning that one downstream, in a
    # comparability guard that asserted a token ceiling applied to a run that emitted no tokens.
    no_provider = bool(a.baseline)
    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "dataset_version": DATASET_VERSION,
        # `claims` is this kit's row unit. `documents` is written alongside it because several
        # tools in the estate look for that name first; they are the same number by construction.
        "claims": len(records),
        "documents": len(records),
        "failures": failures,
        "truncated_replies": None if no_provider else truncated,
        "latency_p50_ms": None if no_provider else p(0.50),
        "latency_p95_ms": None if no_provider else p(0.95),
        "latency_ms_all": None if no_provider else lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": None if no_provider else tin,
        "output_tokens_total": None if no_provider else tout,
        "scores": scores,
        "by_field": scored["by_field"],
        "by_branch": br,
        "cells": scored["cells"],
        "flag_scores": flag_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": None if no_provider else MAX_TOKENS,
        # This kit never sends a `thinking` parameter -- reasoning is left at the provider's own
        # default on every published run. Recorded as an explicit null rather than omitted, so a
        # reader can tell "left at default" from "nobody wrote it down".
        "thinking": None,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    cons = flag_scored["consistency"]
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s%%)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                   scores["extraction_accuracy_pct"]))
    print("%-34s %s%%" % ("coverage accuracy", scores["coverage_accuracy_pct"]))
    print("%-34s %s%%  precision %s%%" % ("denial recall", scores["coverage_denial_recall_pct"],
                                          scores["coverage_denial_precision_pct"]))
    print("%-34s %d" % ("wrongly-approved claims", flag_scored["false_negative"]))
    print("%-34s %s%%   coded-cause trap %s%% of %d"
          % ("narrative_finding accuracy", scores["narrative_finding_accuracy_pct"],
             scores["coded_cause_trap_accuracy_pct"], scores["coded_cause_trap_of"]))
    print("%-34s %s" % ("per deciding branch",
                        "  ".join("%s %s%% (%d)" % (k, _pct(v["accuracy"]), v["of"])
                                  for k, v in sorted(br.items()))))
    print("%-34s acc %s%%  recall %s%%  precision %s%%"
          % ("needs_review vs gold", scores["recovery_flag_accuracy_pct"],
             scores["recovery_flag_recall_pct"], scores["recovery_flag_precision_pct"]))
    print("%-34s %d reply(s) disagreed with their own values, %d with their own dates; %d of %d "
          "verdict errors were visible without gold"
          % ("consistency diagnostics", cons["replies_disagreeing_with_own_values"],
             cons["replies_disagreeing_with_own_dates"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    if truncated:
        print("%-34s %d reply(s) hit finish_reason=length at max_tokens=%d"
              % ("!! TRUNCATED", truncated, MAX_TOKENS))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
