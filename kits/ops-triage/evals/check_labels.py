#!/usr/bin/env python3
"""Load the corpus, and check the labels before anybody scores anything against them.

    python3 -m evals.check_labels

⚑ THE LABELS ARE THE MEASURING STICK, SO THEY GET CHECKED FIRST AND FOR FREE. Every number this kit
publishes is a comparison against this file's contents; a label that is wrong does not produce a
wrong answer, it produces a wrong SCORE, which is worse because it looks like a finding. This runs
in under a second, calls nothing, and is the cheapest thing in the repo.

It re-derives from the events what the generator claimed when it wrote the labels — the two are
built by different code paths reading different files, so agreement between them means something.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import window as W                                                   # noqa: E402

LABELS = os.path.join(HERE, "data", "labelled.jsonl")


def load_labels(path=LABELS):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_windows():
    """The cut stream. `len(labels)` fixes the window count so a truncated events file is a loud
    failure rather than a corpus that quietly got shorter."""
    labels = load_labels()
    return W.cut(W.load_events(), len(labels)), labels


def check(windows, labels):
    problems = []
    if len(windows) != len(labels):
        problems.append("%d windows cut from the stream, %d labelled" % (len(windows), len(labels)))
    by_id = {w["id"]: w for w in windows}
    for lab in labels:
        if lab["id"] not in by_id:
            problems.append("label %s has no window" % lab["id"])
            continue
        if lab["label"] not in ("page", "hold"):
            problems.append("%s carries label %r" % (lab["id"], lab["label"]))
        win = by_id[lab["id"]]
        # ⚑ THE SILENCE LABEL IS RE-DERIVED, NOT TRUSTED. It is the one label whose evidence is an
        # absence, so it is the one a corpus edit can invalidate without changing a single line of
        # text anywhere. Checking it here means the generator and the window cutter have to agree.
        if lab["trap"] == "silence":
            here = {e["service"] for e in win["events"]}
            if lab["silent_service"] in here:
                problems.append("%s is labelled silence for %r and that service emitted lines"
                                % (lab["id"], lab["silent_service"]))
        elif lab["trap"] != "quiet":
            if not win["events"]:
                problems.append("%s (%s) is empty but is not labelled silence" % (lab["id"],
                                                                                 lab["trap"]))
    return problems


def main():
    windows, labels = load_windows()
    problems = check(windows, labels)
    page = sum(1 for r in labels if r["label"] == "page")
    print("LABELS — %d window(s), %d page / %d hold, %d event(s) in the stream"
          % (len(labels), page, len(labels) - page, sum(len(w["events"]) for w in windows)))
    traps = {}
    for r in labels:
        traps[r["trap"]] = traps.get(r["trap"], 0) + 1
    for k, v in sorted(traps.items()):
        print("  %-14s %3d" % (k, v))
    st = W.stats(windows, labels)
    print("\ngate: %d of %d windows are candidates (%.0f%% never reach a model), "
          "gate recall %.1f%%"
          % (st["candidates"], st["windows"], 100 * st["reduction"], 100 * st["gate_recall"]))
    if st["lost_to_gate"]:
        print("  ⚠︎ the gate DROPS %d incident(s) — traps %s. Every score below is conditional on "
              "this." % (len(st["lost_to_gate"]), ", ".join(st["lost_traps"])))
    if problems:
        print("\nLABEL CHECK FAILED — %d problem(s):" % len(problems))
        for p in problems[:12]:
            print("  - %s" % p)
        return 1
    print("\nlabel check clean — every label agrees with the stream it was derived from")
    return 0


if __name__ == "__main__":
    sys.exit(main())
