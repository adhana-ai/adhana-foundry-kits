# obligation-extract — the promises in a subscription contract, and the ones it leaves open

**UC055.** Point it at a subscription contract pack — an order form plus the clauses behind its
lines — and get a worksheet back: one row per ordered line, with two calls made by a shipped
rulebook, plus a review flag taken afterwards in pure code. **The field that matters is the one
that says the paperwork does not settle it.**

> **⚠︎ This is a reviewer's worksheet. It is never an accounting conclusion.** It does not determine
> performance obligations, does not allocate a transaction price, does not conclude on timing, does
> not open a revenue schedule and does not write a journal entry. A controller does all of that, on
> the whole arrangement, against the framework their company reports under.
> **The worksheet rulebook shipped with this kit (`data/rulebook.json`) is illustrative and is not
> an authority** — it was written for this kit and reproduces no accounting standard, no
> standard-setter's guidance, no audit firm's manual and no company's revenue policy, and it names
> none of them. Replace it with your own before you decide anything real by it. See
> `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                       # free — validates the gold set
python -m evals.run --run-id b000-obligation-extract-priceline --baseline   # free — the price floor
python -m evals.run --run-id t000-obligation-extract-stub --stub   # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-obligation-extract --yes         # THIS SPENDS MONEY: one call/pack
python -m src.app                                                  # the local UI on 127.0.0.1:8804
```

## The decision: three stated facts, two calls, and a step people skip

```
separation(charge, dependency):            # work through in order, stop at the first that fires
    dependency == required_first                          -> bundled
    dependency == separately_available                    -> distinct   (whatever the fee says)
    dependency == silent AND charge == no_separate_charge -> bundled
    otherwise                                             -> not_determined

pattern(timing):
    timing == period -> over_time      timing == event -> point_in_time      timing == silent -> not_determined
```

`not_determined` is a first-class answer, not a failure to produce one. **A worksheet that never
reaches for it is not a confident worksheet, it is a guessing one** — and a call recorded as settled
is a call nobody re-reads, so an over-confident worksheet quietly removes the reviewer it exists to
serve.

**The rulebook is sent with every call.** Both calls are lookups over a shipped rule, and a model
cannot look up a rule it has never been shown. `src/rulebook.py::rulebook_block()` renders
`data/rulebook.json` into the prompt rather than restating it in prose, so the model's instructions
and the gold labels cannot drift apart about the same rule. On the worked example it is 847 of 3,067
input tokens.

## Three ways to put a promise on a worksheet that is not one

39 codes across the 50 packs are in the same format as a real line and are not obligations:

| decoy | what it is | packs |
|---|---|---|
| a line struck by an amendment | its code, its description **and its whole clause section** are still printed. Only the order-form row and the Contract Notes say it was removed | **13** |
| a professional-services rate card | a coded day rate, with the pack stating in terms that no services are ordered under this order form. A price is not a promise | **14** |
| an item continuing under an earlier order form | somebody else's paperwork, referred to here for context | **12** |

Note what `SECTION_HINTS` in `src/select.py` does **not** do: it does not drop those sections. All
three reach the model, because the whole identification score is "did the run leave those codes off
the worksheet" and a selector that hid them would be marking the model's homework. What selection
genuinely saves is the `Customer Reference` section — the customer's name, its segment, an account
number and a billing-contact reference — which no field maps to and which therefore **never leaves
the machine**: 464 of the corpus's 514 sections are sent, and the 50 that are not are exactly those.

## What it measures — four graders, never folded together

One scored run over 50 packs and 275 lines (`results/eval-r001-obligation-extract.json`):

| | |
|---|---|
| extraction accuracy | **1,961 of 1,975 cells (99.29%)** |
| obligation identification | **275 of 275 matched, 0 missed, 0 phantom** — every one of the 39 decoy codes left off |
| the separation call | **275 of 275 (100%)**, including all 105 the paperwork does not settle |
| the delivery pattern | **268 of 275 (97.45%)** |
| ⚑ **over-confident calls** | **7 of 175 (4.0%)** of the calls the paperwork does not settle |
| over-cautious calls | **0 of 375 (0%)** of the calls it does settle |
| `needs_drafting_review` | 12 of 12 fired, 38 of 38 left alone — 1.00 recall and precision |
| hallucinations / spans | 0 values invented; 325 of 325 returned strings located back to their own section |

### The headline is the over-confidence number, and it lives in one place

Every one of the seven errors is the same shape: **a line whose clause states no delivery timing at
all, answered `point_in_time` (6) or `over_time` (1)**. Not one of them is over-*caution*, and not
one is a separation call. Six of the seven sit on lines whose *dependency* clause names an
acceptance or completion moment — "not made available until the implementation acceptance
certificate is signed" — while the line states no timing of its own. **11 lines in the corpus are
shaped that way and the run missed 6 of them.** That is the failure mode this kit exists to expose,
found at its sharpest edge rather than asserted.

### And the consistency diagnostic could not see any of it

`evals/judge.py` re-runs the rulebook over each row's OWN extracted facts and counts rows whose
stated calls disagree. **0 rows disagreed, and it caught 0 of the 7 errors.** The model misread
`timing` and then applied the rulebook faultlessly to the misreading — which is exactly the blind
spot the diagnostic's own docstring names, demonstrated live rather than argued for. On the free
floor the same diagnostic catches **200 of 200** call errors with no labels at all, so it is worth
computing; it is reported as a diagnostic and deliberately not as this kit's guardrail.

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM worksheet builder: it reads every stated fact off the pack correctly by
regex — line code, description, type, fee column, dependency sentence, timing sentence — and then
**decides `separation` from the money column alone**: priced is `distinct`, unpriced is `bundled`.
No key, no cost.

It scores **40.0% on the separation call** and **74.55% on the pattern**, and — the number that
matters — it is **over-confident on 175 of 175 open calls, 100%**. It structurally cannot say
`not_determined` about anything. It also lists **all 13 struck lines** as obligations, because it
reads the order-form rows and never reads the amendment beside them, and its review flag fires
**0 times of 12**, because a floor that never says "not determined" can never notice a priced line
the contract leaves open.

Making the floor perfect would take one line — it already extracts every fact the rulebook needs.
Not doing so is the design: **the gap it opens is the gap between reading a price and applying a
rule.**

### One label in the scored run's file predates a wording fix

`evals/judge.py` describes the review flag's positive class in a string. That string said "a PRICED
line whose separation the paperwork does not settle" — accurate before the flag was narrowed to
require **both** calls open, and stale after. It was corrected, and the two free runs were re-run,
but `results/eval-r001-obligation-extract.json` was already paid for and carries the earlier
wording. **No behaviour and no figure differs**: `src/extract.py::compute()` has been the narrower
rule since before any run was fired, and all three runs scored against exactly that rule. Recorded
here rather than quietly patched into the result file.

## There is no LLM judge in this kit

Gold is exact, every answer is one value out of a closed set, and identification is a set
comparison — so `==` with light normalisation settles all of it. The two calls are rulebook lookups,
which is the one thing you should never ask a model to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the worksheet |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## Two things this kit measured about itself

**The calibration under-measured the ceiling by a factor of two.** A 6-pack calibration at
`max_tokens=16000` saw a largest reply of **3,398** output tokens, and `MAX_TOKENS` was set to 8,000
on that basis — 2.4x headroom. The scored run's largest reply was **6,776**, or **85% of the
ceiling**. Nothing truncated and no document was lost, but the margin was 15%, not 135%. A reply
here is a **list**, so its length scales with the pack, and a six-pack subset does not see the tail.
If you re-run this on longer packs, raise the cap first.

**Provider-side reasoning is 80.6% of the output bill.** 82,693 of the run's 102,608 output tokens
were reasoning rather than the JSON worksheet, which is about 400 tokens of actual content per pack.
Reasoning was left at the provider's default and **nothing here has measured what turning it off
would cost in accuracy** — `src/adapters/__init__.py` can send the parameter and this harness never
does. That is the one experiment worth firing next.

## Point it at your own contracts

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold row per pack.
**Replace `data/rulebook.json` first** — it is this kit's own construction and reproduces no
accounting standard. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will**
need editing for a different pack layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct.

If your packs are unlabelled — the normal case — the cell grade, the identification matrix and both
call graders go away, and the **consistency diagnostic** does not: it re-runs the rulebook over each
row's own facts and counts the rows whose stated calls disagree. No gold needed. It caught 200 of
200 of the free floor's errors and 0 of 7 of the model's, and that asymmetry is the honest statement
of what it is worth.

## What it does not do

It never determines a performance obligation, never allocates a transaction price, never concludes
on timing, never opens a revenue schedule, never writes an entry, and it is not a substitute for a
controller's judgement or the framework their company reports under. It reads one pack at a time. It
does not see the master agreement, a side letter, a prior amendment it is not shown, the customer's
other orders, or anything the sales team knows and did not write down. It has no view on
materiality, on the transaction price, or on how a discount spread across lines should be read. It
does no OCR — a scanned or image-only contract extracts no text. No auth, no database, no
multi-tenancy, no deployment story. It runs once per model, locally, and that run is what gets
published.
