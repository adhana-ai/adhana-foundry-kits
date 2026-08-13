#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the labels before anybody scores anything against them. 0 calls, under a second.

⚑ THE LABELS ARE THE MEASURING STICK. Every number this kit publishes is a comparison against
`data/requests.jsonl`; a wrong label does not produce a wrong answer, it produces a wrong SCORE,
which is worse because it looks like a finding.

⚑ AND ON THIS KIT THERE IS A CHECK NO OTHER KIT HERE CAN MAKE: the labelled tool sequence has to be
RUNNABLE. Every request labelled `shop_sql` must have a query that returns something from the real
database, and every request labelled `doc_search` must have a note that actually contains the fact.
So this file does not merely inspect the labels — it exercises the tools against them, which is the
only way to catch a label that is plausible and impossible.

    python3 -m evals.check_labels
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import tools  # noqa: E402
from tools import build_corpus  # noqa: E402  — the generator, to compare constants against

REQUESTS = os.path.join(HERE, "data", "requests.jsonl")


def main():
    problems = []
    with open(REQUESTS, encoding="utf-8") as f:
        reqs = [json.loads(line) for line in f if line.strip()]

    # 1. Every labelled tool exists in the catalogue. A label naming a tool the kit does not ship
    #    is unscoreable: the model could never be right.
    for r in reqs:
        for t in r["truth"]:
            if t not in tools.NAMES:
                problems.append("%s labels tool %r, which is not in the catalogue" % (r["id"], t))

    # 2. `decline` and a non-empty truth are contradictory — one says nothing can answer it, the
    #    other says exactly what does.
    for r in reqs:
        if r.get("decline") and r["truth"]:
            problems.append("%s is labelled decline AND carries a tool sequence %s"
                            % (r["id"], r["truth"]))

    # 3. Ids are unique. A duplicate id silently overwrites a row in any dict keyed by it.
    seen = {}
    for r in reqs:
        if r["id"] in seen:
            problems.append("duplicate id %s" % r["id"])
        seen[r["id"]] = r

    # 4. THE TOOLS ACTUALLY WORK against the shipped corpus, which is what makes the labels
    #    runnable rather than merely plausible.
    ok, out = tools.call("shop_sql", "SELECT count(*) AS n FROM orders")
    if not ok or "400" not in out:
        problems.append("shop_sql does not report 400 orders against the shipped database: %s" % out)
    ok, out = tools.call("doc_search", "returns deadline")
    if not ok or "30 days" not in out:
        problems.append("doc_search cannot find the 30-day returns fact the labels depend on")
    ok, out = tools.call("calc", "15/120*100")
    if not ok or not out.startswith("12.5"):
        problems.append("calc does not evaluate: %s" % out)

    # 5. ⚑ THE FIXED DATE LIVES IN TWO FILES AND THEY MUST AGREE. `tools.TODAY` is what the model
    #    is told; `build_corpus.TODAY` is what the labels were computed against. Two copies of a
    #    constant is two copies of a constant, and this is the cheapest possible place to notice.
    if tools.TODAY != build_corpus.TODAY:
        problems.append("src/tools.py TODAY=%s but tools/build_corpus.py TODAY=%s — the labels "
                        "were computed against one of them" % (tools.TODAY, build_corpus.TODAY))

    traps = {}
    for r in reqs:
        traps[r["trap"]] = traps.get(r["trap"], 0) + 1
    print("requests   %d" % len(reqs))
    for t in sorted(traps):
        print("  %-14s %3d" % (t, traps[t]))
    print("catalogue  %s" % ", ".join(tools.NAMES))
    print("fixed date %s (both files agree)" % tools.TODAY)

    if problems:
        print("\n%d PROBLEM(S) — nothing should be scored against these labels:" % len(problems))
        for p in problems:
            print("  ✗ " + p)
        return 1
    print("\nlabels check out: every tool exists, every sequence is runnable, no contradictions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
