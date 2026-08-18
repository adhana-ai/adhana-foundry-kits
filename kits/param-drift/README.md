# param-drift — flag a configured parameter that has drifted from observed reality

One parameter, one review call. It reads a configured operating value — a lead time, a safety
margin, a service target — against a rolling window of what the system has actually observed for
it, plus two facts computed by code (the trend across the window, and any outlier readings with
whatever note was logged against them), and decides **FLAG** (surface it for review, with a
proposed corrected value attached) or **HOLD**. The corrected value is never asked of the model —
`src/formulas.py` computes it deterministically from the observed window alone. **Decision-free by
design: nothing here auto-applies a change.**

```bash
python -m src.app                                                # the local UI on http://127.0.0.1:8782

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-rule-threshold-floor      # free. no key, no spend.
python -m evals.run --run-id t000 --stub                          # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                          # THIS SPENDS: 60 calls, one per parameter.
```

## The job, generically

Compare a configured operating parameter against the system's own observed real-world behaviour
over a rolling window, and flag which parameters have drifted far enough from reality to justify a
review — with a proposed corrected value attached. This corpus flavours "parameter" as a supplier
lead time, a demand-variability buffer and a service target across a synthetic replenishment
scenario, because that gives three genuinely independent parameter categories with different
correction arithmetic to exercise. Point `tools/build_corpus.py` at your own parameter shape — an
SLA threshold, a staffing ratio, a reorder point, anything a system relies on as a configured
constant — and the pipeline does not change. See [`data/SOURCES.md`](data/SOURCES.md).

## Two verdicts, and why the corrected value is never the model's to assert

| verdict | means | what happens next |
|---|---|---|
| **FLAG** | The configured value and observed reality have parted ways enough to justify a human look. | Surfaced with a proposed corrected value, computed by code. A person decides; nothing here applies it. |
| **HOLD** | Nothing here needs a person yet. | Nothing surfaces. |

`src/formulas.py::corrected_value` computes the proposed number from the observed window's own
mean (lead time, service target) or `1.65 x observed std` (safety margin — the standard
buffer-covers-variability shape) — **regardless of what the model said**, the same discipline
change-impact's `src/impact.py` states for its own dollar figure. The model's whole job is the
FLAG/HOLD judgement call.

## What was measured — one model, 60 parameters, three categories

| run | approach | recall (detection) | precision | value agreement |
|---|---|---|---|---|
| `b000-rule-threshold-floor` | **baseline** — a fixed deviation threshold per category, scored before any model call | 59.3% | 61.5% | 68.8% |
| `r001-param-drift` | **deepseek-v4-flash**, reasoning off | **88.9%** | 66.7% | 70.8% |

The model's real advantage over the floor is **recall**, not precision: it catches 88.9% of real
drift against the floor's 59.3%, because it can read the trend and outlier facts the floor's
single threshold structurally cannot. Per category the picture is uneven — see
`Business.not_good_enough` on the published report for the full breakdown, and the three findings
below for exactly where and why it disagrees with reality.

## Three real findings, not asserted — measured on this run

**1. The model mis-applies the "compare to the mean" heuristic to the one category where it is
wrong.** Every one of the 7 `safety_margin` parameters that were genuinely fine (`clean_hold`) was
false-flagged. Its own stated reasoning compares the configured buffer directly to the observed
*demand level* ("readings consistently above/below the configured value") — the right comparison
for a lead time or a service target, and the wrong one for a buffer, which should be judged against
the observed *variability* (`1.65 x std`), not the observed *level*. This is the single largest
driver of the model's weak 43.8% precision on this category.

**2. The corrected-value formula is measurably the wrong estimator for a still-moving trend.** For
`lead_time` and `service_target`, `corrected_value` is the whole-window mean. On a `slow_creep`
parameter, the true current value is near the END of the window, not its average — so the proposed
value lands between where the parameter started and where it now is. 3 of `lead_time`'s 4
`slow_creep` parameters disagreed with gold on this exact structural basis.

**3. The trend fact tracks the window's mean, not its spread — so a widening-variability drift is
invisible to it.** `safety_margin`'s `slow_creep` scenario drifts by widening the *spread* of
demand readings, not shifting their average; `src/aggregate.py::trend` only compares first-half vs
second-half MEAN, so it reports "no material trend" on exactly the case where the real signal is a
growing standard deviation. One parameter (`PD-0037`) was missed by both the floor and the model
for precisely this reason.

## The gold corrected value cannot drift from the pipeline's own formula, and is not computed by it

`tools/build_corpus.py` decides a TRUE underlying value at generation time and samples the window's
readings around it with realistic noise; the gold corrected value is that true value, never run
through `src/formulas.py`. The pipeline's own proposed value is computed later, from the noisy
observed window alone — so how close the two land is a measured question, not a tautology (a
generator that computed gold from the same formula the pipeline runs would score every drift case
100% by construction, which would test nothing). See [`data/SOURCES.md`](data/SOURCES.md).

## What it cannot do, stated up front

- **One rolling window snapshot per parameter, not a live stream.** A real deployment re-cuts the
  window every cycle; this corpus ships one static ten-period window per parameter.
- **Three categories, one formula each.** A parameter category this kit has not seen needs its own
  entry in `src/formulas.py` — the model's judgement generalises more readily than the deterministic
  correction arithmetic does.
- **The trend fact is mean-only.** See finding 3 above; a spread-based drift needs a second fact
  this kit does not yet compute.

## Layout

```
data/parameters.jsonl        60 parameters: category, entity, configured value, unit
data/readings.csv             600 rows: one reading per parameter per period, with notes
data/labelled.jsonl           60 gold rows: drift/no-drift, trap, gold corrected value
data/SOURCES.md               how the corpus was generated, and what it does and doesn't test
src/aggregate.py              the cut: grouping readings into windows, mean/std/trend/outliers
src/formulas.py                the free floor's threshold, and the deterministic corrected value
src/prompt.py                   the FLAG/HOLD vocabulary, declared once
src/triage.py                    the AI layer: assemble, call, parse, always compute the value
src/app.py                        the local UI (port 8782)
evals/scoring.py                  pure-code scoring: five outcomes, never one accuracy number
evals/baseline.py                  the free rule-and-threshold floor
evals/run.py                        the real eval harness
tools/build_corpus.py               generates parameters, readings and gold from a fixed seed
```

MIT, like every kit here.
