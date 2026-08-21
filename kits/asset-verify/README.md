# asset-verify — extract and verify asset/deposit figures from a bank statement

**UC031.** Point it at a bank or brokerage statement, get a field table back, plus two numbers
computed afterwards in pure code: a vested reserve value and whether the period's largest deposit
needs routing for underwriter review. Neither computed figure is an approval — both are proposals
for a person to check, never an auto-approval input.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the rules-and-regex extractor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per statement
python -m src.app                                      # the local UI on 127.0.0.1:8767
```

## The guardrail: a keyword is not a counterparty

The measurable failure this kit exists to catch is not a wrong balance — it is a large deposit
whose source was never actually verified getting waved through because a description merely
*sounds* documented. `deposit_documented` is `yes` only when the largest deposit's description
names a specific, verifiable **institutional** counterparty: a named employer, "IRS TREAS", a
named pension fund, "SSA", or a named bank/brokerage on a transfer. A generic "Payroll Deposit"
with no employer named, a P2P transfer, or a cash deposit is `no` — even when it uses the word
"payroll". See [data/SOURCES.md](data/SOURCES.md) for the planted ambiguity this corpus tests.

Two things happen downstream, in pure code (`src/extract.py::compute`), never authored from
intent and never a judgment call the model makes:

| | rule | not a real program's published guideline |
|---|---|---|
| `computed_reserve_value` | `ending_balance × VESTING[account_type]` — 100% for checking/savings/money market, 70% for brokerage | this kit's own simplification, stated plainly so nobody mistakes it for an agency's guideline |
| `large_deposit_flag` | `largest_deposit_amount >= $1,000 AND deposit_documented == "no"` | a flat, non-configurable threshold this kit chose — real programs vary by loan type and income |

## What it measures, and the number that matters most

Two models, same 55-statement corpus, same judge, same guardrail rule:

| | deepseek-v4-flash (r001) | deepseek-v4-pro (r002) |
|---|---|---|
| extraction accuracy | 98.47% (515/523) | 98.47% (515/523) |
| refusal accuracy | 100% (27/27) | 100% (27/27) |
| hallucinations | 0 | 0 |
| span rate | 97.16% | 97.16% |
| **large-deposit flag recall** | **1.00 (9/9)** | **1.00 (9/9)** |
| **large-deposit flag precision** | **1.00** | **1.00** |
| latency p50 / p95 | 2,490 ms / 3,278 ms | 5,064 ms / 7,806 ms |
| output tokens/call (avg) | 295 | 321 |

**Recall on the flag is the figure this kit exists to publish** — of every statement that should
have been routed for underwriter review, how many actually were. A model that never flags anything
can still post a respectable extraction accuracy on the other nine fields; this figure is reported
separately and never folded into it. See `evals/judge.py::score_flags`.

**The two tiers tie on every accuracy figure and disagree only on latency and output tokens.** The
higher tier is roughly twice the p50 latency and 9% more output tokens for identical scores on
this corpus — a real, measured case where paying for the bigger tier buys nothing on this task.
That is not a universal claim about either tier; it is what this corpus, on this run, showed.

## Where the model actually disagreed with this kit's own gold rule

In 8 of 55 statements, **on both tiers, identically**, the model marked a self-paid **"Interest
Payment"** as `deposit_documented: no`, where this kit's gold rule calls interest documented — the
holding institution pays it, so it is self-evidently verifiable off the same statement. **This
never affected the safety-critical flag in either run**, because every one of those interest
payments was well under the $1,000 threshold — but it is a real field-level disagreement, and
arguably as defensible a reading as this kit's own rule. Recorded here rather than smoothed over:
see `evals/judge.py`'s per-field breakdown in the committed run records.

## The baseline is shipped, including where it wins and where the gap actually is

`--baseline` is a non-LLM extractor: rules and regexes, no key, no cost. It scores **97.9%**
extraction because ten fields sitting in a fixed statement layout are mostly regex work — the
header fields, the balances, even picking out the largest deposit line by amount. **The gap is
entirely in `deposit_documented`**, where the baseline is a deliberate keyword floor (`payroll`,
`direct deposit`, `irs`, `ssa`, `pension`, `wire transfer` — see `evals/baseline.py`) that fails
the planted ambiguity by construction: it marks "Payroll Deposit" (no employer named) documented
and misses "ACH CREDIT ACME LOGISTICS INC" (a real employer, no keyword) entirely. On this
corpus's random seed the baseline's flag recall is **0.89 (8/9)** with **1 false negative** — one
large, undocumented deposit that a keyword scan waved through. That one missed statement is the
whole demonstration.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it —
adding an LLM judge would add cost and a second source of disagreement to a comparison that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one statement, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
ten fields × the whole statement is ten times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the context, not by the question.**

## Point it at your own statements

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
statement with a `stated` flag for every optional field. `SECTION_HINTS` in `src/select.py` maps
fields to section headings and **will** need editing for a different statement layout — when it
does not match, selection falls back to the whole document, which is slower and more expensive and
always correct. `LARGE_DEPOSIT_THRESHOLD_USD` and `VESTING` in `src/extract.py` are this kit's own
policy, not a real loan program's — replace them with your own program's actual rules before
trusting the computed figures for anything real.

## What it does not do

Reads one statement at a time and never nets multiple accounts together — a real underwriting file
usually holds several statements per applicant and totals available funds across all of them; this
kit computes a per-statement reserve figure only. No asset-seasoning check across statement
periods. Program eligibility varies by loan program and this kit does not model it — the threshold
and vesting percentages are one kit's own simplification. No OCR — scanned or image-only statements
extract no text. No auth, no database, no multi-tenancy, no deployment story. It runs once per
model, locally, and that run is what gets published.
