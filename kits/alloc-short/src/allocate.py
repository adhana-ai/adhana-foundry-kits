"""SEAM 1 -- the cut. Running the five-clause written allocation policy (data/POLICY.md) on one
shortage event and deciding whether it needs a human review. Pure code, no model -- same
discipline gap-brief's src/segment.py and param-drift's src/aggregate.py both keep: the thing
that decides the actual allocated units, and which events get itemized for review, must be
arithmetic on the event's own facts, never something the model asserted.

THE FIVE CLAUSES, IN THE ORDER THEY APPLY (data/POLICY.md is the same five clauses in prose):

    1. Promo-committed units are protected first, up to each store's own
       `promo_committed_units` -- a bounded PORTION of that store's ask, never the whole ask.
    2. Customer-committed units are protected next, from what clause 1 left, up to each store's
       own `customer_committed_units` -- a separate bounded portion of the same ask.
    3. The remainder is fair-shared by trailing velocity weight, capped at each store's own
       REMAINING ask (ask minus whatever clauses 1-2 already gave it) -- nobody is ever
       allocated more than they asked for, and a store cannot be double-counted across clauses.
    4. No store may end below EQUITY_FLOOR_PCT of its original ask, unless the event is
       globally short of even that floor across every store (a flag, never an auto-correction).
    5. Allocation is decided from ask, velocity, promo-committed and customer-committed fields
       ONLY. trade_area_tier is never a parameter of this function -- see
       evals/scoring.py::parity_check for the proof this holds on every generated session, not
       just a promise in this docstring.

⚑ 'PROMO-COMMITTED' AND 'CUSTOMER-COMMITTED' ARE BOUNDED PORTIONS OF ONE ASK, NOT TWO SEPARATE
ASKS -- FIXED 2026-08-18 AFTER A STRESS TEST CAUGHT THE ALTERNATIVE OVER-ALLOCATING. An earlier
version modeled promo commitment as a boolean that granted a store its FULL `ask_units` in clause
1, then let clause 2 add `customer_committed_units` on top for any store that carried both flags
-- allocating more than the store had asked for on every event where one store was both promo-
and customer-committed. `promo_committed_units + customer_committed_units <= ask_units` is now
enforced at generation time (tools/build_corpus.py), so a store's ask is a single pool that the
three clauses partition, never a total that two of them can both claim in full. 2,000 randomised
stress-tests, including cases where available_units exceeds total ask, are in
tools/selftest_allocate.py and assert zero over-allocations and 100% conservation.

⚑ CONSERVATION IS INTEGER AND EXACT, VIA LARGEST-REMAINDER. Splitting a fixed pool of whole units
by a continuous weight cannot round every store to its exact share and still sum to the pool --
some remainder units are always left over. Largest-remainder (compute exact shares, floor them,
hand the leftover units one at a time to the stores with the largest fractional remainder) is the
standard apportionment method for exactly this problem and it is the only one of the common
choices that GUARANTEES the sum equals `min(available_units, total_ask)` exactly, which is what
evals/scoring.py::conservation checks on every event, always, independent of the model call.

⚑ WHY 'FLAGGED' IS A FACT ABOUT THE NUMBERS AND 'CAUSE' IS NOT. An event is flagged the moment
protecting BOTH promo and customer commitments in full is not possible within available units, or
the equity floor cannot hold even before the fair-share step runs -- both are arithmetic on this
event alone. WHY it happened -- whose process broke -- is not visible in these numbers; it lives in
the session's merchant notes log, which is why that half is the model's job (src/prompt.py).
"""
EQUITY_FLOOR_PCT = 40.0          # a store may not end below this fraction of its original ask


def _largest_remainder(pool, shares):
    """`shares` are non-negative floats that should sum to (approximately) `pool`. Returns integer
    allocations, same order, summing to EXACTLY `pool`. `pool` must not exceed sum(shares)'s
    natural ceiling -- callers pass shares already capped so this never has to invent units."""
    floors = [int(s) for s in shares]
    remainder = pool - sum(floors)
    fracs = sorted(range(len(shares)), key=lambda i: (shares[i] - floors[i]), reverse=True)
    out = list(floors)
    for i in fracs[:max(remainder, 0)]:
        out[i] += 1
    return out


def _protect(pool, wants):
    """Split `pool` units across `wants` (a list of desired quantities, one per store, already
    bounded at that store's own ask) -- full protection when the pool covers every want, else a
    proportional, integer-exact, largest-remainder share of the pool. Returns (alloc list, whether
    every want was fully protected)."""
    total_want = sum(wants)
    if total_want <= 0:
        return [0] * len(wants), True
    if total_want <= pool:
        return list(wants), True
    idx = [i for i, w in enumerate(wants) if w > 0]
    shares = [wants[i] / total_want * pool for i in idx]
    got = _largest_remainder(pool, shares)
    out = [0] * len(wants)
    for k, i in enumerate(idx):
        out[i] = got[k]
    return out, False


def allocate(event):
    """One shortage event -> its full computed split. `event` carries `available_units` and
    `stores`, each with `ask_units`, `velocity_weight`, `promo_committed_units`,
    `customer_committed_units` (and, for the UI only, `trade_area_tier` -- read nowhere below).

    Returns every number src/pack.py is allowed to itemize: the per-store allocation, whether
    conservation holds, whether the event needs a human review, and -- ONLY as a numeric symptom,
    never a cause -- which protections could not both be honored.
    """
    stores = event["stores"]
    available = event["available_units"]
    n = len(stores)

    # Clause 1 -- promo protection, capped at available.
    promo_wants = [s["promo_committed_units"] for s in stores]
    promo_alloc, promo_protected = _protect(available, promo_wants)
    remaining = available - sum(promo_alloc)

    # Clause 2 -- customer-commitment protection, from what clause 1 left.
    cust_wants = [s["customer_committed_units"] for s in stores]
    cust_alloc, cust_protected = _protect(remaining, cust_wants)
    remaining -= sum(cust_alloc)

    # Clause 3 -- fair-share the rest by trailing velocity, capped at each store's remaining ask.
    #
    # ⚑ THE SHARE WEIGHT IS velocity_weight * remaining_ask, NOT velocity_weight ALONE. A bare
    # velocity weight is a per-store MULTIPLIER, not a size -- weighting by it alone splits the
    # pool by how fast a store sells relative to its PEERS' speed, with no regard for how much
    # that store actually asked for, so a large-ask store with an average-or-below velocity
    # multiplier ends up with a small pool share against a large ask and can fall under the
    # equity floor even when overall supply comfortably covers overall demand. "Fair-share by
    # trailing velocity" in a real allocation policy means proportional to each store's own
    # historical SELLING RATE, which scales with the store's own size to begin with -- so the
    # weight has to carry that size, and remaining_ask is the size this event actually offers.
    # With every multiplier near 1.0 (an ordinary week) this reduces to plain ask-proportional
    # sharing, which is what keeps every store near the same PERCENTAGE of its own ask and is
    # why the equity floor essentially never breaches on an undisputed, well-supplied event --
    # see tools/selftest_allocate.py's flag-purity check on the 'clean' scenario.
    fair_alloc = [0] * n
    remaining_ask = [max(stores[i]["ask_units"] - promo_alloc[i] - cust_alloc[i], 0)
                     for i in range(n)]
    pool = remaining
    # Iterative capped largest-remainder: a store whose weighted share would exceed its remaining
    # ask is capped and removed, and the freed pool is re-split among the rest -- at most n passes.
    active = [i for i in range(n) if remaining_ask[i] > 0]
    while pool > 0 and active:
        weight_total = sum(stores[i]["velocity_weight"] * remaining_ask[i] for i in active)
        if weight_total <= 0:
            break
        shares = {i: stores[i]["velocity_weight"] * remaining_ask[i] / weight_total * pool
                 for i in active}
        capped_any = False
        for i in list(active):
            if shares[i] > remaining_ask[i] + 1e-9:
                fair_alloc[i] = remaining_ask[i]
                pool -= remaining_ask[i]
                active.remove(i)
                capped_any = True
        if capped_any:
            continue
        got = _largest_remainder(pool, [shares[i] for i in active])
        for idx, i in enumerate(active):
            fair_alloc[i] = got[idx]
        pool = 0

    total_alloc = [promo_alloc[i] + cust_alloc[i] + fair_alloc[i] for i in range(n)]

    # Clause 4 -- the equity floor, checked against the final split. A flag, never a correction.
    floor_breach = []
    for i, s in enumerate(stores):
        floor_units = s["ask_units"] * EQUITY_FLOOR_PCT / 100.0
        if s["ask_units"] > 0 and total_alloc[i] < floor_units:
            floor_breach.append(s["store_id"])

    flagged = (not promo_protected) or (not cust_protected) or bool(floor_breach)

    per_store = [{
        "store_id": stores[i]["store_id"], "ask_units": stores[i]["ask_units"],
        "allocated_units": total_alloc[i],
        "promo_units": promo_alloc[i], "customer_units": cust_alloc[i],
        "fair_share_units": fair_alloc[i],
        "floor_breach": stores[i]["store_id"] in floor_breach,
    } for i in range(n)]

    total_ask = sum(s["ask_units"] for s in stores)
    return {
        "event_id": event["event_id"], "sku": event["sku"], "available_units": available,
        "total_ask": total_ask,
        "per_store": per_store,
        # A store is never allocated more than it asked for, so the split can only ever sum to
        # the SMALLER of what was available and what was actually asked for -- true whether this
        # event is a shortage (the corpus's only case) or, in a stress test, an oversupply.
        "conservation_ok": sum(total_alloc) == min(available, total_ask),
        "promo_protected": promo_protected, "customer_protected": cust_protected,
        "floor_breach": floor_breach,
        "flagged": flagged,
    }


def allocate_session(session):
    """Every event in one session, session's own order preserved -- the deterministic per-event
    computation the flow calls 'Allocate'. No event is dropped or reordered here; `pack.py` is the
    station that decides which of these get itemized to the model."""
    return [allocate(ev) for ev in session["events"]]


def flagged_events(session):
    """The subset `pack.py` and the scorer both itemize -- flagged events only, session's own
    event order preserved so a run is reproducible byte-for-byte."""
    return [fx for fx in allocate_session(session) if fx["flagged"]]
