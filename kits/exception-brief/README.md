# exception-brief — assemble the evidence packet for a forecast exception

One review batch, one drafting call. Code flags item/location combinations where recent POS
disagrees with the statistical forecast by enough to matter — or whose recent POS is itself
flagged unreliable — and packs the evidence (recent POS, lost-sales/OOS flags, the promo calendar,
the prior-year analog) with the batch's merchant notes log. The model tags a probable cause per
flagged item from a fixed five-member vocabulary — or says **unknown**, never fabricated — cites
the two exact notes lines that support a traceable cause, and drafts the short narrative for the
review meeting. **Decision-free by design: nothing here recommends accepting or overriding the
statistical forecast.**

```bash
python -m src.app                                                # the local UI on http://127.0.0.1:8786

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-always-unknown             # free. no key, no spend.
python -m evals.run --run-id t000 --stub                          # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                          # THIS SPENDS: 40 calls, one per batch.
```

## The job, generically

Assemble the evidence for an automated forecast exception — an item/location combination where an
actuals feed disagrees with a statistical baseline by enough to matter, or whose actuals feed is
itself unreliable — itemize each with a quantified deviation and a probable cause traced to two
real source lines, and draft the narrative brief for the meeting where a human decides what to do
about it — never fabricating an untraceable cause, never recommending an action. This corpus
flavours "statistical baseline vs. actuals" as a retail demand-forecast exception queue across
synthetic categories, regions and store locations, because that is the scenario the kit's
originating use case names. Point `tools/build_corpus.py` at your own forecast and actuals feed —
a reorder-point exception, a staffing-plan exception, anything an automated baseline flags against
an actuals feed — and the pipeline does not change. See [`data/SOURCES.md`](data/SOURCES.md).

## Five causes, and the one that matters most

| cause | means | citations required |
|---|---|---|
| `promo_uncaptured` | a promo not baked into the statistical baseline explains the deviation | two real notes lines |
| `oos_suppressed` | a lost-sales/out-of-stock period explains the deviation | two real notes lines |
| `onetime_event` | a one-off, non-repeating local driver explains the deviation | two real notes lines |
| `assortment_shift` | an item/pack/channel change broke comparability with the baseline | two real notes lines |
| `unknown` | the notes don't support any of the four causes above | none — empty is correct |

`unknown` is the safe answer, not a fallback to avoid. `evals/scoring.py`'s fabrication guardrail
checks every non-`unknown` cause's two citations against that batch's own notes log, as both a
real substring AND a line that actually names the item it's cited for — a citation that is real
but about the wrong item is graded as a fabrication, not a pass.

## What was measured — two models, 40 batches, 139 material exceptions

| run | model | exception recall | exception precision | cause-tag agreement | fabricated cause | narrative faithfulness |
|---|---|---|---|---|---|---|
| `b000-always-unknown` | **baseline** — itemize every exception it's handed, always say unknown | 100.0% | 100.0% | 35.3% | 0 | 100.0% |
| `r001-exception-brief` | **the fast tier**, reasoning off | **96.4%** | 100.0% | **100.0%** | **0** | **100.0%** |
| `r002-exception-brief-pro` | **the reasoning tier**, reasoning off | PENDING | PENDING | PENDING | PENDING | PENDING |

The fast tier's real advantage over the floor is **cause-tag agreement**, not completeness: the
floor gets completeness for free (it's pure copying of what it was handed) but always says
`unknown`, so its cause-tag agreement is exactly the gold set's own unknown share (35.3%). The
fast tier correctly names a traceable cause — or correctly says unknown — 100% of the time it
matches an exception.

## The finding that matters more than the headline number

**The fast tier's one miss is a single malformed-JSON reply, never a wrong judgement.** Batch
EB-0040's reply was well-formed for four of its five item entries and the narrative text itself,
but the narrative string's closing quote was never emitted before the closing brace —
`finish_reason` `'stop'` and only 697 of a 2,200-token ceiling used, so this was not a budget
cutoff. That single parse failure zeroed the batch's five material exceptions outright (0 of 5
answered), which is the entire gap between the fast tier's 96.4% recall and a clean 100%. Every one
of the other 39 batches parsed cleanly and scored 100% on cause-tag agreement, 0 fabrications and a
faithful narrative.

## What it cannot do, stated up front

- **One planted cause per exception.** A real exception can have two compounding causes at once;
  this corpus always plants exactly one (or none, for the untraceable case).
- **One static review per item, not a rolling history.** A real deployment would see the same
  item/location recur review after review; this corpus judges every batch independently.
- **A notes log at real deployment volume.** This corpus ships 6–11 lines per batch;
  `src/pack.py`'s 40-line cap was never exercised.
- **No schema-validation pass on the model's JSON output.** The malformed-JSON reply above was
  caught by this run's parser, not prevented by the pipeline itself — see `Guardrails.add_first`.

## The gold cause is never inferred by the pipeline's own code

`tools/build_corpus.py` decides each item's scenario, its shifted actual and (for the four
traceable causes) its exact two explanatory notes lines at generation time — all before
`src/segment.py::flag` ever computes materiality on the same batch. The pipeline recomputes
materiality independently, from the forecast/actual pair alone, using the identical threshold the
generator was sized against; it never reads `data/gold.jsonl`. See
[`data/SOURCES.md`](data/SOURCES.md).

## Layout

```
data/batches.jsonl               40 batches: region, review week, 5 flagged item/location candidates
data/notes.jsonl                  40 rows: the merchant-notes log per review batch
data/gold.jsonl                    40 rows: every item's materiality, true cause, citations
src/segment.py                       the cut: flags material exceptions
src/rubric.py                         the five-cause vocabulary and the three graded axes, once
src/pack.py                            deterministic assembly of the material-item list + notes
src/prompt.py                           the cause vocabulary and answer schema, declared once
src/brief.py                             the AI layer: pack, call, parse
src/app.py                                the local UI (port 8786) -- runs the citation check live
evals/scoring.py                           pure-code scoring: completeness, cause-tag, fabrication, faithfulness
evals/baseline.py                           the free always-unknown floor
evals/run.py                                 the real eval harness
tools/build_corpus.py                          generates batches, notes and gold from a fixed seed
```

MIT, like every kit here.
