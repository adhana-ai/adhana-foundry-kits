#!/usr/bin/env python3
"""Score the rules and the model TOGETHER, from outputs already recorded. 0 calls, $0.00.

    python3 -m evals.combine

⚑ WHY THIS FILE EXISTS, AND IT IS NOT "TRY THINGS UNTIL ONE WINS". The run and the floor failed on
DISJOINT traps, which is a structural fact about the two deciders rather than a lucky split:

    the rules are blind where the evidence is absent   quiet-killer (0/8), silence (0/6)
    the model is unreliable where the evidence is loud  flapping (24/40 false pages),
                                                        cascade (2/6 MISSED)

When two deciders fail in different places, the interesting question is not "which is better" — it
is what a system built out of both does. That question is answerable for nothing, because the
model's verdict on all 123 windows is already on disk.

⚠︎ THIS IS RE-SCORING RECORDED OUTPUTS, NOT A SECOND RUN, and the distinction is worth protecting.
The model's output is the evidence; a combination rule is an opinion about how to act on it. What
this must never become is trying rules until the number improves — so **every combination below is
declared before it is scored, each one is a defensible product design somebody would actually
build, and all of them are printed whether they win or lose.** Adding a combination because the
first four disappointed is how this file would stop being honest.

⚠︎ AND NONE OF IT IS A SECOND OPINION ON THE SCORER. Every row goes through `src/decide.py`, the
same module that scored the run and the floor.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_windows                                    # noqa: E402
from src import decide, rules, window as W                                     # noqa: E402

RESULTS = os.path.join(HERE, "results")
FLOOR_THRESHOLD = 49          # the floor's best setting, from results/baseline.json


def load_run(run_id):
    path = os.path.join(RESULTS, "eval-%s.json" % run_id)
    return json.load(open(path, encoding="utf-8"))


# The combinations, declared up front. Each takes (model_verdict, floor_verdict, has_signal) and
# returns a verdict. `has_signal` is whether the RULES had anything to look at — loud lines or a
# keyword — which is the only input that distinguishes "the rules said hold" from "the rules had
# nothing to say".
COMBOS = [
    ("model alone", lambda m, f, sig: m,
     "the run as it was scored"),
    ("rules alone", lambda m, f, sig: f,
     "the free floor at its best setting, from results/baseline.json"),
    ("either pages (OR)", lambda m, f, sig: decide.PAGE if decide.PAGE in (m, f) else decide.HOLD,
     "page if either decider says so — the cautious build"),
    ("both must agree (AND)",
     lambda m, f, sig: decide.PAGE if m == decide.PAGE and f == decide.PAGE else decide.HOLD,
     "page only when both agree — the quiet build"),
    ("rules decide, model escalates the quiet ones",
     lambda m, f, sig: f if sig else m,
     "the rules keep the windows they have evidence for; the model is asked ONLY about windows "
     "where the rules are structurally blind"),
]


def main():
    windows, labels = load_windows()
    idx = {w["id"]: i for i, w in enumerate(windows)}
    run = load_run("r014-ops-triage-flash")
    model_of = {r["id"]: (r["verdict"] if r["replied"] else None) for r in run["rows"]}

    judged = [lab for lab in labels if lab["id"] in model_of]
    print("COMBINATIONS — %d window(s), %d model call(s) already spent, %d new call(s)\n"
          % (len(judged), len(model_of), 0))

    floor_rows = {r["id"]: r for r in rules.score(windows, judged, FLOOR_THRESHOLD)}
    out = {"kind": "combination", "calls": 0, "cost_usd": 0.0,
           "run_id": run["run_id"], "floor_threshold": FLOOR_THRESHOLD,
           "note": "Re-scored from recorded outputs through src/decide.py. No model was called.",
           "combinations": {}}

    print("  %-44s %-8s %-13s %-11s %s"
          % ("", "missed", "false pages", "detection", "traps handled"))
    for name, fn, why in COMBOS:
        rows = []
        for lab in judged:
            i = idx[lab["id"]]
            c = W.counts(windows[i])
            silent = W.gone_silent(windows, i)
            # ⚠︎ `has_signal` MEANS "THE RULES HAD SOMETHING TO GRIP", NOT "THE RULES FIRED", AND THE
            # FIRST VERSION OF THIS LINE CONFUSED THE TWO. It read
            # `c["loud"] >= FLOOR_THRESHOLD or ...`, which is the rules' VERDICT, not their
            # competence — so a flapping window with 47 error lines counted as "the rules are
            # blind here" and was handed to the model, when in fact the rules have 47 lines to look
            # at and correctly decide to hold. The escalation combination scored identically to a
            # plain OR because of it, which is what gave the bug away: two rules with different
            # logic producing the same number is a coincidence worth two minutes.
            #
            # ⚠︎ FIXING IT IMPROVED THE RESULT, AND THAT IS EXACTLY THE CIRCUMSTANCE THIS FILE
            # WARNS ABOUT AT THE TOP. Stated plainly so a reader can judge it: the predicate was
            # changed because its code contradicted its own declared description — "windows where
            # the rules are structurally blind" — and not because the number was disappointing. The
            # description was written before the run; the code is now what it always said.
            sig = bool(c["loud"] or rules.keyword_hits(windows[i]) or silent)
            f = floor_rows[lab["id"]]["verdict"]
            if silent and f == decide.HOLD:
                f = decide.PAGE          # the absence floor, same as baseline.py's best row
            m = model_of[lab["id"]]
            v = fn(m, f, sig) if m else f     # a silent model falls back to the rules, and says so
            rows.append({"id": lab["id"], "label": lab["label"], "trap": lab["trap"],
                         "outcome": decide.outcome(lab["label"], v, True)})
        t = decide.tally(rows)
        handled = sorted(k for k, v in decide.trap_verdict(rows).items() if v and k != "quiet")
        t["traps_handled"] = handled
        t["why"] = why
        out["combinations"][name] = t
        print("  %-44s %-8d %-13d %-11s %d of 6  %s"
              % (name, t["missed_incidents"], t["false_pages"],
                 "%.0f%%" % (100 * t["detection"]) if t["detection"] is not None else "n/a",
                 len(handled), " ".join(handled)))
        print("  %-44s %s" % ("", why))

    # ⚑ THE READING, STATED RATHER THAN LEFT TO THE TABLE. A combination that beats both parents on
    # BOTH numbers is the only outcome that would justify building one, and if none does, the honest
    # answer is that this corpus does not support a combined pager.
    m = out["combinations"]["model alone"]
    f = out["combinations"]["rules alone"]
    best = None
    for name, t in out["combinations"].items():
        if name in ("model alone", "rules alone"):
            continue
        if t["missed_incidents"] <= min(m["missed_incidents"], f["missed_incidents"]) and \
           t["false_pages"] <= min(m["false_pages"], f["false_pages"]):
            if best is None or (t["missed_incidents"], t["false_pages"]) < \
                               (best[1]["missed_incidents"], best[1]["false_pages"]):
                best = (name, t)
    out["beats_both_parents"] = best[0] if best else None
    print("\nDOES ANY COMBINATION BEAT BOTH PARENTS ON BOTH NUMBERS?")
    if best:
        print("  ✓ %s — %d missed, %d false pages, against the model's %d/%d and the rules' %d/%d."
              % (best[0], best[1]["missed_incidents"], best[1]["false_pages"],
                 m["missed_incidents"], m["false_pages"],
                 f["missed_incidents"], f["false_pages"]))
    else:
        print("  ✗ NO. Every combination is worse than one parent or the other on at least one")
        print("    number. The two deciders fail in different places, and on this corpus that is")
        print("    not enough to build a better pager out of them — it is only enough to know")
        print("    which half of the problem each one owns.")

    path = os.path.join(RESULTS, "combinations.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s — 0 calls, $0.00" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
