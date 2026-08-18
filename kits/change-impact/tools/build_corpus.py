#!/usr/bin/env python3
"""Generate the structured records and the correspondence that requests changes to them, from a
fixed seed.

    python3 tools/build_corpus.py

Writes data/vendors.json, data/records.jsonl, data/messages.jsonl and data/gold.jsonl,
byte-identical on every run. Nothing is fetched and nothing is licensed from anybody: every
vendor, SKU and message here is invented, so the corpus ships under this repo's MIT licence and
there is no third-party grant to verify.

⚑ WHY THE RECORDS AND CORRESPONDENCE ARE INVENTED. A real "change requested by email" always names
a real counterparty and a real commercial number -- exactly the material nobody lets sit in a
public repo under an MIT licence. A synthetic set is the only kind of this corpus that can be
re-run by a stranger with a clone and no NDA to sign. See data/SOURCES.md.

⚑ THE SCENARIO IS FLAVOURED, THE JOB IS NOT. This kit generically extracts a requested change from
unstructured correspondence, matches it to the specific record it modifies, and computes the
downstream impact of accepting it. The corpus below happens to flavour "record" as a purchase-order
line and "correspondence" as a vendor email, because that is a concrete, checkable instance of the
job -- not because the job is about purchase orders. Point tools/build_corpus.py at your own record
shape and your own correspondence and the pipeline does not change.

⚑ THREE MATCH OUTCOMES, EACH PLANTED ON PURPOSE.
    a specific record id        the message names or clearly implies exactly one open record
    NONE                        the message's own vendor+product has no open record at all --
                                the record was already closed, or never existed
    genuinely ambiguous         more than one open record shares the vendor and product; the
                                message states a hint (the ORIGINAL value of a field the change
                                does not touch) that disambiguates the candidates -- if you read
                                the hint. A checker that ignores it cannot solve these.

⚑ FIVE CHANGE TYPES, EACH WITH A DETERMINISTIC IMPACT FORMULA. See src/impact.py -- the number a
model or a baseline is scored against is never asserted here, it is computed from the same record
and the same extracted change value that produced the correspondence in the first place.
"""
import argparse
import datetime
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
SEED = 20260818                              # fixed. change it and every downstream file changes.
BASE_DATE = datetime.date(2026, 9, 1)         # the "today" every relative date in this corpus is anchored to

VENDOR_NAMES = [
    "Halberd Fastening Co", "Marrow Fabrication", "Sable Ridge Supply", "Corrigan Metalworks",
    "Ferndale Components", "Vesper Industrial", "Loxley Hardware Group", "Alder & Finch Supply",
    "Brackwater Trading", "Emberline Materials",
]
REGIONS = ["NA-EAST", "NA-WEST", "NA-CENTRAL", "EU-NORTH", "EU-SOUTH", "APAC-EAST"]
CHANGE_TYPES = ("expedite", "delay", "cancel", "qty_change", "price_change")

# Three products per vendor. The third is deliberately given NO open records at all -- any message
# about it is an orphan by construction, not a coin flip.
PRODUCT_POOL = [
    ("hex bolts", 14.0), ("steel brackets", 22.0), ("cable reels", 61.0), ("foam gaskets", 4.5),
    ("ball bearings", 9.0), ("aluminium channel", 33.0), ("rubber grommets", 2.25),
    ("threaded rod", 18.0), ("welding rod", 27.0), ("conveyor rollers", 74.0),
    ("safety hinges", 11.0), ("wire mesh panels", 48.0), ("epoxy sealant", 16.0),
    ("anchor plates", 39.0), ("compression springs", 6.5), ("pipe clamps", 8.0),
    ("insulated sleeving", 12.0), ("torque limiters", 91.0), ("shock mounts", 29.0),
    ("drive couplings", 55.0), ("filter cartridges", 21.0), ("pressure gauges", 44.0),
    ("gate valves", 88.0), ("union fittings", 13.5), ("cotter pins", 1.75),
    ("lock washers", 1.4), ("strut channel", 24.0), ("cam followers", 37.0),
    ("shear pins", 3.2), ("split collars", 7.8),
]


def _vendor_id(i):
    return "VEN-%04d" % (100 + i)


def _sku(vendor_i, prod_i):
    return "SKU-%02d%02d" % (vendor_i + 10, prod_i)


def _record_id(n):
    return "REC-%05d" % n


def build_vendors(rng):
    """Each vendor gets three products: two carry open records and are eligible to be matched,
    the third carries none at all -- any correspondence about it is a genuine orphan, not a
    hypothetical."""
    vendors = []
    pool = list(PRODUCT_POOL)
    rng.shuffle(pool)
    for i, name in enumerate(VENDOR_NAMES):
        products = pool[i * 3:(i * 3) + 3]
        skus = []
        for j, (desc, base_cost) in enumerate(products):
            skus.append({"sku": _sku(i, j), "description": desc,
                        "base_cost": round(base_cost * rng.uniform(0.85, 1.2), 2)})
        vendors.append({"id": _vendor_id(i), "name": name,
                        "open_skus": skus[:2], "closed_sku": skus[2]})
    return vendors


def build_records(vendors, rng):
    """2-3 open records per open SKU, spread across a ~90-day window so date does real work as a
    disambiguator. ~45% of records carry a live promotion, which is what gives `delay` its real
    cost beyond a flat accessorial -- missing the promo window loses the whole promo value, not a
    per-day fee."""
    records, by_vendor_sku = [], {}
    n = 0
    for v in vendors:
        for sku in v["open_skus"]:
            n_recs = rng.choice([2, 2, 3])
            key = (v["id"], sku["sku"])
            by_vendor_sku[key] = []
            for _k in range(n_recs):
                n += 1
                rid = _record_id(n)
                qty = rng.choice([20, 40, 60, 100, 150, 200, 250, 320, 400])
                unit_cost = round(sku["base_cost"] * rng.uniform(0.95, 1.05), 2)
                ship_offset = rng.randint(-20, 70)
                ship_date = BASE_DATE + datetime.timedelta(days=ship_offset)
                has_promo = rng.random() < 0.45
                promo_start = promo_end = promo_value = None
                if has_promo:
                    promo_start = ship_date - datetime.timedelta(days=rng.randint(5, 12))
                    promo_end = ship_date + datetime.timedelta(days=rng.randint(3, 15))
                    promo_value = round(rng.uniform(600, 6500), 2)
                rec = {
                    "record_id": rid, "vendor_id": v["id"], "sku": sku["sku"],
                    "description": sku["description"], "qty": qty, "unit_cost": unit_cost,
                    "ship_date": ship_date.isoformat(), "ship_to": rng.choice(REGIONS),
                    "promo_start": promo_start.isoformat() if promo_start else None,
                    "promo_end": promo_end.isoformat() if promo_end else None,
                    "promo_value_usd": promo_value, "status": "open",
                }
                records.append(rec)
                by_vendor_sku[key].append(rec)
    return records, by_vendor_sku


# ---------------------------------------------------------------------------------------------
# Message text -- phrasing varied per change type so a fixed pattern cannot cover every message.

def _product_ref(sku, rng, explicit_sku_bias):
    """A product is referenced either by its SKU code or by its plain-English description --
    varied per message so a checker keyed to one form misses the other."""
    if rng.random() < explicit_sku_bias:
        return sku["sku"]
    return sku["description"]


def _date_phrase(d):
    return d.strftime("%B %-d") if os.name != "nt" else d.strftime("%B %d").replace(" 0", " ")


def _expedite_text(rec, new_date, ref, recid_line, hint):
    variant = 0  # kept deterministic per-call by caller's rng choice below
    templates = [
        "Hi -- following up on the %s order. Any chance you can pull the ship date forward to "
        "%s? We're short on the floor and need it sooner than planned.%s%s" % (
            ref, _date_phrase(new_date), recid_line, hint),
        "We need to expedite the %s shipment. Please move the ship date up to %s if at all "
        "possible -- happy to cover a reasonable rush fee.%s%s" % (
            ref, _date_phrase(new_date), recid_line, hint),
        "Can you get the %s order out earlier than scheduled? %s is the date we actually need "
        "it by.%s%s" % (ref, _date_phrase(new_date), recid_line, hint),
    ]
    return templates


def _delay_text(rec, new_date, ref, recid_line, hint):
    return [
        "Please hold the %s shipment -- our dock isn't ready. Push the ship date to %s "
        "instead.%s%s" % (ref, _date_phrase(new_date), recid_line, hint),
        "We won't be able to receive the %s order on the current schedule. Can you reschedule "
        "shipment for %s?%s%s" % (ref, _date_phrase(new_date), recid_line, hint),
        "Requesting a delay on the %s order -- new ship date of %s, please.%s%s" % (
            ref, _date_phrase(new_date), recid_line, hint),
    ]


def _cancel_text(rec, ref, recid_line, hint):
    return [
        "Please cancel the %s order entirely -- our requirements changed and we no longer need "
        "it.%s%s" % (ref, recid_line, hint),
        "We need to cancel the %s line. No replacement order planned at this time.%s%s" % (
            ref, recid_line, hint),
        "Cancel request: the %s order should be pulled entirely, effective immediately.%s%s" % (
            ref, recid_line, hint),
    ]


def _qty_text(rec, new_qty, ref, recid_line, hint):
    return [
        "Please adjust the %s order to %d units instead of what's currently on file.%s%s" % (
            ref, new_qty, recid_line, hint),
        "We'd like to change the quantity on the %s order to %d units.%s%s" % (
            ref, new_qty, recid_line, hint),
        "Requesting a quantity change on the %s line -- %d units going forward.%s%s" % (
            ref, new_qty, recid_line, hint),
    ]


def _price_text(rec, new_cost, ref, recid_line, hint):
    return [
        "We need to revisit pricing on the %s order -- $%.2f per unit going forward.%s%s" % (
            ref, new_cost, recid_line, hint),
        "Effective this order, unit cost on %s should be $%.2f, not what's currently quoted.%s%s" % (
            ref, new_cost, recid_line, hint),
        "Pricing update for the %s line: new unit cost is $%.2f.%s%s" % (
            ref, new_cost, recid_line, hint),
    ]


def _orphan_text(sku, rng):
    templates = [
        "Checking in on the %s order -- can you confirm the current ship date? We may need to "
        "adjust it." % sku["description"],
        "Any update on our %s order? We're considering a quantity change depending on timing." %
        sku["description"],
        "Following up on %s -- please expedite if the order is still open." % sku["sku"],
    ]
    return rng.choice(templates)


def _hint_for(rec, change_type, rng):
    """The disambiguating clue: the ORIGINAL value of a field the change does NOT touch. Only
    used when more than one open record shares this vendor+product and the message carries no
    explicit record id -- otherwise there would be nothing to disambiguate and nothing to hint
    at."""
    if change_type in ("expedite", "delay"):
        return " (currently at %d units on our records.)" % rec["qty"]
    return " (currently scheduled to ship %s.)" % _date_phrase(
        datetime.date.fromisoformat(rec["ship_date"]))


def build_messages(vendors, by_vendor_sku, rng, per_vendor=7):
    messages, gold = [], []
    m_i = 0
    ct_cycle = list(CHANGE_TYPES)
    ct_idx = 0
    for v in vendors:
        for k in range(per_vendor):
            m_i += 1
            mid = "MSG-%05d" % m_i
            is_orphan = (k == 0)
            explicit_sku_bias = rng.choice([0.3, 0.5, 0.7])

            if is_orphan:
                sku = v["closed_sku"]
                text = _orphan_text(sku, rng)
                messages.append({"message_id": mid, "vendor_id": v["id"], "text": text})
                gold.append({"message_id": mid, "vendor_id": v["id"],
                            "matched_record_id": "NONE", "change_type": None,
                            "new_value": None, "impact": None, "decision": None,
                            "candidates_expected": 0, "note": "orphan -- no open record for this product"})
                continue

            sku = v["open_skus"][k % 2]
            recs = by_vendor_sku[(v["id"], sku["sku"])]
            rec = rng.choice(recs)
            change_type = ct_cycle[ct_idx % len(ct_cycle)]
            ct_idx += 1

            explicit_recid = rng.random() < 0.55
            recid_line = " (PO reference %s.)" % rec["record_id"] if explicit_recid else ""
            ambiguous = (not explicit_recid) and len(recs) > 1
            hint = _hint_for(rec, change_type, rng) if ambiguous else ""
            ref = _product_ref(sku, rng, explicit_sku_bias)

            new_value = None
            if change_type == "expedite":
                pull = rng.randint(3, 14)
                new_date = datetime.date.fromisoformat(rec["ship_date"]) - datetime.timedelta(days=pull)
                text = rng.choice(_expedite_text(rec, new_date, ref, recid_line, hint))
                new_value = {"new_ship_date": new_date.isoformat()}
            elif change_type == "delay":
                push = rng.randint(5, 30)
                new_date = datetime.date.fromisoformat(rec["ship_date"]) + datetime.timedelta(days=push)
                text = rng.choice(_delay_text(rec, new_date, ref, recid_line, hint))
                new_value = {"new_ship_date": new_date.isoformat()}
            elif change_type == "cancel":
                text = rng.choice(_cancel_text(rec, ref, recid_line, hint))
                new_value = None
            elif change_type == "qty_change":
                delta = rng.choice([d for d in range(-80, 121, 10) if d != 0])
                new_qty = max(1, rec["qty"] + delta)
                text = rng.choice(_qty_text(rec, new_qty, ref, recid_line, hint))
                new_value = {"new_qty": new_qty}
            else:  # price_change
                delta = round(rng.choice([-1, 1]) * rng.uniform(0.5, 4.0), 2)
                new_cost = round(max(0.10, rec["unit_cost"] + delta), 2)
                text = rng.choice(_price_text(rec, new_cost, ref, recid_line, hint))
                new_value = {"new_unit_cost": new_cost}

            messages.append({"message_id": mid, "vendor_id": v["id"], "text": text})
            gold.append({"message_id": mid, "vendor_id": v["id"],
                        "matched_record_id": rec["record_id"], "change_type": change_type,
                        "new_value": new_value, "candidates_expected": len(recs) if not explicit_recid else 1,
                        "ambiguous": ambiguous, "explicit_recid": explicit_recid})
    return messages, gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-vendor", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(SEED)
    vendors = build_vendors(rng)
    records, by_vendor_sku = build_records(vendors, rng)
    messages, gold = build_messages(vendors, by_vendor_sku, rng, per_vendor=args.per_vendor)

    # impact is computed after gold is built, by the same formulas the pipeline uses -- imported
    # rather than re-derived, so the label can never drift from what src/impact.py will compute.
    import sys
    sys.path.insert(0, HERE)
    from src import impact as I  # noqa: E402

    by_id = {r["record_id"]: r for r in records}
    for g in gold:
        if g["matched_record_id"] == "NONE":
            continue
        rec = by_id[g["matched_record_id"]]
        imp = I.compute(rec, g["change_type"], g["new_value"])
        g["impact"] = imp
        g["decision"] = I.decide(imp)

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "vendors.json"), "w", encoding="utf-8") as f:
        json.dump(vendors, f, indent=2)
    with open(os.path.join(DATA, "records.jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(DATA, "messages.jsonl"), "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g) + "\n")

    tally = {}
    for g in gold:
        tally[g["change_type"]] = tally.get(g["change_type"], 0) + 1
    n_orphan = sum(1 for g in gold if g["matched_record_id"] == "NONE")
    n_ambig = sum(1 for g in gold if g.get("ambiguous"))
    print("vendors: %d   records: %d   messages: %d" % (len(vendors), len(records), len(messages)))
    print("change types:", tally)
    print("orphan (no open record): %d   ambiguous (>1 candidate, no recid): %d"
          % (n_orphan, n_ambig))


if __name__ == "__main__":
    main()
