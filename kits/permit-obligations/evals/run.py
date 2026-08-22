"""Run the register reader over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-permit-obligations --yes        # the real run, one call each
    python -m evals.run --run-id t000-permit-obligations-stub --stub  # no key, no spend
    python -m evals.run --run-id b000-permit-obligations-flag --baseline   # free, the flag floor
    python -m evals.run --run-id c000-permit-obligations-calibration --limit 6 --max-tokens 16000 --yes
"""
import argparse
import json
import os
import re
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


def stub_complete(cfg, system, user, max_tokens=1024, thinking=None):
    """No key, no spend. Three values regexed straight back out of the prompt plus one entry per
    condition heading, so the whole path -- segment, select, prompt, parse, the per-row span search,
    the pure-code rulebook, the worklist, the escalation flag and the scorer -- is exercised for
    free before anything is paid for.

    ⚠︎ IT RETURNS THE ROWS AND ALMOST NONE OF THEIR VALUES ON PURPOSE. A stub that filled every
    field would prove the harness runs and hide the two paths that actually break: a row whose
    fields are missing, and a status the rulebook has to refuse to compute. This one drives both.
    """
    out = {}
    m = re.search(r"Site\n-+\n(.+)", user)
    if m:
        got = re.search(r"\((SITE-[A-Z]{2}-\d{4})\)", m.group(1))
        out["site_id"] = got.group(1) if got else None
    m = re.search(r"Permit\n-+\n(MP-\d{4}-[A-Z])", user)
    out["permit_no"] = m.group(1) if m else None
    m = re.search(r"Register Date\n-+\n(\d{4}-\d{2}-\d{2})", user)
    out["register_date"] = m.group(1) if m else None
    out["obligations"] = [{"condition_id": cid}
                          for cid in re.findall(r"^Condition (C-\d+\.\d+)$", user, re.M)]
    body = json.dumps(out)
    return {"text": body, "input_tokens": len(user) // 4, "output_tokens": len(body) // 4,
            "raw": {"stub": True}}


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
    ob_fields = EX.load_obligation_fields()
    docs = EX.documents()
    if a.limit:
        # ⚠︎ SPREAD, NOT THE FIRST N. A calibration must see the largest registers as well as the
        # smallest, because the reply length here is one entry per condition block and a register
        # carries 4 to 7 of them. Taking the first six files would measure the ceiling against
        # whatever the seed happened to put at the front of the directory listing.
        step = max(1, len(docs) // a.limit)
        docs = docs[::step][:a.limit]

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
                r = B.extract(EX.load_doc(reg_id), fields, ob_fields)
            else:
                r = EX.extract(cfg, EX.load_doc(reg_id), fields, ob_fields, complete=complete)
        except Exception as exc:
            return i, reg_id, None, str(exc)[:300], time.time() - t0
        return i, reg_id, r, None, time.time() - t0

    records, flags, lat = {}, {}, []
    tin = tout = 0
    out_max = 0
    reasoning_total = 0
    reasoning_seen = False
    failures = []
    first = None
    t_all = time.time()

    # ⚑ CONCURRENT, LIVE RUNS ONLY. --stub and --baseline are already free and instant (no HTTP
    # call) and stay sequential (workers=1); a live run is one real HTTP call per register and was
    # the long pole in a kit build. `EX.extract` is a pure function with no shared mutable state,
    # and `complete()` in src/adapters already retries transient failures (429/5xx AND transport
    # drops) with backoff, so nothing new was added here for that -- concurrency just makes hitting
    # that path more likely than a one-at-a-time loop ever did. `pool.map` preserves document order
    # for the prints and the `first` sample below even though completion order is not guaranteed.
    #
    # EVAL_WORKERS is the one knob to raise if a run shows headroom. The provider's documented
    # ceiling is far above this; 12 is chosen to be polite, not to be the limit.
    workers = 1 if (a.stub or a.baseline) else int(os.environ.get("EVAL_WORKERS", "12"))
    items = list(enumerate(docs, 1))
    if workers > 1:
        print("  running %d registers with %d concurrent workers" % (len(items), workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, reg_id, r, err, dt in pool.map(process_one, items):
            if err is not None:
                failures.append({"doc": reg_id, "error": err})
                print("  !! %-10s %s" % (reg_id, err[:90]))
                continue
            if not r.get("parsed", True):
                why = r.get("finish_reason")
                cut = (why == "length") or (r.get("output_tokens") or 0) >= max_tokens
                failures.append({"doc": reg_id,
                                 "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
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
            records[reg_id] = {"fields": r["fields"], "obligations": r["obligations"]}
            flags[reg_id] = r.get("escalate")
            if first is None:
                first = r
            print("  %3d/%-3d %-10s %2d row(s)  %d ms"
                  % (i, len(docs), reg_id, len(r["obligations"]), lat[-1]))

    golds = load_gold()
    golds = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, ob_fields, records, golds)
    status_scored = J.score_statuses(records, flags, golds)

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    # ⚑ `false_alarm_rate_pct` RIDES IN `scores` DELIBERATELY, AND IT IS THE FIRST THING PRINTED.
    # It is this kit's own discriminator -- of the obligations this run put in front of a person,
    # what share did not need to be there -- and on a monitor it is the number a reader should see
    # before any accuracy figure.
    #
    # ⚠︎ EVERY PUBLISHED FIGURE IS LIFTED INTO THIS ONE BLOCK ON PURPOSE. The date arithmetic, the
    # cannot-determine rates and the escalation flag are computed under `status_scores`, two levels
    # down; a board extractor that has to walk three different depths to build one record is an
    # extractor that quietly drops the deepest half. They are copied, not moved -- `status_scores`
    # keeps the full matrices and every failing row.
    wl = status_scored["worklist"]
    nd = status_scored["not_determinable"]
    esc = status_scored["escalate"]
    pct = lambda v: None if v is None else round(100.0 * v, 2)
    overall = dict(scored["overall"],
                   false_alarm_rate_pct=status_scored["false_alarm_rate_pct"],
                   false_alarm_count=status_scored["false_alarm_count"],
                   missed_action_count=status_scored["missed_action_count"],
                   missed_action_rate_pct=status_scored["missed_action_rate_pct"],
                   worklist_raised=status_scored["worklist_raised"],
                   worklist_precision_pct=pct(wl["precision"]),
                   worklist_recall_pct=pct(wl["recall"]),
                   status_accuracy_pct=round(100.0 * status_scored["status_accuracy"], 2),
                   due_date_accuracy_pct=status_scored["due_dates"]["accuracy_pct"],
                   due_dates_scored=status_scored["due_dates"]["scored"],
                   not_determinable_recall_pct=pct(nd["recall"]),
                   not_determinable_precision_pct=pct(nd["precision"]),
                   escalate_recall_pct=pct(esc["recall"]),
                   escalate_precision_pct=pct(esc["precision"]),
                   register_flag_disagreements=(
                       status_scored["register_flag_diagnostic"]["disagreements"]))

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "obligations": sum(len(g.get("obligations") or []) for g in golds.values()),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "output_tokens_max": out_max,
        "reasoning_tokens_total": reasoning_total if reasoning_seen else None,
        "scores": overall,
        "by_field": scored["by_field"],
        "rows": scored["rows"],
        "cells": scored["cells"],
        "status_scores": status_scored,
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
    dd = status_scored["due_dates"]
    diag = status_scored["register_flag_diagnostic"]
    ext_hit = sum(1 for c in scored["cells"] if c["verdict"] == "hit")
    print("\n%-38s %s" % ("run", a.run_id))
    print("%-38s %s%%  (%d of %d raised did not need to be)"
          % ("FALSE-ALARM RATE", status_scored["false_alarm_rate_pct"],
             status_scored["false_alarm_count"], status_scored["worklist_raised"]))
    print("%-38s %d  (%s%% of the %d that need action)"
          % ("missed actions", status_scored["missed_action_count"],
             status_scored["missed_action_rate_pct"],
             wl["true_positive"] + wl["false_negative"]))
    print("%-38s %d/%d  (%s)" % ("extraction accuracy", ext_hit, o["extraction_cells"],
                                 o["extraction_accuracy"]))
    print("%-38s %d/%d  (%s)" % ("status accuracy, five-way",
                                 status_scored["status_correct"], status_scored["status_rows"],
                                 status_scored["status_accuracy"]))
    print("%-38s %d/%d  (%s%%)" % ("derived due dates exact", dd["correct"], dd["scored"],
                                   dd["accuracy_pct"]))
    print("%-38s recall %s  precision %s" % ("cannot-determine", nd["recall"], nd["precision"]))
    print("%-38s acc %s  recall %s  precision %s"
          % ("escalation flag vs gold", esc["accuracy"], esc["recall"], esc["precision"]))
    print("%-38s %d of %d obligation rows found, %d invented"
          % ("rows", scored["rows"]["found"], scored["rows"]["expected"],
             scored["rows"]["spurious"]))
    print("%-38s %d of %d rows -- the site's own flag disagrees with the computed status"
          % ("register-flag diagnostic (no gold)", diag["disagreements"], diag["rows_compared"]))
    if out_max:
        print("%-38s %d (cap %d)" % ("largest reply, output tokens", out_max, max_tokens))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
