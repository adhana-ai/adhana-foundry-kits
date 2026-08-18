#!/usr/bin/env python3
"""Generate the supplier agreements and the draft orders that check against them, from a fixed
seed.

    python3 tools/build_corpus.py

Writes data/agreements/<supplier_id>.txt, data/orders.jsonl and data/gold.jsonl, byte-identical on
every run. Nothing is fetched and nothing is licensed from anybody: every supplier, SKU and clause
here is invented, so the corpus ships under this repo's MIT licence and there is no third-party
grant to verify.

⚑ WHY THE AGREEMENTS ARE INVENTED, AND WHY THAT IS THE HONEST CHOICE HERE RATHER THAN THE
CONVENIENT ONE. A real supplier agreement names a real counterparty, real contracted pricing and
real payment terms — exactly the material a business will not let leave the building, let alone
sit in a public repo under an MIT licence. A synthetic set is the only kind of reconcile corpus
that can be re-run by a stranger with a clone and no NDA to sign. See data/SOURCES.md.

⚑ THE AGREEMENT IS PROSE ON PURPOSE. The five checks below are simple comparisons once the numbers
are in hand — the actual job is getting them out of a paragraph that phrases the same fact a
different way every time ("Minimum order quantity: 240 units, packed in cartons of 24" vs "Orders
must clear a 150-unit floor"). A structured price sheet would make this kit a lookup, not a
reconcile. See src/reconcile.py for what the model is actually asked to do with it.

⚑ FIVE CHECKS, EACH PLANTED ON PURPOSE. A corpus that cannot express a check's failure cannot show
the eval earning its keep — same discipline as ops-triage's planted traps. Every order below is
generated with a KNOWN verdict per check, counted and asserted:

    cost         the line's unit cost against the agreement's contracted cost for that SKU.
    min_qty      the line's quantity against the agreement's minimum order / pack rounding.
    lead_time    the order's requested ship window against the agreement's quoted lead time.
    ship_to      the order's ship-to region against the agreement's approved regions.
    order_value  the order's total against the agreement's standing-authorization band.

Each check on each order is exactly one of three things: CLEAN (the value satisfies the clause),
DEFECT (the value violates a clause the agreement states), or UNVERIFIABLE (the agreement is silent
on the relevant SKU or field — a checker that guesses here is worse than one that says so).
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
SEED = 20260817                              # fixed. change it and every downstream file changes.

SUPPLIER_NAMES = [
    "Nordholt Fasteners", "Briarcombe Supply Co", "Kestrel Components", "Vantage Materials Group",
    "Ashgrove Industrial", "Palmerton & Sons", "Delacroix Hardware", "Millbrook Fabrication",
    "Corvid Logistics Supply", "Thornfield Parts Co", "Underwood Metalworks", "Bellcastle Trading",
]
REGIONS = ["NA-EAST", "NA-WEST", "NA-CENTRAL", "EU-NORTH", "EU-SOUTH", "APAC-EAST"]
TERMS = ["Net 30", "Net 45", "Net 60", "2/10 Net 30"]
CHECKS = ("cost", "min_qty", "lead_time", "ship_to", "order_value")
VERDICTS = ("clean", "defect", "unverifiable")


def _supplier_id(i):
    return "SUP-%04d" % (100 + i)


def _sku(supplier_i, j):
    return "SKU-%02d%02d" % (supplier_i + 10, j)


def build_suppliers(rng):
    """Each supplier gets 3-4 SKUs with a contracted cost, a min-order/pack rule, a lead time, an
    approved ship-to list, payment terms and (usually, not always) an order-value band. One in
    four suppliers omits the value band and one in six omits the ship-to list entirely — those
    omissions are what makes `unverifiable` a real, not a hypothetical, verdict."""
    suppliers = []
    for i, name in enumerate(SUPPLIER_NAMES):
        n_sku = rng.choice([3, 3, 4, 4])
        skus = {}
        for j in range(n_sku):
            skus[_sku(i, j)] = round(rng.uniform(2.25, 48.00), 2)
        min_qty = rng.choice([25, 50, 100, 150, 240, 300])
        pack = rng.choice([1, 6, 12, 24, 25])
        lead_time = rng.choice([5, 7, 9, 10, 14, 21])
        has_regions = rng.random() > (1.0 / 6)
        regions = sorted(rng.sample(REGIONS, k=rng.choice([1, 2, 3]))) if has_regions else None
        terms = rng.choice(TERMS)
        has_band = rng.random() > 0.25
        band = None
        if has_band:
            lo = rng.choice([250, 500, 750, 1000])
            hi = rng.choice([25000, 40000, 50000, 75000])
            band = (lo, hi)
        suppliers.append({
            "id": _supplier_id(i), "name": name, "skus": skus, "min_qty": min_qty, "pack": pack,
            "lead_time_days": lead_time, "regions": regions, "terms": terms, "value_band": band,
        })
    return suppliers


def _cost_paragraph(sup, rng):
    variant = rng.choice([0, 1, 2])
    items = sorted(sup["skus"].items())
    if variant == 0:
        return " ".join("Contracted unit cost for %s is $%.2f." % (s, c) for s, c in items)
    if variant == 1:
        return ("Per-unit pricing under this agreement: " +
                "; ".join("%s at $%.2f/ea" % (s, c) for s, c in items) + ".")
    parts = ["The parties have agreed the following unit costs."]
    for s, c in items:
        parts.append("For %s, the price is fixed at $%.2f per unit." % (s, c))
    return " ".join(parts)


def _min_qty_clause(sup, rng):
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        if sup["pack"] > 1:
            return ("Minimum order quantity is %d units per line, packed in cartons of %d; "
                    "partial cartons are rounded up to the next full carton."
                    % (sup["min_qty"], sup["pack"]))
        return "Minimum order quantity is %d units per line." % sup["min_qty"]
    if variant == 1:
        base = ("No line may be ordered below a floor of %d units" % sup["min_qty"])
        if sup["pack"] > 1:
            base += (", and quantities are packed %d to a carton -- round any partial carton up"
                     % sup["pack"])
        return base + "."
    base = ("This agreement will not process a line quantity under %d units." % sup["min_qty"])
    if sup["pack"] > 1:
        base += (" Carton size is %d units; orders not landing on a carton multiple are rounded "
                 "up by the supplier before shipment." % sup["pack"])
    return base


def _lead_time_clause(sup, rng):
    variant = rng.choice([0, 1])
    if variant == 0:
        return ("Quoted lead time is %d business days from purchase-order receipt to ship date; "
                "requested ship windows shorter than this are not feasible without an expedite "
                "agreement, which this contract does not grant." % sup["lead_time_days"])
    return ("The supplier requires %d business days between receiving a purchase order and "
            "releasing it for shipment. A shorter requested window cannot be met under the "
            "standing terms of this agreement." % sup["lead_time_days"])


def _ship_to_clause(sup, rng):
    variant = rng.choice([0, 1])
    if variant == 0:
        return ("Approved ship-to regions under this agreement: %s. Shipments outside this list "
                "fall outside the supplier's standing distribution network."
                % ", ".join(sup["regions"]))
    return ("This agreement's distribution network covers the following regions only: %s. A "
            "destination outside that list is not served under these terms."
            % ", ".join(sup["regions"]))


def _value_band_clause(sup, rng):
    lo, hi = sup["value_band"]
    variant = rng.choice([0, 1])
    if variant == 0:
        return ("Orders under this agreement's standing authorization must total between $%d "
                "and $%d; orders outside this band require a separate approval this agreement "
                "does not cover." % (lo, hi))
    return ("Standing authorization under this contract covers order totals from $%d up to "
            "$%d. A total outside that range needs a separate sign-off not granted here."
            % (lo, hi))


def agreement_text(sup, rng):
    """Render the supplier's facts as a prose agreement. Both the PHRASING of each clause (picked
    from several hand-written variants) and the ORDER the clauses appear in are randomised per
    supplier, so a checker cannot key off a fixed sentence template or a fixed position — it has
    to find the number regardless of how the sentence says it or where it sits. This is the whole
    reason evals/baseline.py, which is regex against one fixed template, is the honest free floor
    and not a competitor."""
    header = ["SUPPLIER AGREEMENT", "%s (%s)" % (sup["name"], sup["id"]), "",
              _cost_paragraph(sup, rng)]
    body = [_min_qty_clause(sup, rng), _lead_time_clause(sup, rng)]
    if sup["regions"]:
        body.append(_ship_to_clause(sup, rng))
    body.append("Payment terms are %s." % sup["terms"])
    if sup["value_band"]:
        body.append(_value_band_clause(sup, rng))
    rng.shuffle(body)
    return "\n\n".join(header + body) + "\n"


def _line_cost(sup, sku, verdict, rng):
    true_cost = sup["skus"][sku]
    if verdict == "clean":
        return true_cost
    return round(true_cost + rng.choice([-1, 1]) * rng.uniform(0.25, 3.50), 2)


def _line_qty(sup, verdict, rng):
    if verdict == "clean":
        base = sup["min_qty"] + rng.choice([0, sup["pack"], sup["pack"] * 2])
        return base
    return max(1, sup["min_qty"] - rng.randint(5, sup["min_qty"] // 2 or 1))


def _ship_days(sup, verdict, rng):
    if verdict == "clean":
        return sup["lead_time_days"] + rng.randint(0, 10)
    return max(1, sup["lead_time_days"] - rng.randint(1, sup["lead_time_days"] - 1 or 1))


def _ship_to(sup, verdict, rng):
    if sup["regions"] is None:
        return rng.choice(REGIONS)                        # nothing to violate; check is n/a
    if verdict == "clean":
        return rng.choice(sup["regions"])
    outside = [r for r in REGIONS if r not in sup["regions"]]
    return rng.choice(outside) if outside else rng.choice(REGIONS)


def build_orders(suppliers, rng, n_per_supplier=6):
    """Each supplier gets N orders. One order per supplier is fully clean; the rest each carry
    exactly one planted defect (round-robined across the five checks) so per-check accuracy is
    measurable and not dominated by orders that are wrong everywhere at once. A supplier whose
    agreement omits a field (no `regions`, no `value_band`) yields `unverifiable` on that
    check for every one of its orders — the omission, not a coin flip, decides it."""
    orders, gold = [], []
    order_i = 0
    for sup in suppliers:
        plan = ["clean"] + [CHECKS[k % len(CHECKS)] for k in range(n_per_supplier - 1)]
        for defect_check in plan:
            order_i += 1
            order_id = "ORD-%05d" % order_i
            sku_list = sorted(sup["skus"])
            n_lines = rng.choice([1, 1, 2])
            lines = []
            line_verdicts = []
            for li in range(n_lines):
                sku = rng.choice(sku_list)
                is_defect_line = (defect_check == "cost") and (li == 0)
                cost_v = "defect" if is_defect_line else "clean"
                qty_v = "defect" if (defect_check == "min_qty" and li == 0) else "clean"
                cost = _line_cost(sup, sku, cost_v, rng)
                qty = _line_qty(sup, qty_v, rng)
                lines.append({"sku": sku, "qty": qty, "unit_cost": cost})
                line_verdicts.append({"sku": sku, "cost_verdict": cost_v, "qty_verdict": qty_v})

            lt_v = "defect" if defect_check == "lead_time" else "clean"
            ship_days = _ship_days(sup, lt_v, rng)

            st_v = "unverifiable" if sup["regions"] is None else (
                "defect" if defect_check == "ship_to" else "clean")
            ship_to = _ship_to(sup, "defect" if defect_check == "ship_to" else "clean", rng)

            total = sum(l["unit_cost"] * l["qty"] for l in lines)
            if sup["value_band"] is None:
                ov_v = "unverifiable"
            elif defect_check == "order_value":
                lo, hi = sup["value_band"]
                total = (lo - rng.uniform(50, 200)) if rng.random() < 0.5 else (hi + rng.uniform(500, 5000))
                total = round(max(total, 1.0), 2)
                ov_v = "defect"
            else:
                ov_v = "clean"

            any_cost_defect = any(lv["cost_verdict"] == "defect" for lv in line_verdicts)
            any_qty_defect = any(lv["qty_verdict"] == "defect" for lv in line_verdicts)

            order = {
                "order_id": order_id, "supplier_id": sup["id"], "lines": lines,
                "requested_ship_days": ship_days, "ship_to": ship_to,
                "terms": sup["terms"] if defect_check != "clean" or rng.random() > 0.15
                else rng.choice([t for t in TERMS if t != sup["terms"]]),
                "total_value": round(total, 2),
            }
            checks = {
                "cost": "defect" if any_cost_defect else "clean",
                "min_qty": "defect" if any_qty_defect else "clean",
                "lead_time": lt_v,
                "ship_to": st_v,
                "order_value": ov_v,
            }
            overall = ("defects_flagged" if "defect" in checks.values() else
                       "unverifiable" if "unverifiable" in checks.values() else "clean")
            orders.append(order)
            gold.append({"order_id": order_id, "supplier_id": sup["id"], "checks": checks,
                         "overall": overall, "line_verdicts": line_verdicts})
    return orders, gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-supplier", type=int, default=6)
    args = ap.parse_args()

    rng = random.Random(SEED)
    suppliers = build_suppliers(rng)

    agr_dir = os.path.join(DATA, "agreements")
    os.makedirs(agr_dir, exist_ok=True)
    sup_index = []
    for sup in suppliers:
        text = agreement_text(sup, rng)
        with open(os.path.join(agr_dir, sup["id"] + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)
        sup_index.append({"id": sup["id"], "name": sup["name"], "skus": sorted(sup["skus"]),
                          "has_regions": sup["regions"] is not None,
                          "has_value_band": sup["value_band"] is not None})
    with open(os.path.join(DATA, "suppliers.json"), "w", encoding="utf-8") as fh:
        json.dump(sup_index, fh, indent=2)

    orders, gold = build_orders(suppliers, rng, n_per_supplier=args.per_supplier)
    with open(os.path.join(DATA, "orders.jsonl"), "w", encoding="utf-8") as fh:
        for o in orders:
            fh.write(json.dumps(o) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")

    tally = {}
    for g in gold:
        tally[g["overall"]] = tally.get(g["overall"], 0) + 1
    print("suppliers: %d   orders: %d   agreements: %s" % (
        len(suppliers), len(orders), os.path.join("data", "agreements")))
    print("overall verdict tally:", tally)
    per_check = {c: {} for c in CHECKS}
    for g in gold:
        for c in CHECKS:
            v = g["checks"][c]
            per_check[c][v] = per_check[c].get(v, 0) + 1
    for c in CHECKS:
        print("  %-12s %s" % (c, per_check[c]))


if __name__ == "__main__":
    main()
