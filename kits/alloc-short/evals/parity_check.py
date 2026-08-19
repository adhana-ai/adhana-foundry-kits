#!/usr/bin/env python3
"""The protected-class guardrail, MEASURED rather than merely promised.

    python3 -m evals.parity_check

src/allocate.py's docstring states that `trade_area_tier` is never a parameter of the allocation
function -- true by construction, checkable by reading the function signature. This script proves
the CONSEQUENCE of that exclusion instead: that a store's allocated fraction of its own ask does
not systematically differ by trade_area_tier across the corpus.

⚑ A PERMUTATION TEST, NOT A PROMISE. Comparing raw group means would be confounded by ask size,
velocity, promo and customer commitments all varying between stores for reasons that have
nothing to do with tier. The test instead asks a sharper question: if `trade_area_tier` carries
no information about allocated fraction, then relabelling which tier each store within an event
"belongs to" should not systematically change how extreme the tier-to-tier spread looks. Shuffle
the tier labels WITHIN each event (so every store keeps its own ask, velocity, promo and customer
figures -- the tier label alone is randomised), recompute the same spread statistic 500 times, and
check that the REAL labelling is not more extreme than the shuffled ones. This is exchangeability
under the null of "no tier effect", the standard test for exactly this question, and it needs no
model call, no key and no spend.

Exits non-zero if the real spread lands in the top 5% of the permutation distribution -- the
signal a real deployment's fair-lending or disparate-impact review would also key on.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")

from src import allocate as A          # noqa: E402

TIERS = ("A", "B", "C")


def _rows(sessions):
    """Every (event, store) allocated fraction, tagged with its tier -- recomputed fresh from
    src/allocate.py, which never receives the tier as an input."""
    rows = []
    for s in sessions:
        for ev in s["events"]:
            fx = A.allocate(ev)
            tier_by_store = {st["store_id"]: st["trade_area_tier"] for st in ev["stores"]}
            for p in fx["per_store"]:
                if p["ask_units"] <= 0:
                    continue
                rows.append({
                    "tier": tier_by_store[p["store_id"]],
                    "fraction": p["allocated_units"] / p["ask_units"],
                })
    return rows


def _spread(rows, tier_of):
    means = {}
    for t in TIERS:
        vals = [r["fraction"] for r in rows if tier_of(r) == t]
        if vals:
            means[t] = sum(vals) / len(vals)
    if len(means) < 2:
        return 0.0, means
    return max(means.values()) - min(means.values()), means


def parity_check(sessions, n_perm=500, seed=20260818):
    rows = _rows(sessions)
    rng = random.Random(seed)

    real_spread, real_means = _spread(rows, lambda r: r["tier"])

    # Group rows by event so a shuffle only reassigns tier labels AMONG that event's own stores
    # -- preserving each store's real ask/velocity/promo/customer-driven fraction, randomising
    # only which tier label it wears.
    by_event = {}
    for s in sessions:
        for ev in s["events"]:
            fx = A.allocate(ev)
            tier_by_store = {st["store_id"]: st["trade_area_tier"] for st in ev["stores"]}
            entries = [(p["allocated_units"] / p["ask_units"] if p["ask_units"] else None,
                       tier_by_store[p["store_id"]])
                      for p in fx["per_store"] if p["ask_units"] > 0]
            by_event[ev["event_id"]] = entries

    perm_spreads = []
    for _ in range(n_perm):
        perm_rows = []
        for entries in by_event.values():
            tiers = [t for _, t in entries]
            rng.shuffle(tiers)
            for (frac, _orig), t in zip(entries, tiers):
                perm_rows.append({"tier": t, "fraction": frac})
        spread, _ = _spread(perm_rows, lambda r: r["tier"])
        perm_spreads.append(spread)

    worse = sum(1 for s in perm_spreads if s >= real_spread)
    p_value = worse / n_perm if n_perm else 1.0

    return {
        "rows": len(rows),
        "tier_means": {t: round(v, 4) for t, v in real_means.items()},
        "real_spread": round(real_spread, 4),
        "permutations": n_perm,
        "p_value": round(p_value, 4),
        "passed": p_value > 0.05,
    }


def main():
    path = os.path.join(DATA, "sessions.jsonl")
    if not os.path.exists(path):
        print("no data/sessions.jsonl -- run tools/build_corpus.py first")
        return 1
    sessions = [json.loads(l) for l in open(path, encoding="utf-8")]
    result = parity_check(sessions)
    print("rows scored     : %d" % result["rows"])
    print("tier means      : %s" % result["tier_means"])
    print("real spread     : %.4f" % result["real_spread"])
    print("permutation p   : %.4f  (n=%d shuffles)" % (result["p_value"], result["permutations"]))
    print("PARITY HOLDS" if result["passed"] else "PARITY GUARDRAIL FAILED -- spread is not "
         "explained by chance")
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "parity-check.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
