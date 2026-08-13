#!/usr/bin/env python3
"""What you get without a model. Run this BEFORE reading any score this kit produces.

    python3 -m evals.baseline

⚑ THE FLOOR HERE IS NOT A STRAWMAN, AND ON THIS KIT THAT IS THE ENTIRE ARGUMENT. On most kits in
this repo the free baseline is a constant, and it exists to prove the model is doing something.
Here the free answer is a WORKING PAGER — an error-count threshold plus a keyword regex — which is
what a very large number of production alerting setups amount to once the dashboards are stripped
off. So this file does not ask "is the model better than nothing". It asks "is the model better
than the thing you already have", and that is the only version of the question worth paying to
answer.

⚑ FREE IN THE STRICT SENSE. Nothing is sent anywhere. Every number below can be reproduced by
anybody with a clone and no key, as often as they like, which is why they are committed rather than
quoted.

⚠︎ SCORED BY `src/decide.py`, UNCHANGED — the same module `evals/run.py` scores the model with.
Same windows, same labels, same five outcomes. A floor with its own scorer is a second opinion.

⚠︎ AND THE THRESHOLD IS SWEPT, NOT CHOSEN. A single threshold would let this file pick the number
that flatters whichever conclusion was wanted. The sweep publishes the whole trade — every setting,
its missed incidents and its false pages — so a model has to beat a CURVE rather than one
convenient point.

⚑ THE THIRD FLOOR EXISTS SO THE COMPARISON CANNOT BE ACCUSED OF CHEATING. The model is told, in its
prompt, when a service has gone silent — a fact `src/window.py` computes in code. Handing the model
evidence the rules were never given would rig the comparison, so `count+keyword+absence` gives the
rules the identical fact. It is the strongest free floor, it is the one the headline is drawn from,
and it is still not enough. That is a finding, and it belongs to the corpus rather than to the
model.

── THE CLAIM THIS FILE EXISTS TO TEST ─────────────────────────────────────────────────────────────

The Stop-A wireframe asserted that **no setting of the free rules gets all six traps right**. That
was a design intention when it was written, with no corpus behind it. This file measures it, at
every threshold, for all three floors, and it is allowed to come out false — if some setting does
get all six, the kit is not worth building and the report has to say so in the first line.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_windows                                   # noqa: E402
from src import decide, rules, window as W                                    # noqa: E402

# Swept across the whole range the corpus can produce, not a hand-picked few: the loudest window
# carries a little over fifty error lines, so anything past that pages nothing at all.
THRESHOLDS = (1, 2, 5, 10, 16, 20, 25, 31, 40, 47, 48, 49, 54, 60, 100, 220)
TRAPS = ("flapping", "retry-storm", "deploy", "quiet-killer", "cascade", "silence")


def floor_rows(windows, labels, threshold, use_count=True, use_keyword=True, use_absence=False):
    """One floor at one setting, through the shared scorer."""
    idx = {w["id"]: i for i, w in enumerate(windows)}
    rows = rules.score(windows, labels, threshold, use_count, use_keyword)
    if use_absence:
        for r in rows:
            silent = W.gone_silent(windows, idx[r["id"]])
            if silent and r["verdict"] == decide.HOLD:
                r["verdict"] = decide.PAGE
                r["reasons"] = r["reasons"] + ["silent: %s" % ", ".join(silent)]
                r["outcome"] = decide.outcome(r["label"], decide.PAGE, True)
    return rows


def handled(rows):
    """Which of the six trap kinds this setting got COMPLETELY right."""
    v = decide.trap_verdict(rows)
    return sorted(t for t in TRAPS if v.get(t))


def main():
    windows, labels = load_windows()
    cand = W.candidates(windows)
    judged = [lab for lab in labels if lab["id"] in cand]
    st = W.stats(windows, labels)

    print("FLOORS — %d window(s) judged, 0 model calls, $0.00\n" % len(judged))
    print("  the gate passes %d of %d windows; the other %d are held for free and never reach"
          % (st["candidates"], st["windows"], st["windows"] - st["candidates"]))
    print("  anything. Gate recall %.1f%% — every incident in the corpus survives it.\n"
          % (100 * st["gate_recall"]))

    out = {"kind": "baseline", "calls": 0, "cost_usd": 0.0,
           "dataset": {"file": "data/labelled.jsonl", "windows": len(judged),
                       "page": sum(1 for r in judged if r["label"] == "page"),
                       "hold": sum(1 for r in judged if r["label"] == "hold")},
           "gate": st,
           "note": "Deterministic pagers scored by src/decide.py, the same module evals/run.py "
                   "scores the model with. No model was called.",
           "floors": {}}

    # ── the two constants, because they are the ceiling and floor of doing nothing clever ─────────
    for name, verdict, why in (
        ("always-hold", decide.HOLD,
         "never wakes anybody: zero false pages, and every incident is found by a customer"),
        ("always-page", decide.PAGE,
         "wakes somebody every five minutes: zero missed incidents, and the pager is ignored "
         "by Tuesday"),
    ):
        rows = [{"id": r["id"], "label": r["label"], "trap": r["trap"],
                 "outcome": decide.outcome(r["label"], verdict, True)} for r in judged]
        rec = decide.tally(rows)
        rec["why"] = why
        rec["traps_handled"] = handled(rows)
        out["floors"][name] = rec
        print("  %-14s missed %2d   false pages %3d   %s"
              % (name, rec["missed_incidents"], rec["false_pages"], why))

    # ⚑ AND THE ACCURACY NUMBER NOBODY SHOULD PUBLISH, PRINTED ONCE SO IT CANNOT BE PUBLISHED BY
    # ACCIDENT. On an 8%-page corpus "hold everything" is right about nine times in ten. That is
    # the number a single-figure report would lead with, and it is the behaviour this kit exists
    # to catch.
    hold_acc = 100.0 * sum(1 for r in judged if r["label"] == "hold") / len(judged)
    print("\n  ⚠︎ 'always-hold' scores %.1f%% ACCURATE on this set while missing every incident in"
          % hold_acc)
    print("     it. That is why this kit publishes two numbers and never one.\n")

    # ── the three real floors, swept ──────────────────────────────────────────────────────────────
    variants = [
        ("count", dict(use_count=True, use_keyword=False, use_absence=False),
         "an error-count threshold alone — the slider on the wireframe"),
        ("count+keyword", dict(use_count=True, use_keyword=True, use_absence=False),
         "threshold plus a real SRE keyword regex — what teams actually run"),
        ("count+keyword+absence", dict(use_count=True, use_keyword=True, use_absence=True),
         "…and the silence signal the model is also given, so the comparison is fair"),
        # ⚑ THE CONTROL, ADDED AFTER READING THE THREE SWEEPS ABOVE. The count threshold's best
        # settings are indistinguishable from its most extreme one, which is only possible if the
        # count is contributing nothing that the keyword was not already catching. Dropping it
        # entirely is the way to prove that rather than infer it — and if this row matches the row
        # above, then the knob every on-call rotation spends its afternoons tuning is, on this
        # corpus, either inert or a source of false pages and never anything else.
        ("keyword+absence (no count at all)",
         dict(use_count=False, use_keyword=True, use_absence=True),
         "the control: is the error-count threshold contributing anything at its best setting?"),
    ]
    best = None
    for name, kw, why in variants:
        print("  %s — %s" % (name, why))
        print("  %-10s %-8s %-13s %-9s %s" % ("threshold", "missed", "false pages", "detection",
                                              "traps handled"))
        sweep = []
        for t in THRESHOLDS:
            rows = floor_rows(windows, judged, t, **kw)
            rec = decide.tally(rows)
            rec["threshold"] = t
            rec["traps_handled"] = handled(rows)
            rec["floor"] = name
            sweep.append(rec)
            print("  %-10d %-8d %-13d %-9s %d of 6  %s"
                  % (t, rec["missed_incidents"], rec["false_pages"],
                     "%.0f%%" % (100 * rec["detection"]) if rec["detection"] is not None else "n/a",
                     len(rec["traps_handled"]), " ".join(rec["traps_handled"])))
            if best is None or (len(rec["traps_handled"]), -rec["missed_incidents"],
                                -rec["false_pages"]) > (len(best["traps_handled"]),
                                                        -best["missed_incidents"],
                                                        -best["false_pages"]):
                best = rec
        out["floors"][name] = sweep
        if not kw["use_count"]:
            # One setting, printed once — the threshold argument is ignored when the count is off,
            # so sixteen identical rows would be sixteen ways of saying the same thing.
            out["floors"][name] = sweep[:1]
        print()

    # ⚑ THE CONTROL, RESOLVED IN CODE RATHER THAN BY EYE. Two rows that look alike in a terminal is
    # an impression; the same counts is a measurement.
    with_count = min((r for r in out["floors"]["count+keyword+absence"]),
                     key=lambda r: (len(TRAPS) - len(r["traps_handled"]),
                                    r["missed_incidents"], r["false_pages"]))
    without = out["floors"]["keyword+absence (no count at all)"][0]
    same = (with_count["missed_incidents"] == without["missed_incidents"]
            and with_count["false_pages"] == without["false_pages"]
            and with_count["traps_handled"] == without["traps_handled"])
    out["count_threshold_contributes"] = {
        "best_with_count": {"threshold": with_count["threshold"],
                            "missed_incidents": with_count["missed_incidents"],
                            "false_pages": with_count["false_pages"],
                            "traps_handled": with_count["traps_handled"]},
        "without_count_at_all": {"missed_incidents": without["missed_incidents"],
                                 "false_pages": without["false_pages"],
                                 "traps_handled": without["traps_handled"]},
        "identical": same}
    print("THE COUNT THRESHOLD, AS A CONTROL:")
    if same:
        print("  ⚑ AT ITS BEST SETTING IT CONTRIBUTES NOTHING. Deleting the error-count threshold")
        print("     entirely produces the identical result — %d missed, %d false pages, the same"
              % (without["missed_incidents"], without["false_pages"]))
        print("     %d traps handled. Every other setting of it only adds false pages. The knob"
              % len(without["traps_handled"]))
        print("     an on-call rotation spends its afternoons tuning is, on this corpus, inert at")
        print("     best and harmful the rest of the time.")
    else:
        print("  it earns its place: best-with-count %d missed / %d false pages against %d / %d"
              % (with_count["missed_incidents"], with_count["false_pages"],
                 without["missed_incidents"], without["false_pages"]))
    print()

    # ── the claim, measured ───────────────────────────────────────────────────────────────────────
    all_six = [r for v in variants for r in out["floors"][v[0]] if len(r["traps_handled"]) == 6]
    out["claim"] = {
        "asserted_at_stop_a": "no setting of the free rules gets all six traps right",
        "settings_tested": sum(len(out["floors"][v[0]]) for v in variants),
        "settings_getting_all_six": len(all_six),
        "holds": not all_six,
        "best": {"floor": best["floor"], "threshold": best["threshold"],
                 "traps_handled": best["traps_handled"],
                 "missed_incidents": best["missed_incidents"],
                 "false_pages": best["false_pages"]},
    }
    # ⚠︎ DERIVED, NOT TYPED. This line said "across three floors" while the list below it held four
    # — the exact shape this estate gates against in prose everywhere else, arriving in a file
    # whose entire job is to be trusted about numbers.
    print("THE STOP-A CLAIM, MEASURED over %d setting(s) across %d floors:"
          % (out["claim"]["settings_tested"], len(variants)))
    if all_six:
        print("  ⚠︎ IT DOES NOT HOLD. %d setting(s) got all six traps right. The free floor is "
              "enough and this kit is not worth building — that is the finding." % len(all_six))
    else:
        print("  ✓ IT HOLDS. No setting got all six. The best is %s at threshold %d: %d of 6 "
              "(%s), missing %d incident(s) and sending %d false page(s)."
              % (best["floor"], best["threshold"], len(best["traps_handled"]),
                 " ".join(best["traps_handled"]), best["missed_incidents"], best["false_pages"]))
        missing = [t for t in TRAPS if t not in best["traps_handled"]]
        print("  The trap(s) NO free setting handles: %s." % ", ".join(missing))
        out["claim"]["unreachable_traps"] = missing

    # ⚑ AND THE REASON, WHICH IS STRUCTURAL RATHER THAN A MATTER OF TUNING. Stated in the file that
    # measured it, so nobody spends an afternoon looking for the threshold that would fix it.
    print("\nWHY, and it is not a tuning problem:")
    print("  quiet-killer  one WARN line and no alarming word in it, because nothing is on fire")
    print("                yet. No count reacts to one line and no regex matches ordinary English")
    print("                about a certificate. It is a fuse, and it is lit.")
    print("  silence       zero lines. A regex cannot match an absence. The `absence` floor above")
    print("                catches it only because src/window.py computed the fact in code first.")
    print("\nThat gap — %s — is what a model is being asked to close, and the run has not been"
          % ", ".join(out["claim"].get("unreachable_traps", []) or ["none"]))
    print("fired. Nothing in this file spent anything.")

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    path = os.path.join(HERE, "results", "baseline.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("\nwrote %s" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
