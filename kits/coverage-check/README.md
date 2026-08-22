# coverage-check — warranty claim coverage eligibility

One dealer warranty claim, one model call, fourteen extracted fields — and a coverage decision that
is six checks in a fixed order plus a date calculation. The job is not extraction: every value
except three is sitting on the page in a labelled section. The job is deciding whether the claim is
actually covered, when the loudest thing on the record is a technician's free-text narrative that
ends with their own guess about whether it will pay — and on this corpus **that guess is wrong on
22 of 55 claims**.

```bash
python -m src.app                                   # the local UI on http://127.0.0.1:8946

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python3 tools/build_corpus.py                        # free. rebuilds the corpus + gold from a seed.
python -m evals.check_labels                          # free. gold vs its own rule and its own dates.
python -m evals.run --run-id b000-rules --baseline     # free. no key, no spend.
python -m evals.run --run-id t000-stub --stub          # free. proves the wiring end to end.
python -m evals.calibrate --run-id c001 --n 6 --ceiling 16000   # SPENDS 6: measures MAX_TOKENS.
python -m evals.run --run-id r001-<model>              # THIS SPENDS: 55 calls, one per claim.
```

## What this kit never does

It never denies a claim, opens a chargeback, debits a dealer or contacts anybody. `covered` is a
field in a JSON response and `needs_review` is a routing signal computed from two of the extracted
values. If you are looking for the line that enforces this, there isn't one function to point at —
there is no code path anywhere in `src/extract.py`, `src/app.py` or the UI that performs a write or
an outbound call other than the single completion request.

## The mechanic: read the terms, do the arithmetic, then read the story

Each claim states a coverage plan, an in-service date, a repair date, an odometer reading, a failed
component, a claimed labor operation, a coded cause, whether it has already been paid, and the
technician's own narrative. One call returns fourteen fields, three of which are work rather than
transcription:

1. **`months_in_service`** — a calculation, not a reading. Complete months, minus one when the
   repair day-of-month is earlier than the in-service day-of-month. **6 claims sit exactly on a
   limit** and **7 sit exactly one month or one mile past it**; both are settled by that arithmetic.
2. **`narrative_finding`** — what the technician *describes* having found, read out of the
   narrative. Not the coded `Cause Code` field, which disagrees with it on **12 of 55 claims**.
3. **`covered`** — the six-branch rule, in order, stopping at the first check that fires.

```
1. an exclusion the technician describes         -> no    (outranks every coverage term)
2. the labor op is not this component's op       -> no    (not payable as coded)
3. the component is a wear item                  -> yes iff basic/extended AND <=12mo AND <=12,000mi
4. the component is not on this plan's list      -> no
5. past THIS PLAN'S month or mileage limit       -> no    (inclusive; never the basic 36/36,000)
6. otherwise                                     -> yes
```

The rule is written once (`tools/build_corpus.py::coverage_verdict()` and
`src/extract.py::coverage_verdict()` are the same six branches) and used three ways: to write gold,
to state the terms to the model, and to re-derive the verdict from the model's own reply.
`evals/check_labels.py` asserts the two copies agree before anything may spend.

## The two confusions this kit exists to refuse

**The technician's closing opinion.** Every narrative ends with one — "Should be covered under the
plan terms, no question", or "Vehicle is well outside the 3/36 so I expect this one gets denied".
On **22 of 55 claims (40%)** it contradicts the rule. `evals/baseline.py` decides coverage from
that sentence alone, deliberately, and scores **60.0%**.

**The coded cause against the narrated finding.** On **12 claims** the `Cause Code` field disagrees
with what the narrative describes — 6 exclusions filed as `defect` (a drive axle "cracked open with
fresh impact marks … a strike from underneath, not a failure", coded a defect) and 6 plain internal
failures coded as damage, a modification or missed maintenance. The floor copies the coded field
and scores **0 of 12** on them by construction.

Neither is adversarial text. A dealer coding a curb strike as a defect and a technician guessing
wrong about coverage are both ordinary; that is exactly why they are worth measuring rather than
assuming a model handles them.

## What was measured

Two runs on 2026-08-22 — `r001-coverage-check` (the fast tier) and `r002-coverage-check` (the
deliberating tier), 55 claims each, one call per claim, **0 failures and 0 truncations on both**.
Scored by `evals/judge.py`, which is pure code; the free floor below is scored by the identical
function.

| | fast tier | deliberating tier | free floor (`evals/baseline.py`) |
|---|---|---|---|
| extraction accuracy | **100.0%** (770/770 cells) | **100.0%** (770/770) | 95.58% (736/770) |
| coverage accuracy | **100.0%** (55/55) | **100.0%** (55/55) | 60.0% (33/55) |
| denial recall / precision | **1.00 / 1.00** | **1.00 / 1.00** | 0.607 / 0.607 |
| claims wrongly approved | **0 of 28** | **0 of 28** | 11 of 28 |
| `narrative_finding` accuracy | **100.0%** | **100.0%** | 78.18% |
| — on the 12 coded-cause traps | **12 of 12** | **12 of 12** | **0 of 12** |
| recovery flag (acc / recall) | **100.0% / 1.00** | **100.0% / 1.00** | 78.18% / 0.625 |
| replies disagreeing with own values | 0 | 0 | 22 |

Per deciding branch, both tiers: exclusion 8/8, labor op 3/3, wear 8/8, component list 6/6, limit
exceeded 7/7, inside terms 23/23.

120,277 input / 27,800 output tokens on the fast tier; 120,277 / 37,312 on the deliberating one
(identical prompt, 34% more output). Latency p50 4,375 ms / p95 5,710 ms fast, 8,662 / 13,693
deliberating. 244.8 s and 493.2 s wall.

**Read the 100%s with the corpus in mind.** Both tiers cleared every published grader, which means
this corpus **can convict the shortcut and cannot rank the models**. The free floor's 40-point gap
on coverage and its 0 of 12 on the coded-cause trap are the evidence that the corpus discriminates
at all; between the two tiers nothing separated them except 34% more output tokens and 98% higher
p50 latency. A corpus nothing fails has stopped measuring model quality.

### The `MAX_TOKENS` finding — it was measured, not inherited

`evals/calibrate.py` sent six claims, one from each of the hardest classes, at a deliberately
generous ceiling of 16,000 before either run was fired. Committed at
`results/calib-c001-coverage-check.json`:

| | |
|---|---|
| peak completion | **647 tokens** (`WCL-0007`, a one-month-past-the-limit case) |
| mean completion | 543.3 tokens |
| reasoning share | **60.3%** of every completion token billed |
| truncated | none — all six `finish_reason=stop` |

`MAX_TOKENS = 3000` is 4.6× the observed peak. Six in every ten tokens billed here never reach
`text` at all: reasoning is left at the provider's default (this kit never sends a `thinking`
parameter) and reasoning tokens are billed and bounded as completion tokens. A ceiling set from the
visible reply length would have truncated, and a truncated reply is scored as a wrong answer by any
grader that cannot tell the two apart. `evals/run.py` counts `finish_reason == "length"` separately
for that reason; both published runs recorded **0**.

## What it cannot do, stated up front

- **No real manufacturer, model, VIN, dealer or warranty booklet appears anywhere.** Every coverage
  plan, limit, component list and labor operation code was invented for this corpus — see
  [`data/SOURCES.md`](data/SOURCES.md).
- **The corpus contains the confusions we thought to plant and no others.** A real warranty queue
  carries goodwill authorisations outside the written terms, recall campaigns that supersede
  coverage, repeat failures of a previously-replaced part, lapsed or transferred contracts, and
  narratives written in shorthand rather than sentences. None of that is here.
- **Every claim carries at most one deciding branch**, so each failure mode is legible on its own;
  a real claim can be out of term *and* carry an exclusion *and* be coded wrong at once.
- **No red-team run was fired.** The technician narrative is externally-authored free text sitting
  in the same record as the structured values — the obvious place for an indirect prompt injection
  — and whether one could move `covered` is unmeasured. It is named as unmeasured rather than
  quietly counted as a boundary that holds.

## The gold labels cannot drift from the claim data

Nothing is hand-labelled. Every claim's facts are decided at construction time and
`coverage_verdict()` turns them into `covered` by the same six branches the kit publishes.
`tools/build_corpus.py`'s own `_verify()` asserts that every gold value is stated verbatim in the
document it labels, that every verdict is that document's own rule, that `months_in_service` agrees
with its own two dates, and that every class lands on the branch it was written for.
`evals/check_labels.py` re-runs all of that from disk and separately asserts: every branch is
exercised by at least two rows; the wear exception cuts both ways (4 covered, 4 denied); the
coded-cause confusion runs in both directions; every row exactly on a limit is covered (the limit
is inclusive); every opinion template classifies to the register it was authored in against the
free floor's own keyword list; and the two copies of the coverage terms in `src/` and `tools/`
agree.

## Layout

```
data/corpus/*.txt              55 warranty claim records -- everything the model is shown
data/gold.jsonl                55 gold rows, every verdict derived rather than typed
data/fields.json               the 14-field schema, with the rule stated in the `covered` hint
data/SOURCES.md                why the corpus is synthetic, the planted confusions, and its limits
src/segment.py                 cut a claim into addressable sections, pure code
src/select.py                  map fields to sections; Servicing Dealer is mapped by nothing
src/prompt.py                  the one system prompt -- the coverage terms stated in full
src/extract.py                 the AI layer: one call, the rule, the date arithmetic, the flag
src/app.py                     the local UI (port 8946)
src/config.py, src/budget.py, src/adapters/   shared plumbing, near-identical across every kit here
evals/judge.py                 pure-code scoring: cells, the coverage matrix, the flag, per-branch
evals/baseline.py              the free opinion-and-coded-cause floor, honestly narrow
evals/check_labels.py          the pre-flight that must pass before anything may spend
evals/calibrate.py             measures the completion budget MAX_TOKENS was set from
evals/prompt_tokens.py         measures the prompt split in TOKENS by nested prefixes
evals/run.py                   the real eval harness, plus --stub and --baseline for $0.00
tools/build_corpus.py          builds the claims, derives gold, verifies both
tools/capture_example.py       captures one adjudication verbatim for the report
tools/shoot_ui.mjs             screenshots the running UI
```

MIT, like every kit here.
