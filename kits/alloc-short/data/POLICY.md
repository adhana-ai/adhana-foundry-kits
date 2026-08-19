# Constrained supply allocation — written policy

**This policy was authored for this kit. It is not a real retailer's policy, and it is not claimed
to be.** The atlas facet sheet this kit answers records, as its own first open item: *"no written
allocation policy exists; atlas premise requires an operator-supplied written policy before
build."* No operator-supplied policy exists to encode, so this document is the one the kit ships
— five numbered clauses, run exactly as written by `src/allocate.py`. A real deployment forking
this kit replaces this file's clauses with its own; nothing downstream cares what the clauses say,
only that they are numbered, ordered, and that `src/allocate.py` implements the same five in the
same order.

## The five clauses, in the order they apply

1. **Protect promo commitments first.** Any unit a store has been promised against an active
   promotion (`promo_committed_units`) is protected before anything else, up to the amount
   available. If total promo commitments across every store exceed what is available, the pool is
   shared across promo-committed stores proportional to each one's own commitment — nobody's
   promo commitment is protected in full at another's total expense.

2. **Protect committed customer orders next.** Units already promised to a specific customer
   (`customer_committed_units`) are protected from whatever clause 1 left, on the same
   proportional-sharing rule if the remaining pool cannot cover every commitment in full.

3. **Fair-share the remainder by trailing velocity.** What is left after clauses 1 and 2 is split
   across every store's still-unmet ask, weighted by that store's trailing velocity — a store that
   sells this SKU faster gets a larger share of what remains — and capped so no store is ever
   allocated more than it actually asked for.

4. **No store below the equity floor.** After the first three clauses run, no store may end with
   less than 40% of its original ask, unless overall supply is short of even that floor across
   every store combined — in which case this clause cannot be honored and the event is flagged for
   review rather than silently under-filled.

5. **The allocation is decided from ask, velocity, and the two commitment fields only.** No
   store's trade-area demographic profile is ever read by the allocation formula. This is the
   guardrail the atlas facet sheet names as `zero protected-class violations`; see
   `evals/parity_check.py` for the measured proof.

## What this policy does not resolve — and why that is the point of the kit

The atlas sheet's own second open item says the co-sign gate on promo commitments "cannot be
data-verified until [a system of record] exists." This kit does not solve that: it drafts a
proposal for two humans (a store manager and merchandising) to co-sign, and it assumes the
`promo_committed_units` and `customer_committed_units` fields it is handed are accurate. It does
not, and could not, verify those commitments against a system of record that does not exist yet in
the operator's environment — see the kit's `not_good_enough` field for this stated plainly.

Real allocation events also surface cases these five clauses do not jointly resolve cleanly —
a promo commitment that itself exceeds the DC's supply, a customer-commitment total nobody
reconciled against the reservation system, a genuine demand spike nobody planned for, or a supply
shortfall on the DC's own receiving side. **The written policy does not say which of these
explains a given flagged event — that is not an arithmetic question, and it is exactly the
question this kit's model call exists to answer**, from the session's own merchant notes log,
never from the numbers alone. See `src/rubric.py`'s `CAUSE_VOCAB` for the four named explanations
plus `unknown`, the safe answer when the notes do not support any of them.
