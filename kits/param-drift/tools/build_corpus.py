#!/usr/bin/env python3
"""Generate the whole corpus from a fixed seed. No network, no third-party data.

    python3 tools/build_corpus.py

Writes data/parameters.jsonl (the configured value per parameter), data/readings.csv (the raw
rolling-window observations -- the "sample events" this kit's flow starts from) and
data/labelled.jsonl (the gold drift/no-drift label plus, where the gold label is `drift`, the
corrected value a historical analyst actually approved).

⚑ THE GOLD CORRECTED VALUE IS NEVER COMPUTED BY THE SAME FORMULA THE PIPELINE USES. It would be
easy to import src/formulas.py here and let it label its own homework -- and it would make
"value agreement" measure nothing, because the pipeline's formula would score 100% against itself
by construction. Instead this generator decides a TRUE underlying value at generation time (known
here, and only here) and then SAMPLES the window readings around it with realistic noise. The
gold corrected value is the true value; the pipeline's proposed value is computed later, by
`src/formulas.py`, from the noisy OBSERVED window alone -- so how close the two land is a real,
measured question, not a tautology.

THREE CATEGORIES, the "configured value vs observed behaviour" triad this kit's atlas row names:

    lead_time       a configured duration vs the receipt lag actually observed
    safety_margin   a configured buffer vs the variability actually observed (z * std, z=1.65,
                    an assumed 95%-service constant -- see src/formulas.py's own note)
    service_target  a configured rate/threshold vs the rate actually achieved

FOUR SCENARIOS ("traps") PER CATEGORY, planted so the free floor and a real judgement call are
worth telling apart -- same discipline ops-triage's six traps and change-impact's ambiguous
messages both exist for:

    clean_drift     a real, sustained mismatch. Easy: both the floor and a careful reader should
                    catch it.
    clean_hold      configured value already matches observed behaviour. Easy the other way.
    one_off_spike   ONE anomalous reading, logged with a one-time-event note, in an otherwise
                    matched window. A naive mean/std threshold can be fooled into flagging it; the
                    note is the evidence a reader needs to hold instead.
    slow_creep      a steady, one-directional drift across the whole window that ends well away
                    from configured but keeps the whole-window average looking mild. The floor
                    reads only the average; the trend (first-half vs second-half mean, computed
                    and stated as a fact) is what lets a reader catch it before the floor does.

Every number below is stated once, here, not fitted to the corpus after the fact -- same
discipline as change-impact's MATERIALITY_THRESHOLD_USD.
"""
import csv
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

SEED = 20260818
WINDOW_PERIODS = 10
Z_SAFETY = 1.65          # kept in step with src/formulas.py::Z_SAFETY -- see its own header

CATEGORIES = ("lead_time", "safety_margin", "service_target")
TRAPS = ("clean_drift", "clean_hold", "one_off_spike", "slow_creep")
# How many of each trap, per category. 5+7+4+4 = 20 per category x 3 = 60 parameters total.
TRAP_COUNTS = {"clean_drift": 5, "clean_hold": 7, "one_off_spike": 4, "slow_creep": 4}

SUPPLIERS = ["Halden Freight", "Marrow Logistics", "Coastal Intermodal", "Ferrous & Kite",
             "Nordbridge Carriers", "Amaranth Line", "Quillon Transit", "Basalt Fleet Co"]
SITES = ["DC-North", "DC-Bayview", "DC-Prairie", "DC-Highland", "DC-Delta", "DC-Summit",
         "DC-Coldwater", "DC-Ashgrove"]
CHANNELS = ["Storefront", "Marketplace-A", "Marketplace-B", "Wholesale", "Direct-Ship",
            "Kiosk Network", "Partner Portal", "Regional Retail"]

ONE_OFF_NOTES = {
    "lead_time": "logged note: one-time carrier disruption, resolved by the next cycle",
    "safety_margin": "logged note: one-time promotional demand surge, not repeated",
    "service_target": "logged note: one-time platform outage, resolved same day",
}


def _clip(v, lo):
    return v if v >= lo else lo


def _series_lead_time(rng, trap, configured):
    """Returns (values, label, gold, note_idx). Unit: days."""
    if trap == "clean_drift":
        pct = rng.uniform(0.35, 0.60) * rng.choice((1, -1))
        true_now = _clip(configured * (1 + pct), 1.0)
        sigma = max(0.3, true_now * 0.08)
        vals = [rng.gauss(true_now, sigma) for _ in range(WINDOW_PERIODS)]
        return vals, "drift", round(true_now, 1), None
    if trap == "clean_hold":
        true_now = configured * rng.uniform(0.95, 1.05)
        sigma = max(0.25, true_now * 0.07)
        vals = [rng.gauss(true_now, sigma) for _ in range(WINDOW_PERIODS)]
        return vals, "no_drift", None, None
    if trap == "one_off_spike":
        true_now = configured * rng.uniform(0.95, 1.05)
        sigma = max(0.25, true_now * 0.07)
        vals = [rng.gauss(true_now, sigma) for _ in range(WINDOW_PERIODS)]
        idx = rng.randint(3, 7)
        vals[idx] = true_now * rng.uniform(3.0, 4.5)          # one very long delay
        return vals, "no_drift", None, idx
    if trap == "slow_creep":
        start = configured * rng.uniform(0.95, 1.05)
        end_pct = rng.uniform(0.35, 0.55) * rng.choice((1, -1))
        end = _clip(configured * (1 + end_pct), 1.0)
        sigma = max(0.25, ((start + end) / 2) * 0.06)
        vals = [rng.gauss(start + (end - start) * i / (WINDOW_PERIODS - 1), sigma)
                for i in range(WINDOW_PERIODS)]
        return vals, "drift", round(end, 1), None
    raise ValueError(trap)


def _series_safety_margin(rng, trap, configured, base_demand):
    """Returns (values, label, gold, note_idx). `values` are per-period DEMAND readings (units);
    the parameter itself is the configured BUFFER, and drift is judged on required = Z*std(demand),
    never on the demand readings directly."""
    if trap == "clean_drift":
        pct = rng.uniform(0.50, 0.80) * rng.choice((1, -1))
        required = _clip(configured * (1 + pct), 1.0)
        true_std = required / Z_SAFETY
        vals = [_clip(rng.gauss(base_demand, true_std), 0.0) for _ in range(WINDOW_PERIODS)]
        return vals, "drift", round(required, 1), None
    if trap == "clean_hold":
        true_std = (configured / Z_SAFETY) * rng.uniform(0.97, 1.03)
        vals = [_clip(rng.gauss(base_demand, true_std), 0.0) for _ in range(WINDOW_PERIODS)]
        return vals, "no_drift", None, None
    if trap == "one_off_spike":
        true_std = (configured / Z_SAFETY) * rng.uniform(0.97, 1.03)
        vals = [_clip(rng.gauss(base_demand, true_std), 0.0) for _ in range(WINDOW_PERIODS)]
        idx = rng.randint(3, 7)
        vals[idx] = base_demand + rng.uniform(4.0, 6.0) * true_std
        return vals, "no_drift", None, idx
    if trap == "slow_creep":
        start_std = (configured / Z_SAFETY) * rng.uniform(0.97, 1.03)
        end_pct = rng.uniform(0.50, 0.80) * rng.choice((1, -1))
        end_required = _clip(configured * (1 + end_pct), 1.0)
        end_std = end_required / Z_SAFETY
        vals = [_clip(rng.gauss(base_demand, start_std + (end_std - start_std) * i / (WINDOW_PERIODS - 1)),
                      0.0)
                for i in range(WINDOW_PERIODS)]
        return vals, "drift", round(end_required, 1), None
    raise ValueError(trap)


def _series_service_target(rng, trap, configured):
    """Returns (values, label, gold, note_idx). Unit: percentage points, clipped to [50, 100]."""
    if trap == "clean_drift":
        pts = rng.uniform(4.0, 9.0) * rng.choice((1, -1))
        true_now = min(100.0, max(50.0, configured + pts))
        sigma = rng.uniform(1.0, 1.5)
        vals = [min(100.0, max(50.0, rng.gauss(true_now, sigma))) for _ in range(WINDOW_PERIODS)]
        return vals, "drift", round(true_now, 1), None
    if trap == "clean_hold":
        true_now = configured + rng.uniform(-1.0, 1.0)
        sigma = rng.uniform(0.8, 1.3)
        vals = [min(100.0, max(50.0, rng.gauss(true_now, sigma))) for _ in range(WINDOW_PERIODS)]
        return vals, "no_drift", None, None
    if trap == "one_off_spike":
        true_now = configured + rng.uniform(-1.0, 1.0)
        sigma = rng.uniform(0.8, 1.3)
        vals = [min(100.0, max(50.0, rng.gauss(true_now, sigma))) for _ in range(WINDOW_PERIODS)]
        idx = rng.randint(3, 7)
        vals[idx] = max(50.0, true_now - rng.uniform(22.0, 32.0))
        return vals, "no_drift", None, idx
    if trap == "slow_creep":
        start = configured + rng.uniform(-1.0, 1.0)
        pts = rng.uniform(4.0, 9.0) * rng.choice((1, -1))
        end = min(100.0, max(50.0, configured + pts))
        sigma = rng.uniform(0.8, 1.3)
        vals = [min(100.0, max(50.0, rng.gauss(start + (end - start) * i / (WINDOW_PERIODS - 1), sigma)))
                for i in range(WINDOW_PERIODS)]
        return vals, "drift", round(end, 1), None
    raise ValueError(trap)


def build():
    rng = random.Random(SEED)
    parameters, readings, labels = [], [], []
    n = 0
    for category in CATEGORIES:
        for trap in TRAPS:
            for _ in range(TRAP_COUNTS[trap]):
                n += 1
                pid = "PD-%04d" % n
                sku = rng.randint(10000, 99999)
                if category == "lead_time":
                    configured = rng.randint(3, 15)
                    entity = "Lead time -- %s, SKU %05d" % (rng.choice(SUPPLIERS), sku)
                    unit = "days"
                    vals, label, gold, note_idx = _series_lead_time(rng, trap, configured)
                elif category == "safety_margin":
                    configured = rng.randint(20, 120)
                    base_demand = rng.randint(40, 150)
                    entity = "Safety margin -- %s, SKU %05d" % (rng.choice(SITES), sku)
                    unit = "units"
                    vals, label, gold, note_idx = _series_safety_margin(rng, trap, configured, base_demand)
                else:
                    configured = rng.choice([90, 92, 94, 95, 96, 97, 98, 99])
                    entity = "Service target -- %s, SKU %05d" % (rng.choice(CHANNELS), sku)
                    unit = "pct"
                    vals, label, gold, note_idx = _series_service_target(rng, trap, configured)

                round_to = 0 if category == "safety_margin" else 1
                vals = [round(v, round_to) for v in vals]
                parameters.append({"parameter_id": pid, "category": category, "entity": entity,
                                   "configured_value": configured, "unit": unit,
                                   "window_periods": WINDOW_PERIODS})
                for i, v in enumerate(vals):
                    note = ONE_OFF_NOTES[category] if i == note_idx else None
                    readings.append({"parameter_id": pid, "period_index": i,
                                     "period_label": "t-%d" % (WINDOW_PERIODS - 1 - i),
                                     "observed": v, "note": note})
                labels.append({"parameter_id": pid, "label": label, "trap": trap,
                              "gold_corrected_value": gold})

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "parameters.jsonl"), "w", encoding="utf-8") as f:
        for p in parameters:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "labelled.jsonl"), "w", encoding="utf-8") as f:
        for l in labels:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "readings.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["parameter_id", "period_index", "period_label",
                                          "observed", "note"])
        w.writeheader()
        for r in readings:
            w.writerow(r)

    print("parameters : %d  (%d per category x %d categories)"
          % (len(parameters), len(parameters) // len(CATEGORIES), len(CATEGORIES)))
    print("readings   : %d  (%d periods each)" % (len(readings), WINDOW_PERIODS))
    n_drift = sum(1 for l in labels if l["label"] == "drift")
    print("labels     : %d drift, %d no_drift" % (n_drift, len(labels) - n_drift))
    for trap in TRAPS:
        print("  trap %-14s x%d" % (trap, TRAP_COUNTS[trap] * len(CATEGORIES)))
    print("-> data/parameters.jsonl, data/readings.csv, data/labelled.jsonl")


if __name__ == "__main__":
    build()
