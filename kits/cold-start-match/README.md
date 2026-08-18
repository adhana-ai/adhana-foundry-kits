# cold-start-match — seed a new item's forecast from its prior comparable items

One new-item setup request with no sales history of its own, one candidate set (from
deterministic category blocking), one model call judging every blocked candidate at once, a
per-candidate LIKE_ITEM / NOT_LIKE_ITEM / UNSURE verdict -- then a deterministic calculator drafts
the recommended starting forecast, a range and a confidence tier from the counted like-item set's
own recorded outcomes alone, never asked of the model. Below 2 confirmed like items it refuses to
draft at all and escalates as insufficient comps instead of guessing.

```bash
python -m src.app                                        # the local UI on http://127.0.0.1:8785

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-exact-match-floor      # free. no key, no spend.
python -m evals.run --run-id t000 --stub                       # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                       # THIS SPENDS: 15 calls, one per request.
python -m evals.redteam --run-id x001-<model> --docs 5            # THIS SPENDS: up to 35 calls.
```

## The job, generically

Match a new item with no sales history against prior comparable items on a stated set of
attributes, and draft a quantified starting forecast from the ones that qualify. This corpus
flavours the "new item" as a retail SKU going through cold-start forecast setup and the attribute
set as material / price tier / channel / season, because that is one concrete, checkable instance
of the job. Point `tools/build_corpus.py` at your own attribute vocabulary and outcome metric and
the pipeline does not change. See [`data/SOURCES.md`](data/SOURCES.md).

## Three verdicts, and a rule with two explicit tolerances

| verdict | means | what it costs to get wrong |
|---|---|---|
| **LIKE_ITEM** | A genuinely comparable prior item -- safe to fold into the forecast estimate. | Wrongly called here, it silently pollutes the published number. |
| **NOT_LIKE_ITEM** | Resembles the request on the surface but fails the stated rule. | Wrongly called here, a real comparable is excluded -- recoverable, not silent. |
| **UNSURE** | The fields do not settle it either way. | Defaulting to a guess converts a real gap into a confident wrong answer. |

The rule requires an **identical material**, an **identical-or-adjacent price tier** (on a fixed
four-tier order), an **identical channel or a stated equivalent-family channel**, and an
**identical season** -- no other equivalence. The two tolerances (tier adjacency, channel family)
are exactly what the free exact-match floor cannot express.

## The forecast is never asked of the model

`src/forecast.py` averages the counted like-item set's own recorded `wk13_units_per_store` --
deterministic arithmetic, only ever as wrong as the like-item selection that fed it. Below
`MIN_LIKE_ITEMS_REQUIRED` (2) confirmed like items, it refuses to draft a number at all and
escalates as `insufficient_comps`.

## The gold values cannot drift from the rule

Nothing is hand-labelled. `tools/build_corpus.py::is_like_item()` computes every gold label by
applying the identical rule stated in `src/prompt.py`'s `RULES` text -- so a label can never
disagree with what the model is actually asked. Every request carries 3 deliberately planted like
items (one exact match, one exercising each tolerance) and 4 deliberately planted near-misses
(each violating exactly one rule); everything else is unshaped filler, labelled by the same rule
after the fact. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus design and its
limits.

## What it cannot do, stated up front

- **A perfect exact-match score is a property of this corpus's trap design, not a guarantee.**
  Every request carries planted like items; a request with zero true comparables in history has
  not been measured.
- **The blocking key is a single category equality check.** Every history item sharing a
  request's category is a candidate -- nothing here bounds the candidate list as a category's
  history grows.
- **Adjacency is defined by list position, not by a numeric value.** A change to
  `PRICE_TIERS`'s order or length changes what counts as adjacent everywhere at once.

## Layout

```
data/history.jsonl          120 synthetic history items across 5 categories
data/requests.jsonl         15 new-item setup requests
data/gold.jsonl              360 pairwise gold rows: like_item / not_like_item, one per blocked pair
data/SOURCES.md               why the corpus is synthetic, and what it does and doesn't test
src/normalise.py               categorical-field tidying, pure code
src/block.py                    candidate generation by category, pure code
src/similarity.py                the free exact-match floor
src/decide.py                     the merge threshold + five-outcome scoring
src/forecast.py                    the deterministic forecast-draft calculator
src/prompt.py                       the LIKE_ITEM/NOT_LIKE_ITEM/UNSURE vocabulary and rule, declared ONCE
src/match.py                         the AI layer: block, one call, parse, decide, draft
src/app.py                            the local UI (port 8785)
evals/scoring.py                       pure-code scoring: five outcomes, never one accuracy number
evals/baseline.py                       the free exact-match floor
evals/run.py                             the real eval harness
evals/redteam.py                          the note-poisoning attack harness
tools/build_corpus.py                     renders history, requests, derives the gold rows
```

MIT, like every kit here.
