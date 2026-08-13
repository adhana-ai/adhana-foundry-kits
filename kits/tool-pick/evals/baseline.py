#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score the free floor over all 120 requests, at every setting. 0 calls, $0.00.

⚑ THIS RUNS BEFORE THE MODEL AND IT IS ALLOWED TO WIN. UC012's rule floor beat its model on both
published numbers, and that became the kit's headline finding rather than a problem to hide. The
point of measuring the floor first is that the comparison is honest either way.

    python3 -m evals.baseline
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import router, score as S  # noqa: E402

REQUESTS = os.path.join(HERE, "data", "requests.jsonl")
RESULTS = os.path.join(HERE, "results")


def load():
    with open(REQUESTS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    reqs = load()
    sweep = router.sweep(reqs)

    print("THE FREE FLOOR — a keyword router, %d requests, 0 model calls\n" % len(reqs))
    print("  cap  exact   correct  wrong  early  over  declined  calls  wasted")
    for row in sweep:
        s, c = row["summary"], row["summary"]["counts"]
        print("  %-4d %-7s %-8d %-6d %-6d %-5d %-9d %-6d %d"
              % (row["cap"],
                 "%.1f%%" % (100 * s["sequence_exact"]) if s["sequence_exact"] is not None else "n/a",
                 c["correct"], c["wrong_tool"], c["stopped_early"], c["kept_going"],
                 c["should_have_declined"], s["calls_total"], s["calls_wasted"]))

    best = max(sweep, key=lambda r: r["summary"]["counts"]["correct"])
    print("\nbest setting: cap %d — %d of %d exactly right (%.1f%%)"
          % (best["cap"], best["summary"]["counts"]["correct"], len(reqs),
             100 * best["summary"]["sequence_exact"]))

    print("\nby trap, at the best setting — which KIND of hard case it fails:")
    for trap, t in sorted(best["by_trap"].items(), key=lambda x: -x[1]["wrong"]):
        print("  %-14s %d/%d wrong   %s"
              % (trap, t["wrong"], t["requests"],
                 ", ".join("%s %d" % kv for kv in sorted(t["outcomes"].items()))))

    handled = sorted(k for k, v in best["traps_handled"].items() if v)
    print("\ntrap kinds handled COMPLETELY at any setting:")
    ever = {}
    for row in sweep:
        for trap, ok in row["traps_handled"].items():
            ever[trap] = ever.get(trap, False) or ok
    for trap in sorted(ever):
        print("   %-14s %s" % (trap, "yes" if ever[trap] else "NO — no setting gets it"))
    unreachable = sorted(t for t, ok in ever.items() if not ok)

    # ⚑ THE CLAIM IS CHECKED, NOT ASSERTED. If some setting ever does get every trap right, that is
    # a finding and this has to say so rather than print the sentence it was written to print.
    print("\n%s" % ("NO SETTING GETS EVERY TRAP RIGHT. Unreachable by any keyword rule: %s."
                    % ", ".join(unreachable) if unreachable else
                    "⚠︎ SOME SETTING GETS EVERY TRAP RIGHT — that is a finding; the page must say "
                    "so and the case for a model here is weaker than the wireframe claimed."))

    # ⚑ A CONTROL, BECAUSE THE FLOOR PASSING A TRAP IS THE SUSPICIOUS RESULT, NOT THE GOOD ONE.
    # It gets every `wrong-surface` request right — the ones whose loudest noun names the wrong
    # tool — which is exactly what a keyword router should NOT be able to do. The suspicion is that
    # it wins on rule ORDER (doc_search is tried before shop_sql) rather than on anything it
    # understands. Swapping those two rules tests it. Nothing is re-tuned on the strength of the
    # answer: the floor stays as written, because tuning it to fail would be as dishonest as
    # tuning it to pass.
    swapped = list(router.RULES)
    i_doc = [n for n, _ in swapped].index("doc_search")
    i_sql = [n for n, _ in swapped].index("shop_sql")
    swapped[i_doc], swapped[i_sql] = swapped[i_sql], swapped[i_doc]
    real_rules = router.RULES
    try:
        router.RULES = swapped
        ctl = S.by_trap(router.score(reqs, best["cap"]))
    finally:
        router.RULES = real_rules
    ws = ctl.get("wrong-surface", {})
    print("\nCONTROL — the same router with doc_search and shop_sql tried in the other order:")
    print("  wrong-surface  %d/%d wrong (was %d/%d)   %s"
          % (ws.get("wrong", 0), ws.get("requests", 0),
             best["by_trap"]["wrong-surface"]["wrong"],
             best["by_trap"]["wrong-surface"]["requests"],
             ", ".join("%s %d" % kv for kv in sorted(ws.get("outcomes", {}).items()))))
    print("  %s" % ("So the floor passes that trap on RULE ORDER, not on reading — it is one line "
                    "away from failing all of them, and its score there is luck."
                    if ws.get("wrong", 0) > best["by_trap"]["wrong-surface"]["wrong"] else
                    "Order does not explain it — the floor passes that trap for some other reason, "
                    "which is worth finding before the page claims anything about it."))

    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, "baseline.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"requests": len(reqs), "rules": router.RULES, "sweep": sweep,
                   "best_cap": best["cap"], "unreachable_traps": unreachable,
                   "rule_order_control": {"swapped": [n for n, _ in swapped],
                                          "wrong_surface": ws},
                   "calls": 0, "cost_usd": 0.0}, f, indent=1, sort_keys=True)
    print("\nwrote %s   —   0 calls, $0.00" % os.path.relpath(out, HERE))
    print("handled at the best setting: %s" % (", ".join(handled) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
