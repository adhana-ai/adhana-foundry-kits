#!/usr/bin/env python3
"""Generate the allocation review sessions, their shortage events, per-store facts, merchant
context log and the gold flag/cause list, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/sessions.jsonl, data/notes.jsonl and data/gold.jsonl, byte-identical on every run.
Nothing is fetched and nothing is licensed from anybody: every session, store and note line here
is invented, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ WHY THE WRITTEN POLICY IS INVENTED TOO, AND STATED AS SUCH. The originating atlas row's own
open item says it plainly: "no written allocation policy exists; atlas premise requires an
operator-supplied written policy before build." There is no operator-supplied policy to encode, so
this kit ships one -- data/POLICY.md, five numbered clauses -- authored by us for this corpus, the
same move docs-apply's build_corpus.py makes for its policy documents. It is not a claim about
what any real retailer's policy says.

⚑ CODE DECIDES *THAT* AN EVENT NEEDS REVIEW; THE MODEL DECIDES *WHY*, FROM UNSTRUCTURED CONTEXT
-- same split gap-brief's build_corpus.py states for materiality vs. cause. src/allocate.py runs
the five-clause policy formula in pure arithmetic and flags an event the moment promo protection
plus customer-commitment protection alone cannot both be honored within available units, or the
equity floor cannot be met even before those two protections are applied. That flag is a fact
about the numbers. WHY it happened -- whose process broke -- is not in the numbers; it is in the
session's own merchant notes log, which is what the model reads.

⚑ FIVE SCENARIOS, EACH PLANTED ON PURPOSE -- same discipline gap-brief's build_corpus.py states
for its own seven:

    clean               promo + customer commitments fit inside available units with room for a
                         feasible fair-share on the remainder. Not flagged.
    promo_overcommit     merchandising promised promo units to more stores than the DC can supply
                         for this SKU -- traceable via two notes lines.
    customer_overcommit  store reps took customer pre-orders beyond what the system had reserved --
                         traceable via two notes lines.
    demand_surge         nobody over-promised; a genuine, unplanned velocity spike this week makes
                         the ordinary math infeasible -- traceable via two notes lines.
    supply_shortfall     the DC itself received fewer units than the plan assumed -- traceable via
                         two notes lines.
    unknown_flag         a real, material shortfall -- but the notes do not explain why. Untraceable
                         on purpose, to prove the model says 'unknown' rather than guessing.

⚑ THE PROTECTED-TIER FIELD IS PRESENT AND IS NEVER READ BY THE ALLOCATION FORMULA. Every store
carries a synthetic `trade_area_tier` label (A/B/C) so a reader can audit for disparate impact --
exactly what a real deployment would need to check. src/allocate.py's signature never takes it as
an argument; see evals/scoring.py::parity_check, which proves the correlation is null on every
generated session BY CONSTRUCTION, not by getting lucky on this corpus.

⚑ NOISE LINES ARE PLANTED TOO, SAME DISCIPLINE AS gap-brief. Each session's notes log carries
several lines that name a different event or nothing decision-relevant at all, so a model that
cites "the nearest plausible-looking line" rather than an event-matched one is caught by
evals/scoring.py's citation-fidelity check.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "data")

from src import allocate as A          # noqa: E402

SEED = 20260818                          # fixed. change it and every downstream file changes.

SKUS = [
    "Trailhead Runner Mid", "Summit Shell Jacket", "Camp Stove Compact", "Ridgeline Daypack 28L",
    "Alpine Base Layer Tee", "Basecamp Cookset", "Traverse Hydration Vest", "Northface Rain Poncho",
    "Boulder Approach Shoe", "Glacier Insulated Bottle", "Switchback Trekking Pole", "Frostline Puffy Vest",
]
REGIONS = ["North Region", "South Region", "East Region", "West Region", "Direct-to-Consumer"]
WEEKS = ["2026-W28", "2026-W29", "2026-W30", "2026-W31"]
STORE_IDS = ["ST-%03d" % i for i in range(1, 61)]
TIERS = ["A", "B", "C"]

# Weighted so ~30% of events are clean and the remaining ~70% split across four planted scenarios
# -- heavier on planted conflicts than a real deployment would likely see, on purpose: a corpus
# that is mostly clean teaches a scorer almost nothing about the traceable/untraceable split this
# kit exists to get right.
SCENARIOS = ["clean", "promo_overcommit", "customer_overcommit", "demand_surge", "supply_shortfall",
            "unknown_flag"]
WEIGHTS = [0.30, 0.14, 0.14, 0.14, 0.14, 0.14]

NOISE_LINES = [
    "Reminder: allocation review sign-off is due Thursday EOD this cycle, no exceptions.",
    "Planogram reset for the accessories wall lands next week -- separate meeting, not this one.",
    "New regional merchandiser starts Monday; route urgent items to the deputy until then.",
    "DC dock schedule shifted two hours for the holiday -- see the shared calendar invite.",
    "Vendor scorecard refresh landed in the shared drive, unrelated to this week's allocations.",
    "Please use the new intake form for next cycle's promo requests -- old one is deprecated.",
    "IT ticket open for the allocation tool's export button; workaround is CSV download.",
    "Store ops lead is out next week; escalations go to the district manager instead.",
]


def _ev_id(i):
    return "EV-%04d" % (1 + i)


def _cite_pair(rng, sku, cause, over_amt):
    """Two verbatim notes lines that together explain `cause` for `sku`. Phrasing is templated
    with light variation so a checker cannot key off one fixed sentence -- same discipline
    gap-brief's own citation generator uses."""
    if cause == "promo_overcommit":
        return [
            "%s: merchandising confirmed the promo commitment across all flagged stores adds up "
            "to %d more units than the DC actually has for this week." % (sku, over_amt),
            "Follow-up on %s promo -- the regional promo calendar was built before this week's "
            "supply number was final, so the commitments were never checked against it."
            % sku,
        ]
    if cause == "customer_overcommit":
        return [
            "%s: store ops confirmed reps took customer pre-orders ahead of what the reservation "
            "system actually had on hold -- running about %d units over." % (sku, over_amt),
            "Correction thread on %s -- the pre-order count in the POS doesn't match what "
            "allocation planning reserved; reps were working off last week's number." % sku,
        ]
    if cause == "demand_surge":
        return [
            "%s: sell-through spiked this week well past the trailing-velocity trend -- nothing "
            "on the promo or commitment side changed, it's genuine demand." % sku,
            "Flagging %s -- confirmed with the category lead that the surge is real store-floor "
            "demand, not a data or commitment issue on our side." % sku,
        ]
    if cause == "supply_shortfall":
        return [
            "%s: DC receiving confirmed this week's inbound came in short of the supply plan -- "
            "about %d units under what was expected." % (sku, over_amt),
            "Supply note on %s -- vendor ASN matched the shorted quantity; replenishment plan "
            "assumed the full number and allocation is working off the shortfall." % sku,
        ]
    return []


def build_event(i, rng):
    sku = rng.choice(SKUS)
    n_stores = rng.randint(6, 10)
    stores = rng.sample(STORE_IDS, k=n_stores)
    scenario = rng.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]

    store_rows = []
    for sid in stores:
        ask = rng.randint(20, 90)
        velocity = round(rng.uniform(0.6, 1.6), 2)
        tier = rng.choice(TIERS)
        store_rows.append({
            "store_id": sid, "ask_units": ask, "velocity_weight": velocity,
            "trade_area_tier": tier, "promo_committed_units": 0, "customer_committed_units": 0,
        })

    total_ask = sum(s["ask_units"] for s in store_rows)
    # ⚑ `full_available` IS THE 'NOTHING IS WRONG' BASELINE, SIZED AGAINST THE EQUITY FLOOR, NOT
    # GUESSED. src/allocate.py's clause 3 shares the post-protection pool proportional to each
    # store's own remaining ask, so an ordinary week's coverage ratio (pool / remaining ask,
    # averaged across stores) is what EQUITY_FLOOR_PCT (40%) actually gets compared against.
    # 0.85-0.97 leaves every store safely clear of that floor after a small promo/customer
    # protection carve-out, which tools/selftest_allocate.py's flag-purity check holds this
    # module to on every rebuild -- it is not a number that was fitted after the fact.
    full_available = round(total_ask * rng.uniform(0.85, 0.97))

    # A minority of stores carry a promo commitment or a customer commitment -- each a BOUNDED
    # PORTION of that store's own ask, never the whole ask (see src/allocate.py's 2026-08-18 fix
    # note). A store can carry both; the two are capped so together they never exceed its ask.
    n_promo = rng.randint(1, 3)
    n_cust = rng.randint(1, 3)
    for s in rng.sample(store_rows, k=min(n_promo, len(store_rows))):
        s["promo_committed_units"] = round(s["ask_units"] * rng.uniform(0.35, 0.70))
    for s in rng.sample(store_rows, k=min(n_cust, len(store_rows))):
        cap = s["ask_units"] - s["promo_committed_units"]
        if cap > 4:
            s["customer_committed_units"] = rng.randint(4, min(16, cap))

    over_amt = 0
    available = full_available
    if scenario == "clean":
        pass
    elif scenario == "promo_overcommit":
        # Tests the PROTECTION mechanism directly: shrink supply below what promo alone
        # committed, regardless of the equity-floor baseline above.
        promo_total = sum(s["promo_committed_units"] for s in store_rows)
        over_amt = rng.randint(8, 25)
        available = max(promo_total - over_amt, 5)
    elif scenario == "customer_overcommit":
        cust_total = sum(s["customer_committed_units"] for s in store_rows)
        over_amt = rng.randint(6, 18)
        available = max(cust_total - over_amt, 5)
    elif scenario == "demand_surge":
        available = round(full_available * rng.uniform(0.40, 0.58))
        over_amt = round(total_ask - available)
    elif scenario == "supply_shortfall":
        available = round(full_available * rng.uniform(0.42, 0.60))
        over_amt = round(full_available - available)
    else:  # unknown_flag -- material shortfall, no explanation planted
        available = round(full_available * rng.uniform(0.40, 0.58))
        over_amt = round(total_ask - available)

    event = {
        "event_id": _ev_id(i), "sku": sku, "available_units": int(available),
        "stores": store_rows,
    }
    fx = A.allocate(event)
    true_cause = "unknown" if scenario in ("unknown_flag",) else (
        None if scenario == "clean" else scenario)
    citations = [] if scenario in ("clean", "unknown_flag") else _cite_pair(rng, sku, scenario, over_amt)
    return event, {
        "event_id": event["event_id"], "sku": sku, "scenario": scenario,
        "flagged": fx["flagged"], "true_cause": true_cause, "citations": citations,
    }


def build_session(i, rng):
    session_id = "SESS-%03d" % (i + 1)
    region = rng.choice(REGIONS)
    week = rng.choice(WEEKS)
    n_events = rng.randint(4, 6)

    events, meta = [], []
    for j in range(n_events):
        ev, m = build_event(i * 10 + j, rng)
        events.append(ev)
        meta.append(m)

    notes = []
    for m in meta:
        notes.extend(m["citations"])
    n_noise = rng.randint(3, 5)
    notes.extend(rng.sample(NOISE_LINES, k=min(n_noise, len(NOISE_LINES))))
    rng.shuffle(notes)

    session = {"session_id": session_id, "region": region, "week": week, "events": events}
    gold_events = []
    for ev, m in zip(events, meta):
        fx = A.allocate(ev)
        gold_events.append({
            "event_id": ev["event_id"], "sku": ev["sku"], "scenario": m["scenario"],
            "flagged": fx["flagged"], "conservation_ok": fx["conservation_ok"],
            "true_cause": m["true_cause"], "citations": m["citations"],
        })
    return session, {"session_id": session_id, "notes": notes}, \
        {"session_id": session_id, "events": gold_events}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sessions", type=int, default=40)
    args = ap.parse_args()

    rng = __import__("random").Random(SEED)
    os.makedirs(DATA, exist_ok=True)

    sessions, notes_rows, gold_rows = [], [], []
    for i in range(args.n_sessions):
        s, n, g = build_session(i, rng)
        sessions.append(s)
        notes_rows.append(n)
        gold_rows.append(g)

    with open(os.path.join(DATA, "sessions.jsonl"), "w", encoding="utf-8") as f:
        for s in sessions:
            f.write(json.dumps(s) + "\n")
    with open(os.path.join(DATA, "notes.jsonl"), "w", encoding="utf-8") as f:
        for n in notes_rows:
            f.write(json.dumps(n) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for g in gold_rows:
            f.write(json.dumps(g) + "\n")

    tally, flagged_n, cause_tally = {}, 0, {}
    for g in gold_rows:
        for ev in g["events"]:
            tally[ev["scenario"]] = tally.get(ev["scenario"], 0) + 1
            if ev["flagged"]:
                flagged_n += 1
                cause_tally[ev["true_cause"]] = cause_tally.get(ev["true_cause"], 0) + 1

    print("sessions: %d   events: %d   flagged: %d" % (
        len(sessions), sum(len(s["events"]) for s in sessions), flagged_n))
    print("scenario tally:", tally)
    print("flagged-event cause tally:", cause_tally)


if __name__ == "__main__":
    main()
