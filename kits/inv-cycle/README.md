# inv-cycle — draft a cycle-count variance's likely cause

One variance event, one drafting call. Code reads a single item/location's own transaction history
log — receiving, transfers, scans, adjustments — against the physical-count variance the cycle
count found, and the model tags a probable cause from a fixed five-member vocabulary — or says
**unresolved**, never fabricated — cites the exact log line that supports it, and drafts a short
note for inventory control. **Decision-free by design: the tool never posts an inventory
adjustment or closes the variance itself.**

```bash
python -m src.app                                                  # the local UI on http://127.0.0.1:8791

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-pack-multiple                # free. no key, no spend.
python -m evals.run --run-id t000 --stub                            # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                            # THIS SPENDS: 36 calls, one per event.
```

## The job, generically

Read one item/location's own transaction history, decide whether it supports a specific,
traceable explanation for a physical-count variance, cite the exact log line, and draft the short
note for the human who confirms and corrects it — never posting the adjustment itself, never
guessing a cause the log doesn't support. This corpus flavours "transaction history" as a
retail/warehouse cycle-count program — receiving, transfers, scans, adjustments — because that is
the scenario the kit's originating use case names. Point `tools/build_corpus.py` at your own
transaction types and item master and the pipeline does not change. See
[`data/SOURCES.md`](data/SOURCES.md).

## Five causes, and the one confusion that matters most

| cause | means | citation required |
|---|---|---|
| `mis_receipt` | a receiving correction was logged but never applied to on-hand | one log line |
| `unrecorded_transfer` | the variance lines up with unlogged activity at another location | one log line |
| `uom_error` | eaches and cases were mixed up for this item -- a specific line shows it, not just that the number divides evenly | one log line |
| `unscanned_movement` | more moved than the scan/pick log shows | one or two log lines |
| `unresolved` | the log doesn't clearly support one of the four causes above | none -- empty is correct |

`unresolved` is the safe answer, not a fallback to avoid. The guardrail: **drafted cause is
limited to what the transaction history actually supports, flagged unresolved rather than guessed
when the log doesn't point to one clear cause.** `evals/scoring.py` checks every non-`unresolved`
citation against that event's own log, as both a real line index AND the CORRECT line for the
cause stated — a citation that is real but doesn't actually evidence that cause is graded as a
fabrication, not a pass.

**The confusion this kit exists to catch.** ~44% of `unrecorded_transfer` events also have a
variance that is a clean multiple of a common case-pack size — the surface pattern `uom_error`
looks for. A drafter that pattern-matches "divides evenly by 12, must be a UOM mix-up" without
reading whether the log actually shows a unit-of-measure mismatch gets these wrong in the
expensive direction: the two causes point to different corrective actions.
`evals/scoring.py`'s `uom_transfer_confusion` metric counts exactly this, denominator = the trap
cases specifically, never all `unrecorded_transfer` cases.

## What was measured — one model, 36 events, four MAX_TOKENS attempts

| run | model | cause accuracy | citation validity | uom/transfer confusion | narrative faithfulness | no answer |
|---|---|---|---|---|---|---|
| `b000-pack-multiple` | **baseline** — case-pack multiple means uom_error, full stop | 52.8% | 0.0% | 100.0% (4/4, by construction) | 100.0% (trivial — templates the label into the text) | 0 |
| `r001-inv-cycle` (MAX_TOKENS=16384, registered) | **the fast tier**, reasoning left on | **77.8%** | **91.7%** | **0.0%** (0/4) | 35.3%\* | **2 of 36** |

\*a literal cause-label substring proxy, not a semantic check — manual reading of the 14
non-`unresolved` "unfaithful" hits found all 14 were drafted with the correct cause and a
citation independently scored valid; the narrative simply explains the mechanism in plain prose
rather than echoing the underscore-joined label word. See `evals/scoring.py`'s own docstring for
what the metric actually checks.

**Three earlier attempts are not shown, and that omission is the point.** MAX_TOKENS started at
2500 and was raised four times before landing on 16384: at 2500, 17 of 36 events came back
`finish_reason='length'` with zero answer tokens; at 4096, 14 of 36; at 8192, 5 of 36. Every one
of those was a truncation artefact, not a model failure — and the truncated EVENTS were a
different set each time (the 8192 ceiling's five failures share zero overlap with 16384's two).
Even the registered run at 16384 still has 2 of 36 events return no answer at all, reasoning
having consumed the entire ceiling — see `src/prompt.py`'s own `MAX_TOKENS` comment for the full
history. No fifth run was fired to chase that residual to zero.

**The trap this kit exists to catch was resisted cleanly.** All 4 planted `unrecorded_transfer`
events whose variance also divides evenly by a case-pack size were correctly drafted as
`unrecorded_transfer`, never `uom_error` — against the baseline's 4 of 4 wrong, by construction.
Separately, `unscanned_movement` is this run's clearest weak spot: resolved correctly only 1 of 7
times, the model defaulting to the safe `unresolved` on the rest rather than guessing.

## What it cannot do, stated up front

- **One planted cause per event.** A real variance can have two compounding causes at once; this
  corpus always plants exactly one (or none, for the untraceable case).
- **One event per item/location/period, not a rolling history.** A real deployment would see the
  same item recur cycle over cycle, sometimes still unresolved from last count; this corpus judges
  every event independently.
- **Complete transaction history, by assumption.** This kit assumes receiving, transfers and scans
  are captured completely enough to reconstruct a variance's cause. A store still running manual
  transfer logs on paper leaves gaps the drafted cause can't account for — the tool has no way to
  know evidence is missing rather than simply absent because there was none to log.
- **No schema-validation pass on the model's citation indices before scoring.** An out-of-range or
  malformed index is caught by `src/segment.py::line_supports_cause` at scoring time, not
  prevented by the pipeline itself.

## The gold cause is never inferred by hand

`tools/build_corpus.py` constructs each event's transaction log to carry the structural evidence a
real one would — a flagged receiving-correction line, a flagged counterpart-activity line, a
flagged unit-of-measure note — never a `true_cause` string written directly into gold. Once an
event is assembled, `src/segment.py::classify()` is the only thing that decides its cause and
citation, from the log and variance_qty alone; the identical function grades a live model's
citations in `evals/scoring.py`. `tools/verify_gold.py` re-runs `classify()` over the finished
`data/gold.jsonl` and fails loudly on any disagreement. See [`data/SOURCES.md`](data/SOURCES.md).

## Layout

```
data/events.jsonl                36 variance events: item/location/period, variance, transaction log
data/gold.jsonl                    36 rows: derived cause, citation, confirmed note, trap flag
src/segment.py                       the cut: the five-way rule, pure code, no model
src/rubric.py                          the five-cause vocabulary and the three graded axes, once
src/pack.py                              deterministic rendering of one event's log for the prompt
src/prompt.py                              the cause vocabulary and answer schema, declared once
src/brief.py                                 the AI layer: pack, call, parse
src/app.py                                    the local UI (port 8791) -- runs the citation check live
evals/scoring.py                                pure-code scoring: cause accuracy, citation validity,
                                                uom_transfer_confusion, narrative faithfulness
evals/baseline.py                                the free floor: a case-pack-multiple guessing rule
evals/run.py                                      the real eval harness
tools/build_corpus.py                               generates events and gold from a fixed seed
tools/verify_gold.py                                  asserts gold was derived, never typed
```

MIT, like every kit here.
