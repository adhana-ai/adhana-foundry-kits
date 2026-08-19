# alloc-short — draft a constrained-supply allocation review brief

One shortage event, one written five-clause policy, one drafting call. Code runs the policy —
protect promo commitments, protect customer commitments, fair-share the rest by trailing
velocity, check a 40% equity floor per store — and decides which events it could not cleanly
resolve. The model tags a probable cause per flagged event from a fixed four-member vocabulary —
or says **unknown**, never fabricated — cites the two exact merchant-notes lines that support a
traceable cause, and drafts the short narrative for the review meeting. **Decision-free by
design: the model never proposes a unit count for any store.**

```bash
python -m src.app                                                # the local UI on http://127.0.0.1:8787

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-always-unknown             # free. no key, no spend.
python -m evals.run --run-id t000 --stub                          # free. proves the wiring end to end.
python -m evals.parity_check                                      # free. the protected-class guardrail.
python -m evals.run --run-id r001-<model>                          # THIS SPENDS: 40 calls, one per session.
```

## The job, generically

Run a written allocation policy against a shortage event in code, itemize every event the policy
could not cleanly resolve with a quantified split and a probable cause traced to two real merchant
notes lines, and draft the narrative brief for the meeting where humans decide what to do about
it — never proposing a different split itself, never ranking which event matters more. This
corpus flavours "a written allocation policy" as a retail promo/customer-commitment/fair-share/
equity-floor policy across synthetic store networks, because that is the scenario the kit's
originating use case names. Point `tools/build_corpus.py` and `data/POLICY.md` at your own
policy's clauses and your own event shape — a capacity-allocation policy, a budget-allocation
policy, anything with a written priority order and a scarce pool — and the pipeline does not
change. See [`data/SOURCES.md`](data/SOURCES.md).

## Four causes, and the one that matters most

| cause | means | citations required |
|---|---|---|
| `promo_overcommit` | merchandising committed promo units across stores beyond what the DC has | two real notes lines |
| `customer_overcommit` | store reps took customer pre-orders beyond what the reservation system held | two real notes lines |
| `demand_surge` | a genuine, unplanned velocity spike, no one over-promised anything | two real notes lines |
| `supply_shortfall` | the DC itself received fewer units than the supply plan assumed | two real notes lines |
| `unknown` | the notes don't support any of the four causes above | none — empty is correct |

`unknown` is the safe answer, not a fallback to avoid. `evals/scoring.py`'s fabrication guardrail
checks every non-`unknown` cause's two citations against that session's own notes log, as both a
real substring AND a line that actually names the SKU it's cited for — a citation that is real but
about the wrong SKU is graded as a fabrication, not a pass.

## The written policy is authored, and says so

`data/POLICY.md` is this kit's five-clause allocation policy. The atlas facet sheet this kit
answers records, as its own open item, that no operator-supplied policy exists — so this one is
authored for the kit, the same move `docs-apply`'s policy documents make, and the file's own
header states this rather than implying it is a real retailer's policy.

## The protected-class guardrail is measured

Every store carries a `trade_area_tier` label so a reader can audit for disparate impact.
`src/allocate.py::allocate` never takes it as a parameter — the split cannot use it even if
someone tried. `evals/parity_check.py` proves the consequence with a 500-shuffle permutation test
across every generated event: **p = 0.42**, parity holds. Not asserted — measured, and the script
that measured it ships in the kit.

## What was measured — code floor plus one live tier, 40 sessions, ~150 flagged events

Run `python -m evals.run --run-id r001-<model>` against your own key to fill this section in with
a live result. The free floor (`evals.baseline`) gets flag completeness and protection-state
echoing for free — both are pure copying of what `src/allocate.py` already computed — but always
says `unknown`, so its cause-tag agreement on traceable gold is 0% by construction. That gap is
what a real model is paid to close.

## What it cannot do, stated up front

- **One planted cause per flagged event.** A real shortfall can have two compounding causes at
  once; this corpus always plants exactly one (or none, for the untraceable case).
- **A five-clause policy, not a real one.** `data/POLICY.md` is deliberately simple so its
  arithmetic stays auditable in one file; a real policy would have exceptions this one does not
  model.
- **No verification of the commitment fields themselves.** The atlas sheet's own second open item
  says the promo/customer co-sign gate "cannot be data-verified until [a system of record]
  exists." This kit assumes `promo_committed_units` and `customer_committed_units` are accurate
  input data; it does not check them against a system of record, because none exists yet in the
  operator's environment.
- **One static event, not a rolling history.** A real deployment would see the same SKU recur
  shortage-week over shortage-week; every event here is judged independently.

## Licence

MIT. The corpus, the written policy and the code are all authored here — see
[`data/SOURCES.md`](data/SOURCES.md) for why, and for what a Kaggle-sourced alternative was
weighed against and did not carry.
