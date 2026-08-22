"""Run the filing pre-check over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-ctr-precheck --yes            # the real run, one call a pack
    python -m evals.run --run-id t000-ctr-precheck-stub --stub      # no key, no spend, wiring
    python -m evals.run --run-id b000-ctr-precheck-note --baseline  # free, tone floor, no model
    python -m evals.run --run-id c000-ctr-precheck-calibration --limit 6 --max-tokens 16000 --yes
                                                                    # measure the output ceiling
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["case_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """No key, no spend. Two fields regexed straight back out of the prompt, so the whole path --
    segment, select, prompt, parse, span, the pure-code rule, the scorer -- is exercised for free
    before anything is paid for."""
    import re
    out = {}
    m = re.search(r"Draft Filing\n-+\n(.+)", user)
    out["filing_id"] = m.group(1).strip() if m else None
    m = re.search(r"Patron Record\n-+\n(.+)", user)
    out["patron_record_id"] = m.group(1).strip() if m else None
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

    def process_one(item):
        i, case_id = item
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(case_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(case_id), fields, complete=complete)
        except Exception as exc:
            return i, case_id, None, str(exc)[:300], time.time() - t0
        return i, case_id, r, None, time.time() - t0

    records, flags, lat = {}, {}, []
    tin = tout = 0
    out_max = 0
    reasoning_total = 0
    reasoning_seen = False
    failures = []
    first = None
    t_all = time.time()

    # ⚑ CONCURRENT, LIVE RUNS ONLY. --stub and --baseline make no HTTP call at all and stay
    # sequential (workers=1), which keeps their output byte-stable; a live run is 56 real round
    # trips and was the long pole in this kit's build. `EX.extract` is a pure function with no
    # shared mutable state, and `complete()` in src/adapters already retries transient failures
    # (429/5xx AND transport-level drops) with backoff, so nothing new was added here for that --
    # concurrency just makes hitting that path more likely than a one-at-a-time loop ever did.
    # `pool.map` preserves document order for the prints and the `first` sample below even though
    # completion order is not guaranteed.
    #
    # EVAL_WORKERS is the one knob to raise if a run shows headroom. The provider's documented
    # ceiling is far above this; 12 is chosen to be polite to whichever provider a forker points
    # this at, not to be the most the wire will carry. If you hold the key and know your own
    # ceiling, raise it with the environment variable and change nothing else.
    workers = 1 if (a.stub or a.baseline) else int(os.environ.get("EVAL_WORKERS", "12"))
    items = list(enumerate(docs, 1))
    if workers > 1:
        print("  running %d packs with %d concurrent workers" % (len(items), workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, case_id, r, err, dt in pool.map(process_one, items):
            if err is not None:
                failures.append({"doc": case_id, "error": err})
                print("  !! %-10s %s" % (case_id, err[:90]))
                continue
            if not r.get("parsed", True):
                why = r.get("finish_reason")
                cut = (why == "length") or (r.get("output_tokens") or 0) >= max_tokens
                failures.append({"doc": case_id,
                                 "error": "reply did not parse as JSON — %s, %d output tokens "
                                          "(cap %d)"
                                          % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                             r.get("output_tokens") or 0, max_tokens),
                                 "output_tokens": r.get("output_tokens"), "max_tokens": max_tokens,
                                 "finish_reason": why, "at_ceiling": cut,
                                 "raw_text": (r.get("raw_text") or "")[:4000]})
                print("  !! %-10s reply did not parse (finish_reason=%s)" % (case_id, why))
                continue
            lat.append(int(dt * 1000))
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
            out_max = max(out_max, r.get("output_tokens") or 0)
            td = r.get("token_details") or {}
            if isinstance(td, dict) and td.get("reasoning_tokens") is not None:
                reasoning_seen = True
                reasoning_total += td["reasoning_tokens"] or 0
            records[case_id] = r["fields"]
            flags[case_id] = r.get("needs_recompute")
            if first is None:
                first = r
            print("  %3d/%-3d %-10s %d ms" % (i, len(docs), case_id, lat[-1] if lat else 0))

    golds = load_gold()
    golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, golds)
    defect_scored = J.score_defects(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    # ⚑ `false_alarm_rate_pct` RIDES IN `scores` DELIBERATELY, AND IT IS THE FIRST THING A BOARD
    # SHOULD READ OFF THIS FILE. It is this kit's own discriminator: of the filings with nothing
    # wrong with them, the share this run raised a defect on anyway. A QC queue that cries wolf is
    # worse than no queue, because a person has to clear every row.
    #
    # ⚠︎ EVERY PUBLISHED FIGURE IS LIFTED INTO THIS ONE BLOCK ON PURPOSE. The false-alarm rate, the
    # recompute recall and the consistency count are computed under `defect_scores`, two and three
    # levels down; a board extractor that has to walk three different depths to build one record is
    # an extractor that quietly drops the deepest half. They are copied, not moved -- `defect_scores`
    # keeps the full matrices and the per-code breakdown.
    nr = defect_scored["needs_recompute"]
    fa = defect_scored["false_alarm"]
    ii = defect_scored["insufficient_information"]
    overall = dict(scored["overall"],
                   false_alarm_rate_pct=fa["rate_pct"],
                   false_alarm=fa["clean_packs_flagged"],
                   defect_recall_pct=defect_scored["defect_recall_pct"],
                   defect_precision_pct=defect_scored["defect_precision_pct"],
                   defect_set_exact_pct=defect_scored["defect_set_exact_pct"],
                   insufficient_information_recall_pct=ii["recall_pct"],
                   needs_recompute_recall_pct=(None if nr["recall"] is None
                                               else round(100.0 * nr["recall"], 2)),
                   needs_recompute_precision_pct=(None if nr["precision"] is None
                                                  else round(100.0 * nr["precision"], 2)),
                   self_consistency_disagreements=(
                       defect_scored["consistency"]["replies_disagreeing_with_own_values"]))

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
        "defect_scores": defect_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": max_tokens,
        "workers": workers,
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
    cons = defect_scored["consistency"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-36s %s" % ("run", a.run_id))
    print("%-36s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-36s %d/%d  (%s%%)" % ("arithmetic accuracy", o["arithmetic_correct"],
                                   o["arithmetic_cells"], o["arithmetic_accuracy_pct"]))
    print("%-36s %d/%d  (%s%%)" % ("defect sets exactly right",
                                   defect_scored["defect_set_exact"],
                                   defect_scored["defect_set_rows"],
                                   defect_scored["defect_set_exact_pct"]))
    print("%-36s recall %s%%  precision %s%%"
          % ("defect detection", defect_scored["defect_recall_pct"],
             defect_scored["defect_precision_pct"]))
    print("%-36s %s%%  (%d of %d clean filings flagged)"
          % ("FALSE-ALARM RATE", fa["rate_pct"], fa["clean_packs_flagged"], fa["clean_packs"]))
    print("%-36s %d of %d reached correctly, %d raised wrongly"
          % ("insufficient information", ii["reached_correctly"], ii["seeded"], ii["false_alarm"]))
    print("%-36s acc %s  recall %s  precision %s"
          % ("needs_recompute vs gold", nr["accuracy"], nr["recall"], nr["precision"]))
    print("%-36s %d reply(s) disagreed with their own values; %d of %d defect errors were visible "
          "without gold"
          % ("consistency diagnostic", cons["replies_disagreeing_with_own_values"],
             cons["errors_visible_without_gold"], cons["defect_errors"]))
    for code, d in sorted(defect_scored["per_code"].items()):
        if d["seeded"] or d["false_alarm"]:
            print("    %-26s %d/%d found, %d raised where gold has none"
                  % (code, d["found"], d["seeded"], d["false_alarm"]))
    if out_max:
        print("%-36s %d (cap %d)" % ("largest reply, output tokens", out_max, max_tokens))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
