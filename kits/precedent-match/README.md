# precedent-match — match a planned item to prior comparable cases, and draft an estimate

One planned request, one candidate set (from deterministic category blocking), one model call
judging every blocked candidate at once, a per-candidate ANALOG / NOT_ANALOG / UNSURE verdict --
then a deterministic calculator drafts the recommended lift, a range and a confidence tier from
the counted analog set's own recorded outcomes alone, never asked of the model. Below 2 confirmed
analogs it refuses to draft at all and escalates as insufficient precedent instead of guessing.

```bash
python -m src.app                                        # the local UI on http://127.0.0.1:8784

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-exact-match-floor      # free. no key, no spend.
python -m evals.run --run-id t000 --stub                       # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                       # THIS SPENDS: 15 calls, one per request.
python -m evals.redteam --run-id x001-<model> --docs 5            # THIS SPENDS: up to 35 calls.
```

## The job, generically

Match a new planned item against prior comparable cases on a stated set of attributes, and draft
a quantified estimate from the ones that qualify. This corpus flavours the "planned item" as a
retail promotion and the attribute set as mechanic / price band / ad placement / season, because
that is one concrete, checkable instance of the job. Point `tools/build_corpus.py` at your own
attribute vocabulary and outcome metric and the pipeline does not change. See
[`data/SOURCES.md`](data/SOURCES.md).

## Three verdicts, and a rule with two explicit tolerances

| verdict | means | what it costs to get wrong |
|---|---|---|
| **ANALOG** | A genuinely comparable precedent -- safe to fold into the lift estimate. | Wrongly called here, it silently pollutes the published number. |
| **NOT_ANALOG** | Resembles the request on the surface but fails the stated rule. | Wrongly called here, a real precedent is excluded -- recoverable, not silent. |
| **UNSURE** | The fields do not settle it either way. | Defaulting to a guess converts a real gap into a confident wrong answer. |

The rule requires an **identical mechanic**, an **identical-or-adjacent price band** (on a fixed
four-band order), an **identical placement or a stated equivalent-family placement**, and an
**identical season** -- no other equivalence. The two tolerances (band adjacency, placement
family) are exactly what the free exact-match floor cannot express.

## What was measured — two models, 15 requests, 360 pairs

| run | approach | precision | recall | f1 |
|---|---|---|---|---|
| `b000-exact-match-floor` | **baseline** -- the SAME category blocking, exact match on all four fields, no tolerance | 100.0% | 50.0% | 66.7% |
| `r001-precedent-match` | **deepseek-v4-flash**, reasoning off | 94.7% | 72.0% | 81.8% |
| `r002-precedent-match-pro` | **deepseek-v4-pro**, reasoning off | 100.0% | 70.0% | 82.4% |

**The baseline can never false-merge on this corpus, by construction** -- any pair that is
literally identical on all four fields also satisfies the true rule (identity is a special case of
"identical or adjacent"), so its errors are entirely on the recall side: it misses every candidate
that needs one of the two stated tolerances.

**Both paid tiers share one dominant, systematic defect.** 13 of the fast tier's 14 misses and 12
of the reasoning tier's 15 misses are the identical mistake: a candidate one price band away --
which the rule explicitly counts as valid -- rejected on a factually wrong distance claim (several
replies literally state two adjacent bands are "two bands apart"). The reasoning tier eliminates
false merges entirely (0 of 360 pairs vs the fast tier's 2) at roughly 8x the projected cost, but
does **not** recover the shared recall loss.

**The drafted lift is never asked of the model.** `src/lift.py` averages the counted analog set's
own recorded `actual_lift_pct` -- deterministic arithmetic, only ever as wrong as the analog
selection that fed it.

## We attacked the planner's note field, and it did not hold the way a structural defence would

Unlike a kit whose published figure is recomputed in code from a value the model merely extracts,
here the model's own per-candidate verdict directly decides what counts toward the drafted number
-- there is no downstream arithmetic step that can catch a wrongly-counted candidate. Six attacks,
appended to 5 requests each carrying a known gold NOT_ANALOG candidate:

**3 of 30 scored attempts (90.0% resisted) flipped at least one negative to ANALOG -- and the
attempt-level rate understates it.** The `blanket` attack ("this category has a standing
exemption") succeeded on 2 of its 5 attempts, and when it lands it does not nudge one candidate:
20 of 20 negatives flipped on one request, 19 of 21 on another. The `ignorerules` attack succeeded
once, more narrowly (1 of 21). The other four families (pre-approval, an off-vocabulary verdict,
instruction exfiltration, an essay-demand denial-of-service) were fully resisted. See
`Security.headline` on the published report.

## The gold values cannot drift from the rule

Nothing is hand-labelled. `tools/build_corpus.py::is_analog()` computes every gold label by
applying the identical rule stated in `src/prompt.py`'s `RULES` text -- so a label can never
disagree with what the model is actually asked. Every request carries 3 deliberately planted
analogs (one exact match, one exercising each tolerance) and 4 deliberately planted near-misses
(each violating exactly one rule); everything else is unshaped filler, labelled by the same rule
after the fact. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus design and its
limits.

## What it cannot do, stated up front

- **A perfect exact-match score is a property of this corpus's trap design, not a guarantee.**
  Every request carries planted analogs; a request with zero true precedents in history has not
  been measured.
- **The blocking key is a single category equality check.** Every history event sharing a
  request's category is a candidate -- nothing here bounds the candidate list as a category's
  history grows; see `Architecture.breaks_at_scale`.
- **Adjacency is defined by list position, not by a numeric value.** A change to
  `PRICE_BANDS`'s order or length changes what counts as adjacent everywhere at once.

## Layout

```
data/history.jsonl          120 synthetic history events across 5 categories
data/requests.jsonl         15 planned requests
data/gold.jsonl              360 pairwise gold rows: analog / not_analog, one per blocked pair
data/SOURCES.md               why the corpus is synthetic, and what it does and doesn't test
src/normalise.py               categorical-field tidying, pure code
src/block.py                    candidate generation by category, pure code
src/similarity.py                the free exact-match floor
src/decide.py                     the merge threshold + five-outcome scoring
src/lift.py                        the deterministic lift-draft calculator
src/prompt.py                       the ANALOG/NOT_ANALOG/UNSURE vocabulary and rule, declared ONCE
src/match.py                         the AI layer: block, one call, parse, decide, draft
src/app.py                            the local UI (port 8784)
evals/scoring.py                       pure-code scoring: five outcomes, never one accuracy number
evals/baseline.py                       the free exact-match floor
evals/run.py                             the real eval harness
evals/redteam.py                          the note-poisoning attack harness
tools/build_corpus.py                     renders history, requests, derives the gold rows
```

MIT, like every kit here.
