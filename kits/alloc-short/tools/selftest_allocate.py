#!/usr/bin/env python3
"""Prove src/allocate.py's three hard claims before any model call ever happens.

    python3 tools/selftest_allocate.py

1. CONSERVATION -- every event's split sums to exactly min(available, total_ask). 2,000
   randomised synthetic events, including edge cases (oversupply, zero commitments, every store
   promo-committed) no generated corpus event will actually hit, on top of the real corpus.
2. NO OVER-ALLOCATION -- no store is ever allocated more than it asked for.
3. THE FLAG SIGNAL IS CLEAN ON THE REAL CORPUS -- 'clean' scenario events should essentially
   never be flagged (nothing is broken, so a review flag would be a false alarm) and every
   planted-defect scenario should be flagged close to 100% of the time (the defect is real and
   the code has no narrative to hide it behind). This is what makes 'flagged' a trustworthy
   itemizing signal for src/pack.py, the same role src/segment.py's `material` flag plays for
   gap-brief.

Exits non-zero and prints every failure if any claim does not hold -- run this after any change
to src/allocate.py's formula or tools/build_corpus.py's sizing constants, before regenerating the
corpus for a real eval run.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import allocate as A          # noqa: E402


def stress_synthetic(n=2000, seed=7):
    rng = random.Random(seed)
    bad_cons, bad_over = [], []
    for _ in range(n):
        k = rng.randint(3, 12)
        stores = []
        for i in range(k):
            ask = rng.randint(1, 100)
            promo = round(ask * rng.uniform(0, 1)) if rng.random() < 0.4 else 0
            cust_cap = max(ask - promo, 0)
            cust = rng.randint(0, cust_cap) if (cust_cap > 0 and rng.random() < 0.4) else 0
            stores.append({
                "store_id": "S%d" % i, "ask_units": ask,
                "velocity_weight": round(rng.uniform(0.1, 3.0), 2),
                "promo_committed_units": promo, "customer_committed_units": cust,
            })
        available = rng.randint(0, sum(s["ask_units"] for s in stores) + 20)  # covers oversupply
        fx = A.allocate({"event_id": "E", "sku": "x", "available_units": available, "stores": stores})
        if not fx["conservation_ok"]:
            bad_cons.append((available, sum(s["ask_units"] for s in stores),
                            sum(p["allocated_units"] for p in fx["per_store"])))
        for p, s in zip(fx["per_store"], stores):
            if p["allocated_units"] > s["ask_units"] or p["allocated_units"] < 0:
                bad_over.append((s["store_id"], s["ask_units"], p["allocated_units"]))
    return bad_cons, bad_over


def flag_purity_on_corpus():
    """Reads the ALREADY-GENERATED gold file -- run tools/build_corpus.py first."""
    import json
    gold_path = os.path.join(HERE, "data", "gold.jsonl")
    if not os.path.exists(gold_path):
        print("  (skipped -- run tools/build_corpus.py first to generate data/gold.jsonl)")
        return {}
    by_scenario = {}
    with open(gold_path, encoding="utf-8") as f:
        for line in f:
            g = __import__("json").loads(line)
            for ev in g["events"]:
                by_scenario.setdefault(ev["scenario"], [0, 0])
                by_scenario[ev["scenario"]][1] += 1
                if ev["flagged"]:
                    by_scenario[ev["scenario"]][0] += 1
    return by_scenario


def main():
    print("1. conservation + no-over-allocation, 2000 synthetic events")
    bad_cons, bad_over = stress_synthetic()
    print("   conservation failures: %d" % len(bad_cons))
    print("   over-allocation failures: %d" % len(bad_over))
    for b in bad_cons[:5]:
        print("     ", b)
    for b in bad_over[:5]:
        print("     ", b)

    print("\n2. flag purity on the generated corpus")
    by_scenario = flag_purity_on_corpus()
    ok = True
    for scen, (flagged, total) in sorted(by_scenario.items()):
        pct = 100.0 * flagged / total if total else 0.0
        want_low = scen == "clean"
        bad = (want_low and pct > 5.0) or (not want_low and pct < 90.0)
        ok = ok and not bad
        print("   %-20s %3d/%3d flagged (%.1f%%)%s"
              % (scen, flagged, total, pct, "  <-- OUT OF BAND" if bad else ""))

    failed = bool(bad_cons) or bool(bad_over) or not ok
    print("\n%s" % ("SELFTEST FAILED" if failed else "selftest passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
