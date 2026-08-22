"""Run the register monitor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id t000-attestation-watch-stub --stub          # free, proves wiring
    python -m evals.run --run-id b000-attestation-watch-boxtick --baseline   # free, the floor
    python -m evals.run --run-id r001-attestation-watch --yes                # PAID, one call each
    python -m evals.run --run-id c000-attestation-watch-calibration --limit 3 \
        --max-tokens 20000 --yes                                             # measure the ceiling

⚑ EVERY RUN ID IN THIS KIT IS NAMESPACED WITH THE SLUG, INCLUDING THE FREE ONES. Eight kits in this
series independently chose `b000-rules`, in a namespace keyed by run id alone, and one of them
shipped citing another kit's record. A generic run id is a citation waiting to point at the wrong
file.
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
        return {r["register_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """No key, no spend. The register header and the roster regexed straight back out of the
    prompt, so the whole path -- segment, select, prompt, parse, span, the pure-code rule, the
    routing flag, the scorer -- is exercised for free before anything is paid for.

    ⚑ IT RETURNS A ROSTER, NOT ONE FIELD. A stub that answered only register-level fields would
    leave the list alignment, the per-person spans and every one of the four graders untested,
    which is most of this kit."""
    import re
    out = {}
    m = re.search(r"Engagement\n-+\n(.+)", user)
    out["engagement_ref"] = m.group(1).strip() if m else None
    m = re.search(r"Register As At\n-+\n(.+)", user)
    out["as_at_date"] = m.group(1).strip() if m else None
    rows = []
    body = re.search(r"Attesters On Record\n-+\n(.*?)(?:\n\n|\Z)", user, re.S)
    for ln in (body.group(1).splitlines() if body else []):
        m = re.match(r"^(P-\d+)\s+(\S+)\s+", ln.strip())
        if m:
            rows.append({"person_ref": m.group(1), "role": m.group(2)})
    out["attesters"] = rows
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
        i, reg_id = item
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = B.extract(EX.load_doc(reg_id), fields)
            else:
                r = EX.extract(cfg, EX.load_doc(reg_id), fields, complete=complete)
        except Exception as exc:
            return i, reg_id, None, str(exc)[:300], time.time() - t0
        return i, reg_id, r, None, time.time() - t0

    records, lat = {}, []
    tin = tout = 0
    out_max = 0
    reasoning_total = 0
    reasoning_seen = False
    failures = []
    first = None
    t_all = time.time()

    # ⚑ CONCURRENT, LIVE RUNS ONLY. --stub and --baseline make no HTTP call and stay sequential
    # (workers=1), which keeps their output byte-stable. A live run here is one real HTTP call per
    # register and was the long pole in building this kit. `EX.extract` is a pure function with no
    # shared mutable state, and `complete()` in src/adapters already retries transient failures
    # (429/5xx AND transport-level drops) with backoff, so nothing new was added here for that --
    # concurrency just makes hitting that path more likely than a one-at-a-time loop ever did.
    # `pool.map` preserves document order for the prints and the `first` sample below even though
    # completion order is not guaranteed.
    #
    # EVAL_WORKERS is the one knob to raise if a run shows headroom. The provider's documented
    # ceiling is far above this; 12 is chosen to be polite to whichever provider a forker points
    # this at, not to be the most the wire will carry.
    workers = 1 if (a.stub or a.baseline) else int(os.environ.get("EVAL_WORKERS", "12"))
    items = list(enumerate(docs, 1))
    if workers > 1:
        print("  running %d registers with %d concurrent workers" % (len(items), workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, reg_id, r, err, dt in pool.map(process_one, items):
            if err is not None:
                failures.append({"doc": reg_id, "error": err})
                print("  !! %-10s %s" % (reg_id, err))
                continue
            if not r.get("parsed", True):
                why = r.get("finish_reason")
                cut = (why == "length") or (r.get("output_tokens") or 0) >= max_tokens
                failures.append({"doc": reg_id,
                                 "error": "reply did not parse as a register — %s, %d output "
                                          "tokens (cap %d)"
                                          % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                             r.get("output_tokens") or 0, max_tokens),
                                 "output_tokens": r.get("output_tokens"), "max_tokens": max_tokens,
                                 "finish_reason": why, "at_ceiling": cut,
                                 "raw_text": (r.get("raw_text") or "")[:4000]})
                print("  !! %-10s reply did not parse (finish_reason=%s)" % (reg_id, why))
                continue
            lat.append(int(dt * 1000))
            tin += r.get("input_tokens") or 0
            tout += r.get("output_tokens") or 0
            out_max = max(out_max, r.get("output_tokens") or 0)
            td = r.get("token_details") or {}
            if isinstance(td, dict) and td.get("reasoning_tokens") is not None:
                reasoning_seen = True
                reasoning_total += td["reasoning_tokens"] or 0
            records[reg_id] = r
            if first is None:
                first = r
            print("  %3d/%-3d %-10s %2d people  %d ms"
                  % (i, len(docs), reg_id, len(r.get("attesters") or []), lat[-1] if lat else 0))

    golds = load_gold()
    golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, records, golds)
    status_scored = J.score_statuses(fields, records, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    # ⚑ EVERY PUBLISHED FIGURE IS LIFTED INTO THIS ONE BLOCK ON PURPOSE. The worklist matrix, the
    # date arithmetic and the not-determinable reach are computed two levels down under
    # `status_scores`; a board extractor that has to walk three different depths to build one
    # record is an extractor that quietly drops the deepest half. They are copied, not moved --
    # `status_scores` keeps the full matrices and every named row.
    wl = status_scored["worklist"]
    nd = status_scored["not_determinable"]
    orv = status_scored["owner_review"]
    overall = dict(
        scored["overall"],
        status_accuracy_pct=round(100.0 * status_scored["status_accuracy"], 2),
        false_alarm=status_scored["false_alarm"],
        false_alarm_rate_pct=status_scored["false_alarm_rate_pct"],
        misrouted=status_scored["misrouted"],
        missed_breach=status_scored["missed_breach"],
        missed_breach_rate_pct=status_scored["missed_breach_rate_pct"],
        escalated_instead=status_scored["escalated_instead"],
        due_date_accuracy_pct=status_scored["due_date"]["accuracy_pct"],
        worklist_recall_pct=(None if wl["recall"] is None else round(100.0 * wl["recall"], 2)),
        worklist_precision_pct=(None if wl["precision"] is None
                                else round(100.0 * wl["precision"], 2)),
        not_determinable_recall_pct=(None if nd["recall"] is None
                                     else round(100.0 * nd["recall"], 2)),
        not_determinable_precision_pct=(None if nd["precision"] is None
                                        else round(100.0 * nd["precision"], 2)),
        owner_review_recall_pct=(None if orv["recall"] is None else round(100.0 * orv["recall"], 2)),
        owner_review_precision_pct=(None if orv["precision"] is None
                                    else round(100.0 * orv["precision"], 2)),
        self_consistency_disagreements=(
            status_scored["consistency"]["replies_disagreeing_with_own_values"]),
        latency_p50_ms=p(0.50), latency_p95_ms=p(0.95),
        input_tokens_total=tin, output_tokens_total=tout, output_tokens_max=out_max,
    )

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "attester_rows": scored["overall"]["roster_rows_gold"],
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
        "status_scores": status_scored,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        "raw_text": (first.get("raw_text", "") if first else ""),
        "max_tokens": max_tokens,
        # ⚑ RECORDED EVEN THOUGH IT IS NULL. `thinking` is not sent by this harness, and a run that
        # does not record the field is INDISTINGUISHABLE from one that sent it. Null here means
        # "not sent", which on this model family means the provider's own default, which is ON.
        "thinking": None,
        "workers": workers,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    cons = status_scored["consistency"]
    dd = status_scored["due_date"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-38s %s" % ("run", a.run_id))
    print("%-38s %d/%d  (%s)" % ("1. extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-38s %d/%d rows  (%s%%)" % ("   roster coverage", o["roster_rows_matched"],
                                        o["roster_rows_gold"], o["roster_recall_pct"]))
    print("%-38s %d/%d  (%s%%)" % ("2. status verdict, six-way",
                                   status_scored["status_correct"], status_scored["status_rows"],
                                   round(100.0 * status_scored["status_accuracy"], 2)))
    print("%-38s %d/%d  (%s%%)" % ("3. date arithmetic (the model's own)",
                                   dd["correct"], dd["rows"], dd["accuracy_pct"]))
    print("%-38s %s%%  (%d of %d flagged did not belong)"
          % ("4. FALSE-ALARM RATE", status_scored["false_alarm_rate_pct"],
             status_scored["false_alarm"], status_scored["flagged_rows"]))
    # ⚠︎ THE DENOMINATOR IS EVERY PERSON WHO NEEDS ACTION IN GOLD, NOT EVERY ONE THE RUN ANSWERED.
    # tp+fn would silently drop the rows a truncated or dropped register never produced -- which on
    # a monitoring kit is precisely the population a reader is asking about.
    n_must = sum(1 for r in wl["rows"] if r["want"] == "yes")
    print("%-38s %d  (%s%% of the %d that need action; %d of those went unanswered)"
          % ("   missed breaches", status_scored["missed_breach"],
             status_scored["missed_breach_rate_pct"], n_must,
             sum(1 for r in wl["rows"] if r["want"] == "yes" and r["got"] is None)))
    print("%-38s acc %s  recall %s  precision %s"
          % ("   worklist matrix", wl["accuracy"], wl["recall"], wl["precision"]))
    print("%-38s recall %s  precision %s  (%d misrouted onto the worklist)"
          % ("   'cannot determine' reach", nd["recall"], nd["precision"],
             status_scored["misrouted"]))
    print("%-38s acc %s  recall %s  precision %s"
          % ("   owner-review flag vs gold", orv["accuracy"], orv["recall"], orv["precision"]))
    print("%-38s %d reply(s) disagreed with their own values; the rule over those same values "
          "scores %s%%"
          % ("   consistency diagnostic",
             cons["replies_disagreeing_with_own_values"],
             cons["rule_over_own_values_accuracy_pct"]))
    if out_max:
        print("%-38s %d (cap %d)" % ("   largest reply, output tokens", out_max, max_tokens))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
