# position-reconcile — classify a position break and route true, aged breaks for review

**UC035.** Point it at a position-break record, get a field table back, plus one flag computed
afterwards in pure code: is this a genuine, unresolved discrepancy — as opposed to a benign,
self-resolving timing difference — and is it old enough to matter. The computed flag is never an
adjusting entry — it is a routing signal for an operations supervisor to check.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the keyword-register floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per record
python -m src.app                                      # the local UI on 127.0.0.1:8771
```

## The guardrail: judge by what happened, not by which words the memo uses

The measurable failure this kit exists to catch is not a missing field — it is classifying a
break by its memo's REGISTER rather than by what the memo actually says happened. `is_true_break`
is `yes` only when the memo describes a genuine, unresolved discrepancy — no explanation on file,
custodian unresponsive, no correction submitted. A memo that still reads "pending settlement"
after the settlement date has clearly passed with no confirmation is a true break despite using
settlement language; a memo that opens with an alarming word ("URGENT", "mismatch flagged") but is
fully accounted for by its own end is not. See [data/SOURCES.md](data/SOURCES.md) for the planted
ambiguity this corpus tests.

One computation runs downstream, in pure code (`src/extract.py::compute`), never authored from
intent and never a judgment call the model makes on top of its own classification:

| | rule | not a real firm's documented SLA |
|---|---|---|
| `needs_review` | the model's own `is_true_break` is `yes` AND `break_age_days` exceeds `AGING_THRESHOLD_DAYS = 3` | this kit's own flat aging window, stated plainly so nobody mistakes it for an actual reconciliation-committee escalation policy |

The kit also computes `break_quantity` (`custodian_quantity - internal_quantity`) alongside the
flag, purely arithmetic, no judgment involved.

## What it measures, and the number that matters most

Two models, same 55-record corpus, same judge, same guardrail rule — see the committed run
records in `results/` for the exact figures (`eval-r001-deepseek-v4-flash.json`,
`eval-r002-deepseek-v4-pro.json`).

**Recall on the review flag is the figure this kit exists to publish** — of every break that
should route to an operations supervisor (a true, unresolved discrepancy aged past the threshold),
how many actually got flagged. Both tiers hit 1.0 recall and precision on the review flag (25 of
25). The fast tier hit 100% extraction accuracy (550 of 550 cells); the deliberating tier missed
one cell — a one-character security-name misread ("Novocore" for "Novacore") on a field the flag
computation never touches. That is also a small sample for a rule this consequential; see
`Business.not_good_enough` on the published kit page. The fast tier is strictly better measured
here: lower latency, fewer output tokens, and the one miss of the night landed on the other tier.

## The baseline is shipped, including where it wins and where the gap actually is

`--baseline` is a non-LLM classifier: five fixed benign-sounding keywords, no key, no cost. It
scores well on the nine structured fields — a fixed record layout is mostly regex work, landing at
98.91% extraction accuracy. **The gap is entirely in `is_true_break`**, where the baseline is a
deliberate keyword-register floor (`pending`, `settlement`, `corporate action`, `dividend`,
`timing` — see `evals/baseline.py`) that fails the planted ambiguity by construction: it scores
80% flag recall, missing 5 of the 25 records that should have been flagged. Every one of those 5
misses is a genuine break whose memo still carries one of those five words despite describing an
unresolved discrepancy — exactly the register mismatch this corpus was built to plant.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it —
adding an LLM judge would add cost and a second source of disagreement to a comparison that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here:
sending ten fields × the whole record is ten times the input tokens of sending each field the
section that could possibly state it. **The bill is driven by the context, not by the question.**

## Point it at your own break records

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
break. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different record layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct. `AGING_THRESHOLD_DAYS` in `src/extract.py` is
this kit's own stated policy, not any real firm's actual documented reconciliation SLA or
escalation routing — replace it with your own program's actual standard before trusting the
computed flag for anything real.

## What it does not do

Reads one break record at a time and never cross-references a second, related break on the same
account — a real reconciliation queue often carries related breaks that a specialist would read
together, and this kit's determination comes from the one record's own memo alone. It never posts
an adjusting entry or makes the reconciliation determination itself — it classifies the break and
routes true, aged discrepancies for an operations supervisor to decide. `AGING_THRESHOLD_DAYS` is
this kit's own simplification and does not model how a real escalation policy might vary by
account type or break size. No OCR — scanned or image-only records extract no text. No auth, no
database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run is
what gets published.
