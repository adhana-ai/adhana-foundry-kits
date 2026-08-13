#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-score r015's recorded outputs under a corrected label rule. Calls nothing. 0 calls, $0.00.

⚑ RE-SCORING RECORDED OUTPUTS IS NOT A SECOND RUN, and the distinction is worth protecting: the
model's output is the evidence, the score is an opinion about it, and an opinion may be corrected.
What it must never become is re-scoring until the number improves — so this is committed code with
its reason written down, and BOTH result files stay in the repo, side by side and diffable.

WHAT WAS WRONG, AND IT WAS THE LABELS RATHER THAN THE MODEL. 14 of 120 requests were recorded as
`stopped_early` because the model answered arithmetic itself instead of calling `calc`:

    q007  "What is 165 percent of 2600?"  -> 4290      no tool called
    q012  "What percentage of customers have placed more than one order?"
          -> called shop_sql, then answered 86.66666666666667% itself

Every one of those 14 answers is CORRECT — the eight plain ones check out exactly, and 86.6667% and
126.1393 / 12.61393 match what the shipped database actually contains. And the system prompt the
model was given says, in as many words: *"Call a tool only when you cannot answer without it.
Calling one you did not need is a failure, not caution."* A model that can multiply does not need
`calc`. The corpus labelled `calc` as REQUIRED; the prompt told the model it was not. Those two
contradict, and scoring against the label while the model obeyed the prompt grades it on an
instruction it was never given.

⚑ SO `calc` IS AN OPTIONAL STEP, AND THE OTHER THREE ARE NOT. `shop_sql`, `doc_search` and `today`
reach facts that are not in the model — the shipped database, the shipped notes, the run's date. No
model can produce those from itself, so skipping one is a real failure. Arithmetic is the only one
of the four whose result the model can legitimately arrive at alone.

⚠︎ THE FIX FOR THE NEXT RUN IS THE PROMPT, NOT THIS FILE. Whichever way the ambiguity is settled,
it should be settled where the model can see it — either "use calc for any arithmetic" or "do
arithmetic yourself; calc is for expressions you cannot do reliably". This file exists because r015
was already run under a prompt that said neither clearly, and re-running to fix a label is spending
money to avoid admitting a mistake.

    python3 -m evals.rescore
"""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import score as S  # noqa: E402

RESULTS = os.path.join(HERE, "results")
OPTIONAL = ("calc",)


def strip_optional(seq):
    return [t for t in seq if t not in OPTIONAL]


def outcome_v2(req, got, replied=True):
    """The corrected rule: optional tools are neither required nor forbidden.

    Stripping happens on BOTH sides, so it cannot mask a wrong tool — truth `doc_search shop_sql`
    against got `calc shop_sql` still strips to `doc_search shop_sql` vs `shop_sql` and is still
    wrong. It only forgives the presence or absence of `calc` itself.
    """
    if not replied:
        return "no_verdict"
    if req.get("decline"):
        return "correct" if not got else "should_have_declined"
    t, g = strip_optional(req["truth"]), strip_optional(got)
    if g == t:
        return "correct"
    if t and len(g) < len(t) and g == t[:len(g)]:
        return "stopped_early"
    if len(g) > len(t) and g[:len(t)] == t:
        return "kept_going"
    if not t and g:
        return "kept_going"
    return "wrong_tool"


def main():
    src = os.path.join(RESULTS, "eval-r015-tool-pick-flash.json")
    d = json.load(open(src, encoding="utf-8"))
    rows = [dict(r) for r in d["rows"]]

    moved = []
    for r in rows:
        was = r["outcome"]
        now = outcome_v2(r, r["got"], replied=r["replied"])
        if now != was:
            moved.append((r["id"], r["trap"], was, now))
        r["outcome"] = now

    s = S.tally(rows)
    s["by_trap"] = S.by_trap(rows)
    s["traps_handled"] = S.traps_handled(rows)
    s["capped"] = sum(1 for r in rows if r["capped"])
    lat = [r["latency_ms"] for r in rows if r["replied"]]
    s["latency_p50_ms"] = statistics.median(lat) if lat else None
    s["latency_p95_ms"] = sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else None
    s["input_tokens_total"] = sum(r["input_tokens"] for r in rows)
    s["output_tokens_total"] = sum(r["output_tokens"] for r in rows)
    s["model_calls_total"] = sum(r["model_calls"] for r in rows)
    s["model_calls_per_request"] = round(s["model_calls_total"] / max(1, s["requests"]), 3)

    old = d["summary"]
    print("RE-SCORED under `calc` optional — the recorded outputs are unchanged, 0 calls.\n")
    print("  %-24s %8s -> %s" % ("sequence_exact", "%.1f%%" % (100 * old["sequence_exact"]),
                                 "%.1f%%" % (100 * s["sequence_exact"])))
    for k in ("correct", "wrong_tool", "stopped_early", "kept_going", "should_have_declined",
              "no_verdict"):
        print("  %-24s %8d -> %d" % (k, old["counts"][k], s["counts"][k]))
    print("\n%d row(s) moved, all of them for the same reason:" % len(moved))
    for rid, trap, was, now in moved:
        print("  %s  %-13s %-14s -> %s" % (rid, trap, was, now))

    print("\n⚠︎ WHAT DID NOT CHANGE, AND IS THE RUN'S REAL PROBLEM: %d of %d returned nothing "
          "usable." % (s["counts"]["no_verdict"], s["requests"]))

    payload = dict(d)
    payload["rows"] = rows
    payload["summary"] = s
    payload["rescored"] = {
        "from": os.path.basename(src),
        "rule": "tools in %s are optional: neither required nor forbidden" % list(OPTIONAL),
        "why": "the system prompt told the model not to call a tool it did not need, and the "
               "corpus labelled `calc` as required. All 14 affected answers were verified correct "
               "against the shipped database.",
        "rows_moved": [{"id": i, "trap": t, "was": w, "now": n} for i, t, w, n in moved],
    }
    out = os.path.join(RESULTS, "eval-r015-tool-pick-flash-rescored.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s   —   0 calls, $0.00. Both files are kept." % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
