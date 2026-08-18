# gap-brief — reconcile three plan views and draft the gap brief

One planning cycle, one drafting call. Code aligns three independently-maintained plan views —
demand, supply, financial, or any other three-way split a business tracks — for every line item
and decides which gaps are material (a 12% spread, or a missing view by itself). The model tags a
probable cause per material gap from a fixed five-member vocabulary — or says **unknown**, never
fabricated — cites the two exact notes lines that support a traceable cause, and drafts the short
narrative for the review meeting. **Decision-free by design: nothing here ranks the three plan
views or recommends an action.**

```bash
python -m src.app                                                # the local UI on http://127.0.0.1:8783

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-always-unknown             # free. no key, no spend.
python -m evals.run --run-id t000 --stub                          # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                          # THIS SPENDS: 40 calls, one per cycle.
```

## The job, generically

Reconcile three independently-maintained numeric plan views of the same underlying reality,
itemize every material gap with a quantified impact and a probable cause traced to two real
source lines, and draft the narrative brief for the meeting where humans decide what to do about
it — never fabricating an untraceable cause, never ranking the options itself. This corpus
flavours "three plan views" as a demand/supply/financial planning cycle across synthetic retail
categories, because that is the scenario the kit's originating use case names. Point
`tools/build_corpus.py` at your own three plan views and your own line items — a
budget/forecast/actuals set, a hiring-plan/headcount-budget/actual-headcount set, anything a
business tracks three ways — and the pipeline does not change. See
[`data/SOURCES.md`](data/SOURCES.md).

## Five causes, and the one that matters most

| cause | means | citations required |
|---|---|---|
| `timing_lag` | one view hasn't been refreshed since a change the others reflect | two real notes lines |
| `assumption_mismatch` | two views were built on different stated assumptions | two real notes lines |
| `data_entry_error` | a transcription/unit mistake moved one view | two real notes lines |
| `scope_mismatch` | one view rolls in a sub-line another excludes | two real notes lines |
| `unknown` | the notes don't support any of the four causes above | none — empty is correct |

`unknown` is the safe answer, not a fallback to avoid. `evals/scoring.py`'s fabrication guardrail
checks every non-`unknown` cause's two citations against that cycle's own notes log, as both a
real substring AND a line that actually names the item it's cited for — a citation that is real
but about the wrong item is graded as a fabrication, not a pass.

## What was measured — two models, 40 cycles, 146 material gaps

| run | model | completeness recall | completeness precision | cause-tag agreement | fabricated cause | narrative faithfulness |
|---|---|---|---|---|---|---|
| `b000-always-unknown` | **baseline** — itemize every gap it's handed, always say unknown | 100.0% | 100.0% | 29.5% | 0 | 100.0% |
| `r001-gap-brief` | **the fast tier**, reasoning off | **93.8%** | 95.1% | **100.0%** | **0** | **100.0%** |
| `r002-gap-brief-pro` | **the reasoning tier**, reasoning off | 64.4% | 64.4% | 100.0% | 0 | 100.0% |

The fast tier's real advantage over the floor is **cause-tag agreement**, not completeness: the
floor gets completeness for free (it's pure copying of what it was handed) but always says
`unknown`, so its cause-tag agreement is exactly the gold set's own unknown share (29.5%). The
fast tier correctly names a traceable cause — or correctly says unknown — 100% of the time it
matches a gap.

## The finding that matters more than either headline number

**Every miss on both runs is a formatting failure, never a wrong judgement.** In 2 of 40 fast-tier
cycles, the model echoed `item_id` as `"IT-2 (Base Layers)"` instead of the schema's bare
`"IT-2"`, which fails an exact-match join for every gap in that cycle at once — 14 of the run's 16
completeness misses trace to this alone. One more cycle (`GB-0017`) returned malformed JSON — an
unterminated narrative string, with `finish_reason` `'stop'` and only 265 of a 2,200-token
ceiling used, so not a budget cutoff.

**The reasoning tier does not fix this — it makes it 7.5x worse.** The identical id-formatting
slip hits 15 of its 40 cycles, collapsing completeness to 64.4%, at roughly **3.2x the fast
tier's cost**. Cause-tag agreement and narrative faithfulness both still hold at 100% on the
reasoning tier wherever it complies with the schema — this is a schema-discipline regression, not
a reasoning one, and the pricier model is decisively the wrong pick here.

## What it cannot do, stated up front

- **One planted cause per gap.** A real gap can have two compounding causes at once; this corpus
  always plants exactly one (or none, for the untraceable case).
- **One static cycle per line item, not a rolling history.** A real deployment would see the same
  item recur cycle over cycle; this corpus judges every cycle independently.
- **A notes log at real deployment volume.** This corpus ships 6–11 lines per cycle;
  `src/pack.py`'s 40-line cap was never exercised.
- **No schema-validation pass on the model's `item_id` field.** The id-formatting slip above was
  caught by this run's exact-match scorer, not prevented by the pipeline itself — see
  `Guardrails.add_first`.

## The gold cause is never inferred by the pipeline's own code

`tools/build_corpus.py` decides each item's scenario, its shifted view and (for the four
traceable causes) its exact two explanatory notes lines at generation time — all before
`src/segment.py::align` ever computes materiality on the same cycle. The pipeline recomputes
materiality independently, from the plan-view numbers alone, using the identical threshold the
generator was sized against; it never reads `data/gold.jsonl`. See
[`data/SOURCES.md`](data/SOURCES.md).

## Layout

```
data/cycles.jsonl             40 cycles: business unit, period, 5 line items x 3 plan views each
data/notes.jsonl               40 rows: the planning-notes log per cycle
data/gold.jsonl                  40 rows: every item's materiality, true cause, citations
src/segment.py                    the cut: aligns the three views, decides materiality
src/rubric.py                      the five-cause vocabulary and the three graded axes, once
src/pack.py                         deterministic assembly of the material-gap list + notes
src/prompt.py                        the cause vocabulary and answer schema, declared once
src/brief.py                          the AI layer: pack, call, parse
src/app.py                             the local UI (port 8783) -- runs the citation check live
evals/scoring.py                        pure-code scoring: completeness, cause-tag, fabrication, faithfulness
evals/baseline.py                        the free always-unknown floor
evals/run.py                              the real eval harness
tools/build_corpus.py                       generates cycles, notes and gold from a fixed seed
```

MIT, like every kit here.
