#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score the router and the model TOGETHER, from outputs already recorded. 0 calls, $0.00.

    python3 -m evals.escalate

⚑ WHY THIS FILE EXISTS. The kit publishes the escalation design as UNMEASURED: the free keyword
router answers 56 of 120 correctly for nothing, so "let the router keep the easy ones and pay the
model only for the rest" is the build anybody would reach for next. Saying it is obvious is not the
same as knowing what it scores, and the model's tool sequence for all 120 requests is already on
disk — so the question is answerable for $0.00.

⚠︎ THIS IS RE-SCORING RECORDED OUTPUTS, NOT A SECOND RUN. The model's output is the evidence; an
escalation policy is an opinion about when to ask for it. What this must never become is trying
policies until the number improves — so **every policy below is declared before any is scored, each
one is a build somebody would actually ship, and all of them are printed whether they win or lose.**

⚑ THE CONSTRAINT THAT MAKES IT HONEST: A POLICY MAY LOOK AT THE REQUEST AND NOTHING ELSE. Every
`escalate` function below takes the request TEXT and returns a decision. It cannot see the truth,
the trap kind or the outcome, because a router that knew which ones it was about to get wrong would
not need the model at all. UC012's equivalent file recorded getting this exactly wrong in its first
version — it escalated on the rules' VERDICT rather than on their COMPETENCE — and the tell was two
different policies scoring identically.

⚑ AND A CONTROL SEPARATES THE TWO THINGS THAT CHANGE AT ONCE. Every escalation policy also gains a
fallback: 26 of 120 requests came back with nothing usable, and a shipped system with a router
underneath it never returns nothing — it falls back. That fallback raises the answered denominator
from 94 to 120 all by itself, with no escalation involved. So `model alone, router catches the
silences` is scored as its own row. Without it, the fallback's contribution would be credited to
escalation, and the headline would be a measurement of the wrong thing.

⚠︎ BOTH SIDES ARE SCORED UNDER THE SAME RULE. The published 89.4% treats `calc` as optional
(`evals/rescore.py`). Scoring the router strictly while the model is scored leniently would inflate
every escalation row by the difference. `outcome_v2` is imported rather than reimplemented.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.rescore import outcome_v2                                          # noqa: E402
from src import router, score as S                                            # noqa: E402

RESULTS = os.path.join(HERE, "results")
REQUESTS = os.path.join(HERE, "data", "requests.jsonl")
RUN_ID = "r015-tool-pick-flash"


def rules_fired(text):
    """How many of the router's rules match — the only thing a keyword router knows about its own
    competence before it runs. Not a verdict: a count of what it has to grip."""
    return sum(1 for _, pat in router.RULES if re.search(pat, text, re.I))


# The policies, declared up front. Each `escalate` sees the request text and NOTHING else.
#
# ⚑ THE THREE ESCALATION RULES ARE THE ONLY THREE A KEYWORD ROUTER CAN EXPRESS. It knows how many
# of its patterns matched, and that is the whole of its self-knowledge. Zero means it has nothing to
# grip and would call no tool at all. Two or more means it must guess an ORDER its rules say nothing
# about — `src/router.py` says so in as many words, and calls that the structural thing a keyword
# router cannot do. Exactly one is the only case it was designed for.
POLICIES = [
    ("router alone", None, False,
     "the free floor at its best setting — 0 model calls, the parent to beat on cost"),
    ("model alone (as published)", "all", False,
     "r015 exactly as the kit publishes it, silences left as no_verdict"),
    ("model alone, router catches the silences", "all", True,
     "THE CONTROL: same 210 calls, but the router answers the 26 that came back empty. Isolates "
     "the fallback from the escalation"),
    ("escalate when NO rule fires", lambda t: rules_fired(t) == 0, True,
     "the router has nothing to grip and would call no tool; ask the model instead"),
    ("escalate when RULES DISAGREE (2+ fire)", lambda t: rules_fired(t) >= 2, True,
     "two patterns match and the router must guess an order its rules cannot know"),
    ("escalate unless EXACTLY ONE rule fires", lambda t: rules_fired(t) != 1, True,
     "the confident router: keep only the case a keyword router was designed for, buy the rest"),
]


def load_requests():
    with open(REQUESTS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    run = json.load(open(os.path.join(RESULTS, "eval-%s-rescored.json" % RUN_ID), encoding="utf-8"))
    reqs = load_requests()
    rows = run["rows"]

    # ⚑ A CENSUS BEFORE ANY SCORING. A policy scored over a row set that has drifted from the corpus
    # is a number about nothing, and this file's whole claim is that it re-scores THE run.
    by_id = {r["id"]: r for r in rows}
    corpus_ids = [q["id"] for q in reqs]
    assert len(rows) == len(reqs) == 120, "expected 120 rows and 120 requests, got %d and %d" % (
        len(rows), len(reqs))
    assert set(by_id) == set(corpus_ids), "run rows and corpus disagree on which requests exist"

    cap = run["floor"]["best_cap"]
    total_calls = run["summary"]["model_calls_total"]
    total_tokens = run["summary"]["input_tokens_total"] + run["summary"]["output_tokens_total"]
    paid_usd = 0.065          # results are call-counted, not priced — see the note in the output

    print("ESCALATION — %d requests, %d model calls already spent, 0 new calls.\n"
          % (len(rows), total_calls))
    print("The router runs at cap %d (its best setting). A policy sees the request text only.\n" % cap)

    out = {"kind": "escalation", "calls": 0, "cost_usd": 0.0, "run_id": run["run_id"],
           "floor_cap": cap,
           "note": "Re-scored from recorded outputs through src/score.py and evals/rescore.py's "
                   "corrected label rule. No model was called.",
           "policies": {}}

    print("  %-42s %-8s %-9s %-7s %-7s %-6s %s"
          % ("", "exact", "answered", "calls", "% calls", "danger", "traps clean"))

    for name, esc, fallback, why in POLICIES:
        scored, calls, tok = [], 0, 0
        for q in reqs:
            r = by_id[q["id"]]
            free = router.route(q["text"], cap)
            if esc is None:
                got, replied = free, True
            else:
                take = True if esc == "all" else bool(esc(q["text"]))
                if not take:
                    got, replied = free, True
                else:
                    calls += r["model_calls"]
                    tok += r["input_tokens"] + r["output_tokens"]
                    if r["replied"]:
                        got, replied = r["got"], True
                    elif fallback:
                        got, replied = free, True       # the router catches it; nothing is returned empty
                    else:
                        got, replied = [], False
            scored.append({"id": q["id"], "trap": q["trap"], "truth": list(q["truth"]),
                           "decline": q.get("decline", False), "got": list(got),
                           "outcome": outcome_v2(q, got, replied=replied)})

        t = S.tally(scored)
        t["by_trap"] = S.by_trap(scored)
        t["traps_handled"] = S.traps_handled(scored)
        t["model_calls"] = calls
        t["calls_share"] = round(calls / total_calls, 4) if total_calls else 0.0
        t["tokens"] = tok
        # ⚠︎ PRO-RATA, AND SAYING SO. This kit's budget.py counts CALLS and deliberately not dollars,
        # and no per-token rate for the run's own model is recorded in this repo — only the total
        # actually paid. Splitting that total by token share is the most this evidence supports.
        t["usd_pro_rata"] = round(paid_usd * (tok / total_tokens), 5) if total_tokens else 0.0
        t["escalated_requests"] = sum(1 for q in reqs
                                      if esc is not None and (esc == "all" or bool(esc(q["text"]))))
        t["why"] = why
        t["fallback_to_router_on_silence"] = fallback
        handled = sorted(k for k, v in t["traps_handled"].items() if v)
        t["traps_clean"] = handled
        out["policies"][name] = t

        print("  %-42s %-8s %-9s %-7d %-7s %-6d %s"
              % (name,
                 "%.1f%%" % (100 * t["sequence_exact"]) if t["sequence_exact"] is not None else "n/a",
                 "%d/%d" % (t["answered"], t["requests"]),
                 calls, "%.0f%%" % (100 * t["calls_share"]),
                 t["counts"]["should_have_declined"],
                 ", ".join(handled) or "none"))
        print("  %-42s %s" % ("", why))

    # ⚑ THE HARNESS RECONCILES AGAINST THE PUBLISHED RECORD, OR IT IS MEASURING SOMETHING ELSE.
    # "model alone (as published)" re-derives the run from its own rows: if it does not land on the
    # exact numbers the kit prints, every other row in this table is built on a scorer that
    # disagrees with the one that produced them, and the table is worthless. This is the only check
    # here that can fail loudly, so it is an assert and not a printed warning.
    pub, got = run["summary"], out["policies"]["model alone (as published)"]
    for key in ("sequence_exact", "answered", "requests"):
        assert got[key] == pub[key], "re-derived %s=%r but the record publishes %r" % (
            key, got[key], pub[key])
    assert got["model_calls"] == pub["model_calls_total"], \
        "re-derived %d model calls, the record publishes %d" % (got["model_calls"],
                                                                pub["model_calls_total"])
    out["reconciles_with_published_record"] = True

    # ⚠︎ A CORRECTION THIS FILE FOUND ON ITS WAY PAST, AND IT IS NOT ABOUT ESCALATION. The kit
    # publishes "89.4% against a free keyword router's 46.7%". Those two numbers are measured with
    # DIFFERENT RULERS: the model's is scored with `calc` optional (evals/rescore.py) and the
    # floor's with `calc` required. Under the model's own rule the floor is 50.0% — 16 two-step
    # rows move, 4 of them to correct. The gap survives comfortably and the kit's conclusion is
    # unchanged, but a comparison is only a comparison if both sides are measured the same way.
    strict = out["policies"]["router alone"]["sequence_exact"]
    out["floor_under_the_models_rule"] = {
        "published_strict": run["floor"]["sequence_exact"],
        "same_rule_as_model": strict,
        "why": "the published floor scores `calc` as required; the published model score treats it "
               "as optional. Both numbers are correct under their own rule and they were being "
               "printed side by side as if they shared one.",
    }
    print("\n⚠︎ THE TWO PUBLISHED NUMBERS DO NOT SHARE A RULER.")
    print("  floor as published (calc REQUIRED)     %.1f%%" % (100 * run["floor"]["sequence_exact"]))
    print("  floor under the model's own rule       %.1f%%   <- the honest side-by-side" % (100 * strict))
    print("  model (calc optional, as published)    %.1f%%"
          % (100 * out["policies"]["model alone (as published)"]["sequence_exact"]))

    # ⚑ THE READING, STATED RATHER THAN LEFT TO THE TABLE. Escalation is only worth building if it
    # buys most of the model's accuracy for a fraction of its calls. "Most" and "a fraction" are
    # thresholds, so they are written down here rather than chosen after seeing the numbers: a
    # policy qualifies if it scores at least as well as the model-with-fallback control AND spends
    # less than it. Anything else is a worse answer at a lower price, which is a trade-off to
    # report, not an architecture to recommend.
    ctl = out["policies"]["model alone, router catches the silences"]
    floor = out["policies"]["router alone"]
    winners = []
    for name, t in out["policies"].items():
        if name in ("router alone", "model alone (as published)",
                    "model alone, router catches the silences"):
            continue
        if t["sequence_exact"] >= ctl["sequence_exact"] and t["model_calls"] < ctl["model_calls"]:
            winners.append((name, t))
    out["beats_control_for_fewer_calls"] = winners[0][0] if winners else None

    print("\nDOES ANY POLICY MATCH THE MODEL FOR FEWER CALLS?")
    if winners:
        n, t = sorted(winners, key=lambda x: x[1]["model_calls"])[0]
        print("  ✓ %s — %.1f%% on %d calls (%.0f%% of the run), against the model's %.1f%% on %d."
              % (n, 100 * t["sequence_exact"], t["model_calls"], 100 * t["calls_share"],
                 100 * ctl["sequence_exact"], ctl["model_calls"]))
    else:
        print("  ✗ NO. Every escalation policy that saves calls also loses accuracy. The router's")
        print("    self-knowledge — how many of its patterns matched — does not identify the")
        print("    requests the model is needed for, and on this corpus that is the finding:")
        print("    a keyword router cannot tell which questions are beyond a keyword router.")

    # ⚑ AND THE CHEAPEST ROW THAT IS STILL BETTER THAN FREE, because "no winner" does not mean
    # "nothing to build" — it means the trade-off has to be shown rather than recommended.
    tradeoffs = [(n, t) for n, t in out["policies"].items()
                 if t["model_calls"] and t["sequence_exact"] > floor["sequence_exact"]]
    if tradeoffs:
        n, t = sorted(tradeoffs, key=lambda x: x[1]["model_calls"])[0]
        print("\n  Cheapest row still ahead of the free floor: %s — %.1f%% for %d calls "
              "(the floor is %.1f%% for 0)."
              % (n, 100 * t["sequence_exact"], t["model_calls"], 100 * floor["sequence_exact"]))

    # ⚑ WHY IT FAILS, MECHANICALLY — A DIAGNOSTIC, NOT A POLICY ADDED TO WIN. The table above says
    # escalation does not pay; this says what is actually going on, and it is worse than "it does
    # not pay". Every `unanswerable` request fires EXACTLY ONE rule, so the confident router keeps
    # all of them and runs a tool on every one — `should_have_declined`, the failure this kit calls
    # the most expensive kind, because it returns a confident empty result rather than an error.
    # The requests the router is most sure about are the ones where being sure is the defect.
    fired_by_trap = {}
    for q in reqs:
        fired_by_trap.setdefault(q["trap"], {}).setdefault(rules_fired(q["text"]), 0)
        fired_by_trap[q["trap"]][rules_fired(q["text"])] += 1
    unans = [q for q in reqs if q["trap"] == "unanswerable"]
    kept = [q for q in unans if rules_fired(q["text"]) == 1]
    model_on_unans = {}
    for q in unans:
        o = by_id[q["id"]]["outcome"]
        model_on_unans[o] = model_on_unans.get(o, 0) + 1
    out["diagnostic"] = {
        "rules_fired_by_trap": fired_by_trap,
        "unanswerable_requests": len(unans),
        "unanswerable_firing_exactly_one_rule": len(kept),
        "model_outcomes_on_unanswerable": model_on_unans,
        "reading": "Every unanswerable request fires exactly one rule, so a confidence signal built "
                   "on rule count keeps all of them at the router — the one place the model was "
                   "measurably better (9 of 16 correct against the router's 0).",
    }
    print("\nWHY, MECHANICALLY — and it is worse than 'it does not pay':")
    print("  %d of %d `unanswerable` requests fire EXACTLY ONE rule, so every policy above keeps"
          % (len(kept), len(unans)))
    print("  all of them at the router, which runs a tool on each one. That is")
    print("  `should_have_declined` — the failure this kit calls the most expensive kind.")
    print("  The model got %d of %d of them right. THE ROUTER IS MOST CONFIDENT EXACTLY WHERE IT IS"
          % (model_on_unans.get("correct", 0), len(unans)))
    print("  MOST DANGEROUS, and rule count cannot see the difference.")

    path = os.path.join(RESULTS, "escalation.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s — 0 calls, $0.00" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
