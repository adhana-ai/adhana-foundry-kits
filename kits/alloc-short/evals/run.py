#!/usr/bin/env python3
"""Run the drafter over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id t000 --stub                     # no key, no spend, proves wiring
    python -m evals.run --run-id r001-alloc-short                # THE REAL RUN, one call/session
    python -m evals.run --run-id r001-x --limit 5                 # a costed toe in the water

⚠︎ ONE CALL PER SESSION, COUNTED BEFORE IT IS MADE -- same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                      # noqa: E402
from src import config, draft as D                     # noqa: E402
from src.prompt import MAX_TOKENS                        # noqa: E402
from evals import scoring as S                             # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

_ID_RE = re.compile(r"^- (EV-\d+)", re.M)


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider: always says 'unknown' with no citations, echoing
    promo/customer protected straight from the prompt text. Not a baseline -- evals/baseline.py
    is; this only exercises prompt -> call -> parse -> score end to end with no key."""
    ids = _ID_RE.findall(user)
    events = [{"event_id": i, "cause": "unknown", "citation_1": "", "citation_2": "",
              "promo_protected": True, "customer_protected": True,
              "note": "stub: exercising the pipeline only"} for i in ids]
    body = {"events": events, "narrative": "Stub narrative exercising the pipeline only."}
    return {"text": json.dumps(body), "input_tokens": len(user) // 4,
           "output_tokens": 25 * max(len(ids), 1), "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--no-thinking", action="store_true",
                    help="disable provider-side reasoning. Off by default.")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    sessions = D.sessions()
    if a.limit:
        sessions = sessions[:a.limit]
    notes = D.notes_by_id()
    gold = D.gold_by_id()

    print("run      : %s" % a.run_id)
    print("sessions : %d   (one call per session, all flagged events batched)" % len(sessions))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    if not a.stub:
        print(BUDGET.plan(len(sessions), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted -- nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(sessions))

    from src.adapters import THINKING_OFF
    thinking = THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None
    prompt_v = a.prompt or __import__("src.prompt", fromlist=["DEFAULT_PROMPT"]).DEFAULT_PROMPT

    records, lat, tin, tout, no_answer = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, session in enumerate(sessions, 1):
        sid = session["session_id"]
        snotes = notes.get(sid, [])
        t0 = time.time()
        r = D.draft(cfg, session, snotes, complete=complete, thinking=thinking, prompt=prompt_v)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["answer"]["events"] and r["events_flagged"] > 0:
            no_answer += 1
        if first is None and r["answer"]["events"]:
            first = r
        records.append({
            "session_id": sid, "packed": r["packed"], "pack_meta": r["pack_meta"],
            "events_flagged": r["events_flagged"], "events_answered": r["events_answered"],
            "answer": r["answer"], "finish_reason": r.get("finish_reason"),
            "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
            "reasoning_tokens": r.get("reasoning_tokens"), "latency_ms": ms,
            "raw_text": r.get("raw_text", "") if r["events_answered"] < r["events_flagged"] else None,
        })
        print("  %2d/%d  %-10s %d/%d events answered"
              % (i, len(sessions), sid, r["events_answered"], r["events_flagged"]))

    scored = S.score(records, gold, notes)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    out = {
        "run_id": a.run_id, "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "sessions": len(records), "no_answer_sessions": no_answer,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "max_tokens": MAX_TOKENS, "thinking": thinking, "prompt_version": prompt_v,
        "prompt_parts": [{"name": pp["name"], "chars": len(pp["text"])}
                        for pp in (first["parts"] if first else [])],
        "prompt_verbatim": (first["prompt"] if first else ""),
        "raw_response_example": (first["raw_text"] if first else ""),
        "scores": scored["overall"],
        "per_session": scored["per_session"],
        "fabricated_examples": scored["fabricated_examples"],
        "records": records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)

    o = scored["overall"]
    print("\n%-32s %s" % ("run", a.run_id))
    print("%-32s %s%%" % ("flag completeness (recall)", o["flag_completeness_recall_pct"]))
    print("%-32s %s%%" % ("flag completeness (precision)", o["flag_completeness_precision_pct"]))
    print("%-32s %s%%" % ("cause-tag agreement (all)", o["cause_tag_agreement_pct"]))
    print("%-32s %s%%" % ("  -- on unknown gold", o["cause_tag_agreement_unknown_pct"]))
    print("%-32s %s%%" % ("  -- on traceable gold", o["cause_tag_agreement_traceable_pct"]))
    print("%-32s %s  (%s%%)" % ("FABRICATED CAUSE", o["fabricated_cause"],
                                o["fabricated_cause_rate_pct"]))
    print("%-32s %s%%" % ("narrative faithfulness", o["narrative_faithfulness_pct"]))
    print("%-32s %s%%  (%d/%d)" % ("conservation (code, always)", o["conservation_pct"],
                                   o["conservation_ok"], o["conservation_events"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
