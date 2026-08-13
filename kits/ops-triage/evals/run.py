#!/usr/bin/env python3
"""The eval harness. One model call per candidate window, scored as missed incidents and false pages.

    python3 -m evals.run --dry-run                    # prints what it would spend, calls nothing
    python3 -m evals.run --run-id r014-ops-triage-flash

⚑ TWO NUMBERS, AND THE REASON IS THAT THE TWO MISTAKES COST DIFFERENT AMOUNTS. `detection` answers
"of the incidents that were there, how many were paged?" — its failures are MISSED INCIDENTS, and
the cost of one is the whole of an outage discovered by a customer. `page_precision` answers "of
the pages sent, how many were real?" — its failures are FALSE PAGES, and the cost of one is a
person's night plus a little more of their trust in the pager. An accuracy figure is one number
that moves when either does, and on a corpus that is 8% page it would rate "hold everything" at 92%
while missing every incident in the set. So this file publishes both, and no combined figure.

⚑ THE SCORER IS SHARED WITH THE FREE FLOOR. `src/decide.py` is what `evals/baseline.py` calls too,
so the rule engine and the model travel the identical path: same windows, same labels, same five
outcomes. A baseline with its own scorer is a second opinion, not a floor.

⚑ READ `evals/baseline.py` FIRST. It costs nothing, needs no key, and it is the number this run
only means something beside. On this kit the floor is not a constant — it is a working pager — so
"better than the floor" is a real bar rather than a formality.

⚠︎ WHAT THIS RUN DOES NOT MEASURE. It judges the windows `src/window.py::candidates` passed, not
all 240 — so every score is conditional on the gate having shown the window to the model at all.
Gate recall is measured and published beside the scores, because a pre-filter that drops incidents
sets a ceiling no model quality can lift. On this corpus it is 100%, and the first version of the
gate scored 85% by being blind to silence that was already under way.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_windows                                   # noqa: E402
from src import config, decide, prompt as pr, rules, window as W              # noqa: E402

RESULTS = os.path.join(HERE, "results")


def history_for(windows, i, svc, back=W.HISTORY):
    """Line counts for one service over the previous `back` windows — the evidence behind a NOTE."""
    return [sum(1 for e in windows[i - k]["events"] if e["service"] == svc)
            for k in range(back, 0, -1)]


def prompt_for(windows, i):
    """Everything the model is shown for window `i`, assembled by code."""
    win = windows[i]
    collapsed = W.collapse(win)
    silent = W.gone_silent(windows, i)
    hist = {svc: history_for(windows, i, svc) for svc in silent}
    return pr.render(win, collapsed, silent, hist), collapsed, silent


def score_window(lab, verdict, replied=True):
    """One window's outcome. Identical for the model and for the floor — that is the point."""
    return {"id": lab["id"], "label": lab["label"], "trap": lab["trap"], "verdict": verdict,
            "replied": replied, "outcome": decide.outcome(lab["label"], verdict, replied),
            "paged": verdict == decide.PAGE and replied}


def summarise(rows):
    lat = sorted(r.get("model_latency_ms", 0) for r in rows if r.get("model_latency_ms"))
    t = decide.tally(rows)
    pct = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0
    t.update({"model_latency_p50_ms": pct(lat, 0.50), "model_latency_p95_ms": pct(lat, 0.95),
              "input_tokens_total": sum(r.get("input_tokens", 0) or 0 for r in rows),
              "output_tokens_total": sum(r.get("output_tokens", 0) or 0 for r in rows),
              "by_trap": decide.by_trap(rows),
              "traps_handled": decide.trap_verdict(rows)})
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap the run while iterating")
    ap.add_argument("--run-id", default=None, help="stamped into the result file")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what this would spend and call nothing")
    a = ap.parse_args()

    windows, labels = load_windows()
    cand = W.candidates(windows)
    idx = {w["id"]: i for i, w in enumerate(windows)}
    rows = [lab for lab in labels if lab["id"] in cand]
    if a.limit:
        rows = rows[:a.limit]
    cfg = config.load()

    sample, _, _ = prompt_for(windows, idx[rows[0]["id"]])
    sizes = [len(prompt_for(windows, idx[r["id"]])[0]) for r in rows]
    st = W.stats(windows, labels)
    print("ops-triage eval — %d window(s) cut, %d judged after the gate" % (len(labels), len(rows)))
    print("  gate:   %d of %d windows never reach a model (%.0f%% of the stream), "
          "gate recall %.1f%%"
          % (st["windows"] - st["candidates"], st["windows"], 100 * st["reduction"],
             100 * st["gate_recall"]))
    print("  labels: %d page / %d hold among the judged windows"
          % (sum(1 for r in rows if r["label"] == "page"),
             sum(1 for r in rows if r["label"] == "hold")))
    print("  prompt: %d–%d chars per window (median %d), %d verdicts (%s)"
          % (min(sizes), max(sizes), sorted(sizes)[len(sizes) // 2],
             len(pr.VERDICTS), ", ".join(pr.VERDICTS)))
    print("  calls it will make: %d (one per window, no retries counted)" % len(rows))
    if st["lost_to_gate"]:
        print("  ⚠︎ NOT judged: %d incident(s) the gate dropped — %s"
              % (len(st["lost_to_gate"]), ", ".join(st["lost_to_gate"][:8])))
    if a.dry_run:
        print("\n--dry-run: nothing was called and nothing was spent.")
        print("Read evals/baseline.py first — the free floor costs nothing, and it is a working")
        print("pager rather than a constant, so this number only means something beside it.")
        return 0
    if not config.has_key(cfg):
        print("\nno API_KEY configured. The FREE floor still runs: python3 -m evals.baseline")
        return 1
    print("  model: %s / %s\n" % (cfg["provider"], cfg["model"]))

    from src.adapters import complete
    results = []
    for lab in rows:
        i = idx[lab["id"]]
        user, collapsed, silent = prompt_for(windows, i)
        t0 = time.time()
        got = complete(cfg, pr.SYSTEM, user, max_tokens=pr.MAX_TOKENS)
        ms = round((time.time() - t0) * 1000, 2)
        verdict = pr.parse(got["text"])
        rec = score_window(lab, verdict, replied=verdict is not None)
        rec.update({"model_latency_ms": ms, "raw_response": got["text"],
                    # Kept so an empty reply can be diagnosed from the RESULTS FILE rather than
                    # from a second run — "length" is a truncation, "stop" is a model that said
                    # nothing, and reasoning billed inside the output budget is how a healthy
                    # token count produces an empty string. UC011 paid 78 calls to learn this.
                    "finish_reason": got.get("finish_reason"),
                    "reasoning_chars": got.get("reasoning_chars"),
                    "input_tokens": got["input_tokens"], "output_tokens": got["output_tokens"],
                    "prompt_chars": len(user), "collapsed_lines": len(collapsed),
                    "raw_lines": len(windows[i]["events"]), "silent_services": silent,
                    "loud": W.counts(windows[i])["loud"]})
        results.append(rec)
        print("  %-6s %-6s %-16s %3d loud  %s"
              % (lab["id"], verdict or "(none)", rec["outcome"], rec["loud"], lab["trap"]))

    s = summarise(results)
    # THE DENOMINATOR PRINTS FIRST, above the rates rather than beside them, because a terminal is
    # where a broken run is first read as a success.
    print("\nanswered %d of %d window(s) — the two numbers below are computed over those %d ONLY"
          % (s["answered"], s["windows"], s["answered"]))
    print("MISSED INCIDENTS %d   false pages %d   detection %s   page precision %s   no verdict %d"
          % (s["missed_incidents"], s["false_pages"],
             "%.1f%%" % (100 * s["detection"]) if s["detection"] is not None else "n/a",
             "%.1f%%" % (100 * s["page_precision"]) if s["page_precision"] is not None else "n/a",
             s["no_verdict"]))
    if s["answered"] <= s["windows"] - s["answered"]:
        print("⚠︎  MORE WINDOWS FAILED THAN ANSWERED. Those numbers describe the exception, not the")
        print("   run, and the ingest will refuse this record. Check `finish_reason` before")
        print("   changing anything: a truncated reply and a silent model need different fixes.")
        why = {}
        for r in results:
            if r["outcome"] == "no_verdict":
                why[r.get("finish_reason")] = why.get(r.get("finish_reason"), 0) + 1
        print("   finish_reason on the %d with no verdict: %s"
              % (s["no_verdict"], ", ".join("%s %d" % (k, v) for k, v in sorted(why.items(),
                                                                                key=str))))
    print("tokens in/out %d/%d   p50 %.0f ms   p95 %.0f ms"
          % (s["input_tokens_total"], s["output_tokens_total"],
             s["model_latency_p50_ms"], s["model_latency_p95_ms"]))
    print("\nby trap — which KIND of hard case it failed:")
    for trap, t in sorted(s["by_trap"].items(), key=lambda x: -x[1]["wrong"]):
        print("  %-14s %d/%d wrong   %s"
              % (trap, t["wrong"], t["windows"],
                 ", ".join("%s %d" % kv for kv in sorted(t["outcomes"].items()))))
    handled = [k for k, v in s["traps_handled"].items() if v]
    print("\ntrap kinds handled completely: %d of %d — %s"
          % (len(handled), len(s["traps_handled"]), ", ".join(sorted(handled)) or "none"))

    os.makedirs(RESULTS, exist_ok=True)
    run_id = a.run_id or "unstamped"
    payload = {
        "kind": "triage",
        "run_id": run_id, "model": cfg["model"], "provider": cfg["provider"],
        "window_seconds": W.WINDOW_S,
        "dataset": {"windows": len(rows), "labelled": len(labels), "file": "data/labelled.jsonl",
                    "page": sum(1 for r in rows if r["label"] == "page"),
                    "hold": sum(1 for r in rows if r["label"] == "hold")},
        "corpus": {"events": sum(len(w["events"]) for w in windows), "windows": len(windows),
                   "file": "data/events.csv",
                   "note": "generated by tools/build_corpus.py from a fixed seed, MIT"},
        "gate": st,
        "rules_floor": {"threshold": rules.DEFAULT_THRESHOLD,
                        "note": "measured in results/baseline.json — run evals/baseline.py"},
        "summary": s, "rows": results,
        "could_not_verify": [
            "Only the %d windows the gate passed were judged, not all %d. Every score is "
            "conditional on the gate having shown the window to the model — gate recall is "
            "published beside it for exactly that reason."
            % (len(rows), len(labels)),
            "The five-minute bucket is a product decision, not a measurement. A wider window puts "
            "the retry storm's recovery line inside it and the correct answer flips; a narrower "
            "one splits the cascade into windows that each look like a separate outage. Nothing "
            "here measures how much of the score is the bucket size.",
            "The corpus is invented, so it contains the failure modes we thought to plant and no "
            "others. A real event stream carries kinds of noise this set does not, and its "
            "incidents are not politely one per window.",
            "The absence of lines is computed by code and handed to the model as a stated fact. "
            "This measures whether the model judges silence correctly once told about it — NOT "
            "whether a model can notice something missing from its input, which is a different "
            "question this kit does not ask.",
        ]}
    out = os.path.join(RESULTS, "eval-%s.json" % re.sub(r"[^a-z0-9._-]+", "-", run_id.lower()))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
