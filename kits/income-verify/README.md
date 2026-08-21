# income-verify — extract and verify income continuance from a pay stub

**UC032.** Point it at a pay stub, get a field table back, plus two numbers computed afterwards
in pure code: a proposed qualifying monthly income and whether an excluded bonus needs
underwriter review. Neither computed figure is an approval — both are proposals for a person to
check, never an auto-approval input.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the rules-and-regex extractor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per stub
python -m src.app                                      # the local UI on 127.0.0.1:8768
```

## The guardrail: a label is not a history

The measurable failure this kit exists to catch is not a wrong dollar figure — it is a one-time
bonus getting folded into qualifying income because its history note merely *sounds* recurring.
`bonus_recurring` is `yes` only when the Bonus History note states an ACTUAL PAYMENT HISTORY of
two or more prior payments. A note that only uses a word like "annual" or "recurring" with no
stated history is `no` — even when it uses that word. See
[data/SOURCES.md](data/SOURCES.md) for the planted ambiguity this corpus tests.

Two things happen downstream, in pure code (`src/extract.py::compute`), never authored from
intent and never a judgment call the model makes:

| | rule | not a real program's published guideline |
|---|---|---|
| `qualifying_monthly_income` | `ytd_base_pay/months` + `ytd_overtime_pay/months` (only if overtime was paid in ≥75% of this year's pay periods) + `ytd_bonus_pay/months` (only if `bonus_recurring == "yes"`) | this kit's own simplification, stated plainly so nobody mistakes it for an agency's guideline |
| `needs_review` | a bonus of **$1,000 or more** was excluded because `bonus_recurring == "no"` | a flat, non-configurable threshold this kit chose — real programs vary by loan type and income |

## What it measures, and the number that matters most

Two models, same 55-stub corpus, same judge, same guardrail rule — see the committed run records
in `results/` for the exact figures (`eval-r001-deepseek-v4-flash.json`,
`eval-r002-deepseek-v4-pro.json`).

**Recall on the review flag is the figure this kit exists to publish** — of every stub with an
excluded bonus of $1,000 or more, how many actually got routed for review. A model that always
marks a bonus recurring can still post a respectable extraction accuracy on the other nine
fields; this figure is reported separately and never folded into it. See
`evals/judge.py::score_flags`.

## The baseline is shipped, including where it wins and where the gap actually is

`--baseline` is a non-LLM extractor: rules and regexes, no key, no cost. It scores well on the
nine structured fields — a fixed stub layout is mostly regex work. **The gap is entirely in
`bonus_recurring`**, where the baseline is a deliberate keyword floor (`annual`, `recurring`,
`each year`, `quarterly`, `consistently` — see `evals/baseline.py`) that fails the planted
ambiguity by construction: it marks "Annual performance bonus" (no payment history stated)
recurring on the keyword alone, and misses "Bonus paid in both the 2024 and 2025 performance
cycles" (a real two-year history, no keyword) entirely. On this corpus's seed that produces
multiple missed review flags — large, non-recurring bonuses a keyword scan waved through into
qualifying income.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it —
adding an LLM judge would add cost and a second source of disagreement to a comparison that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one stub, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here:
sending ten fields × the whole stub is ten times the input tokens of sending each field the
section that could possibly state it. **The bill is driven by the context, not by the question.**

## Point it at your own pay stubs

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
stub with a `stated` flag for every optional field. `SECTION_HINTS` in `src/select.py` maps
fields to section headings and **will** need editing for a different stub layout; when it does
not match, selection falls back to the whole document — slower, more expensive, always correct.
`OT_CONTINUANCE_THRESHOLD` and `LARGE_BONUS_THRESHOLD_USD` in `src/extract.py` are this kit's own
policy, not a real loan program's — replace them with your own program's actual rules before
trusting the computed figures for anything real.

## What it does not do

Reads one stub at a time and never cross-references a separate W-2, tax return or employer
verification letter — a real underwriting file often corroborates a stub's history against a
second document; this kit's continuance determination comes from the stub's own Bonus History
note alone. Program eligibility varies by loan program and this kit does not model it — the
threshold and dollar figure are one kit's own simplification. No OCR — scanned or image-only stubs
extract no text. No auth, no database, no multi-tenancy, no deployment story. It runs once per
model, locally, and that run is what gets published.
