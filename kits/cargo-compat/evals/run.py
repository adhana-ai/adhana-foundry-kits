"""Run the pre-load checker over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-cargo-compat --yes       # the real run, one call per sheet
    python -m evals.run --run-id t000 --stub                   # no key, no spend, proves the wiring
    python -m evals.run --run-id b000-rules --baseline         # free, tone floor, no model
    python -m evals.run --run-id c000-calibration --limit 6 --max-tokens 16000 --yes
                                                               # measure the output ceiling
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["check_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """No key, no spend. Two fields regexed straight back out of the prompt, so the whole path --
    segment, select, prompt, parse, span, the pure-code rule, the scorer -- is exercised for free
    before anything is paid for."""
    import re
    out = {}
    m = re.search(r"Tank\n-+\n(.+)", user)
    out["tank_id"] = m.group(1).strip() if m else None
    m = re.search(r"Incoming Product\n-+\n(.+)", user)
    out["incoming_product"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--yes", action="store_true")
    # ⚑ ONLY FOR THE CALIBRATION RUN. A scored run must use src.extract.MAX_TOKENS, which is the
    # constant the kit publishes; overriding it silently would let a published figure be measured
    # under a ceiling the page does not name. The value used is recorded in the result file.
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="override the published MAX_TOKENS -- calibration only")
    a = ap.parse_args()

    max_tokens = a.max_tokens or EX.MAX_TOKENS
    if a.max_tokens and not a.run_id.startswith("c"):
        raise SystemExit("--max-tokens is for calibration runs only; name the run c<NNN>-... so a "
                         "result measured under a non-published ceiling can never be mistaken for "
                         "a scored one.")
    EX.MAX_TOKENS = max_tokens

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
    out_max = 0
    reasoning_total = 0
    reasoning_seen = False
    failures = []
    first = None
    t_all = time.time()
    for i, check_id in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(check_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(check_id), fields, complete=complete)
        except Exception as exc:
            failures.append({"doc": check_id, "error": str(exc)[:300]})
            print("  !! %-10s %s" % (check_id, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= max_tokens
            failures.append({"doc": check_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, max_tokens),
                             "output_tokens": r.get("output_tokens"), "max_tokens": max_tokens,
                             "finish_reason": why, "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-10s reply did not parse (finish_reason=%s)" % (check_id, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        out_max = max(out_max, r.get("output_tokens") or 0)
        td = r.get("token_details") or {}
        if isinstance(td, dict) and td.get("reasoning_tokens") is not None:
            reasoning_seen = True
            reasoning_total += td["reasoning_tokens"] or 0
        records[check_id] = r["fields"]
        flags[check_id] = r.get("needs_hold")
        if first is None:
            first = r
        print("  %3d/%-3d %-10s %d ms" % (i, len(docs), check_id, lat[-1] if lat else 0))

    golds = load_gold()
    golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, golds)
    verdict_scored = J.score_verdicts(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    # ⚑ `unsafe_release_rate_pct` RIDES IN `scores` DELIBERATELY. It is this kit's own
    # discriminator -- no other kit's result shape carries "of the tanks the matrix would have
    # stopped, what share did the run clear for loading" -- and it is the number a reader of a
    # safety-adjacent kit should see first.
    #
    # ⚠︎ EVERY PUBLISHED FIGURE IS LIFTED INTO THIS ONE BLOCK ON PURPOSE. The hold-flag recall and
    # the consistency count are computed under `verdict_scores`, two levels down; a board extractor
    # that has to walk two different depths to build one record is an extractor that quietly drops
    # the deeper half. They are copied, not moved -- `verdict_scores` keeps the full matrices.
    hf = verdict_scored["hold_flag"]
    overall = dict(scored["overall"],
                   unsafe_release_rate_pct=verdict_scored["unsafe_release_rate_pct"],
                   unsafe_release_count=verdict_scored["unsafe_release_count"],
                   verdict_accuracy_pct=round(100.0 * verdict_scored["verdict_accuracy"], 2),
                   hold_flag_recall_pct=(None if hf["recall"] is None
                                         else round(100.0 * hf["recall"], 2)),
                   hold_flag_precision_pct=(None if hf["precision"] is None
                                            else round(100.0 * hf["precision"], 2)),
                   self_consistency_disagreements=(
                       verdict_scored["consistency"]["replies_disagreeing_with_own_values"]))

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
        "output_tokens_max": out_max,
        "reasoning_tokens_total": reasoning_total if reasoning_seen else None,
        "scores": overall,
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "verdict_scores": verdict_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": max_tokens,
        # ⚑ RECORDED EVEN THOUGH IT IS NULL. `thinking` is not sent by this harness, and a run that
        # does not record the field is INDISTINGUISHABLE from one that sent it -- which is exactly
        # the comparability guard a board needs to refuse to diff two runs that measured different
        # things. Null here means "not sent", which on this model family means the provider's own
        # default, which is ON.
        "thinking": None,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    cons = verdict_scored["consistency"]
    hf = verdict_scored["hold_flag"]
    bl = verdict_scored["blocked"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-34s %s" % ("run", a.run_id))
    print("%-34s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-34s %d/%d  (%s)" % ("verdict accuracy, four-way",
                                 verdict_scored["verdict_correct"], verdict_scored["verdict_rows"],
                                 verdict_scored["verdict_accuracy"]))
    print("%-34s acc %s  recall %s  precision %s"
          % ("clear-to-load vs not", bl["accuracy"], bl["recall"], bl["precision"]))
    print("%-34s %d  (%s%% of the %d that must be stopped)"
          % ("UNSAFE RELEASES", verdict_scored["unsafe_release_count"],
             verdict_scored["unsafe_release_rate_pct"],
             bl["true_positive"] + bl["false_negative"]))
    print("%-34s %d" % ("over-blocked (a clear tank stopped)", verdict_scored["over_block_count"]))
    print("%-34s acc %s  recall %s  precision %s"
          % ("needs_hold vs gold", hf["accuracy"], hf["recall"], hf["precision"]))
    print("%-34s %d reply(s) disagreed with their own values; %d of %d verdict errors were "
          "visible without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_values"],
             cons["errors_visible_without_gold"], cons["verdict_errors"]))
    if out_max:
        print("%-34s %d (cap %d)" % ("largest reply, output tokens", out_max, max_tokens))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
