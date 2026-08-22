"""Run the worksheet builder over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-obligation-extract --yes        # the real run, one call each
    python -m evals.run --run-id t000-obligation-extract-stub --stub  # no key, proves the wiring
    python -m evals.run --run-id b000-obligation-extract-priceline --baseline    # free, no model
    python -m evals.run --run-id c000-obligation-extract-calibration --limit 6 \
        --max-tokens 16000 --yes                                      # measure the output ceiling
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
        return {r["contract_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """No key, no spend. The contract id and the order-form line codes regexed straight back out of
    the prompt, so the whole path -- segment, select, prompt, parse, span, the pure-code rule, the
    scorer -- is exercised for free before anything is paid for.

    ⚑ IT RETURNS A LIST, WHICH IS THE HALF A FLAT STUB WOULD NOT EXERCISE. This kit's reply is an
    array and every grader downstream joins on `item_code`, so a stub that returned one flat object
    would prove the wiring of the parser and none of the wiring of the join.
    """
    import re
    m = re.search(r"^Contract\n-+\n(\S+)", user, re.M)
    out = {"contract_id": m.group(1).strip() if m else None, "obligations": []}
    # ⚠︎ SCANNED OVER THE WHOLE PROMPT, NOT OVER A CUT-OUT "Order Form" SECTION. The obvious
    # spelling stops the section at the first blank line, and an order form's blank line sits
    # between its header sentence and its rows -- so it captured the header and none of the rows,
    # and the stub reported fifty packs with zero lines each while every other part of the wiring
    # was fine. The two-space-indented row is unique to the order form in this layout.
    for row in re.finditer(r"^ {2}(PO-\d{4})\s{2,}(\S.*?)\s{2,}\S", user, re.M):
        out["obligations"].append({"item_code": row.group(1),
                                   "item_label": row.group(2).strip()})
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

    if a.max_tokens and not a.run_id.startswith("c"):
        raise SystemExit("--max-tokens is for calibration runs only; name the run c<NNN>-... so a "
                         "result measured under a non-published ceiling can never be mistaken for "
                         "a scored one.")
    max_tokens = a.max_tokens or EX.MAX_TOKENS
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
        i, cid = item
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(cid), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(cid), fields, complete=complete)
        except Exception as exc:
            return i, cid, None, str(exc)[:300], time.time() - t0
        return i, cid, r, None, time.time() - t0

    records, flags, lat = {}, {}, []
    tin = tout = 0
    out_max = 0
    reasoning_total = 0
    reasoning_seen = False
    failures = []
    first = None
    t_all = time.time()

    # ⚑ CONCURRENT, LIVE RUNS ONLY. --stub and --baseline make no HTTP call and stay sequential
    # (workers=1), which keeps their output byte-stable; a live run is one real call per pack and
    # was the long pole in building this kit. `EX.extract` is a pure function with no shared mutable
    # state, and `complete()` in src/adapters already retries transient failures (429/5xx AND
    # transport drops) with backoff, so nothing new is needed here for that -- concurrency just
    # makes hitting that path more likely than a one-at-a-time loop ever did. `pool.map` preserves
    # document order for the prints and the `first` sample below even though completion order is
    # not guaranteed.
    #
    # EVAL_WORKERS is the one knob to raise if a run shows headroom. The provider's documented
    # ceiling is far above this; 12 is chosen to be polite to whichever provider a forker points
    # this at, not to be the most the wire will carry.
    workers = 1 if (a.stub or a.baseline) else int(os.environ.get("EVAL_WORKERS", "12"))
    items = list(enumerate(docs, 1))
    if workers > 1:
        print("  running %d packs with %d concurrent workers" % (len(items), workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, cid, r, err, dt in pool.map(process_one, items):
            if err is not None:
                failures.append({"doc": cid, "error": err})
                print("  !! %-10s %s" % (cid, err[:90]))
                continue
            if not r.get("parsed", True):
                why = r.get("finish_reason")
                cut = (why == "length") or (r.get("output_tokens") or 0) >= max_tokens
                failures.append({"doc": cid,
                                 "error": "reply did not parse as JSON — %s, %d output tokens "
                                          "(cap %d)"
                                          % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                             r.get("output_tokens") or 0, max_tokens),
                                 "output_tokens": r.get("output_tokens"), "max_tokens": max_tokens,
                                 "finish_reason": why, "at_ceiling": cut,
                                 "token_details": r.get("token_details"),
                                 "raw_text": (r.get("raw_text") or "")[:4000]})
                print("  !! %-10s reply did not parse (finish_reason=%s)" % (cid, why))
                continue
            lat.append(int(dt * 1000))
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
            out_max = max(out_max, r.get("output_tokens") or 0)
            td = r.get("token_details") or {}
            if isinstance(td, dict) and td.get("reasoning_tokens") is not None:
                reasoning_seen = True
                reasoning_total += td["reasoning_tokens"] or 0
            records[cid] = {"contract": r["contract"], "obligations": r["obligations"]}
            flags[cid] = r.get("needs_drafting_review")
            if first is None:
                first = r
            print("  %3d/%-3d %-10s %d ms  %d line(s)"
                  % (i, len(docs), cid, lat[-1] if lat else 0, len(r["obligations"])))

    golds = load_gold()
    golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, golds)
    ident = J.score_identification(records, golds)
    calls = J.score_calls(records, golds)
    flag_scored = J.score_flag(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    # ⚑ EVERY PUBLISHED FIGURE IS LIFTED INTO THIS ONE BLOCK ON PURPOSE. The determinacy split, the
    # identification directions and the flag's recall are computed two and three levels down; a
    # board extractor that has to walk three different depths to build one record is an extractor
    # that quietly drops the deepest half. They are COPIED, not moved -- the detail blocks below
    # keep the full matrices and every offending row.
    #
    # ⚠︎ `extraction_accuracy` MUST BE THE KEY THAT NAMES THIS RESULT SHAPE. It is what a downstream
    # extractor dispatches on for every extraction kit in this series, and a result that carried
    # only this kit's own vocabulary would route nowhere and record nothing.
    det = calls["determinacy"]
    rf = flag_scored["review_flag"]
    overall = dict(scored["overall"],
                   overconfident=det["overconfident"],
                   overconfident_rate_pct=det["overconfident_rate_pct"],
                   overcautious=det["overcautious"],
                   overcautious_rate_pct=det["overcautious_rate_pct"],
                   not_determined_recall_pct=(None if det["not_determined_recall"] is None
                                              else round(100.0 * det["not_determined_recall"], 2)),
                   identification_precision_pct=(None if ident["precision"] is None
                                                 else round(100.0 * ident["precision"], 2)),
                   identification_recall_pct=(None if ident["recall"] is None
                                              else round(100.0 * ident["recall"], 2)),
                   phantom_obligation=ident["phantom_obligation"],
                   missed_obligation=ident["missed_obligation"],
                   separation_accuracy_pct=(None if calls["separation"]["accuracy"] is None
                                            else round(100.0 * calls["separation"]["accuracy"], 2)),
                   pattern_accuracy_pct=(None if calls["pattern"]["accuracy"] is None
                                         else round(100.0 * calls["pattern"]["accuracy"], 2)),
                   review_flag_recall_pct=(None if rf["recall"] is None
                                           else round(100.0 * rf["recall"], 2)),
                   review_flag_precision_pct=(None if rf["precision"] is None
                                              else round(100.0 * rf["precision"], 2)),
                   self_consistency_disagreements=(
                       flag_scored["consistency"]["rows_disagreeing_with_own_facts"]))

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "lines": ident["gold_lines"],
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
        "identification": ident,
        "calls": calls,
        "flag_scores": flag_scored,
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
    cons = flag_scored["consistency"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-38s %s" % ("run", a.run_id))
    print("%-38s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-38s %d matched, %d missed, %d phantom  (P %s / R %s)"
          % ("obligation identification", ident["matched"], ident["missed_obligation"],
             ident["phantom_obligation"], ident["precision"], ident["recall"]))
    print("%-38s %s" % ("  phantoms by kind",
                        "  ".join("%s=%d" % kv for kv in sorted(ident["phantom_by_kind"].items()))))
    print("%-38s %d/%d  (%s)" % ("separation call", calls["separation"]["correct"],
                                 calls["separation"]["scored"], calls["separation"]["accuracy"]))
    print("%-38s %d/%d  (%s)" % ("delivery pattern", calls["pattern"]["correct"],
                                 calls["pattern"]["scored"], calls["pattern"]["accuracy"]))
    print("%-38s %d of %d  (%s%% of the calls the paperwork does NOT settle)"
          % ("OVER-CONFIDENT CALLS", det["overconfident"], det["not_determined_in_gold"],
             det["overconfident_rate_pct"]))
    print("%-38s %d  (%s%% of the calls it DOES settle)"
          % ("over-cautious calls", det["overcautious"], det["overcautious_rate_pct"]))
    print("%-38s acc %s  recall %s  precision %s"
          % ("needs_drafting_review vs gold", rf["accuracy"], rf["recall"], rf["precision"]))
    print("%-38s %d row(s) disagreed with their own facts; %d of %d call errors were visible "
          "without gold"
          % ("consistency diagnostic", cons["rows_disagreeing_with_own_facts"],
             cons["errors_visible_without_gold"], cons["call_errors"]))
    if out_max:
        print("%-38s %d (cap %d)" % ("largest reply, output tokens", out_max, max_tokens))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
