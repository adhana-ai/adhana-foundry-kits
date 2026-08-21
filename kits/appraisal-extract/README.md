# appraisal-extract — extract structured fields from a real-estate appraisal report

**UC033.** Point it at an appraisal report, get a field table back, plus one number computed
afterwards in pure code: whether the report states an extraordinary assumption anywhere, which
routes it to a certified review appraiser. That routing flag is not an approval — it is a
proposal for a person to check, never an automated USPAP compliance judgment or value acceptance.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the heading-only extractor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per report
python -m src.app                                      # the local UI on 127.0.0.1:8769
```

## The guardrail: a heading is not the only place to look

The measurable failure this kit exists to catch is a stated extraordinary assumption that never
gets flagged because it was not sitting under an obviously-labelled heading.
`extraordinary_assumption_present` is `yes` when the report states an extraordinary assumption
ANYWHERE in its text — under a dedicated "Extraordinary Assumptions" heading, or embedded
mid-paragraph in Scope of Work or Comments prose with no special heading at all. Forty percent of
this corpus's extraordinary assumptions are written in that second, unlabelled form. See
[data/SOURCES.md](data/SOURCES.md) for the planted ambiguity this corpus tests.

One thing happens downstream, in pure code (`src/extract.py::compute`), never authored from
intent and never a judgment call the model makes:

| | rule | not a threshold |
|---|---|---|
| `needs_review` | `extraordinary_assumption_present == "yes"` — always, no dollar or materiality figure involved | unlike this kit's siblings (`asset-verify`, `income-verify`), which flag only above a $1,000 threshold, every stated assumption here routes for review, because this kit's own facet sheet keeps value/USPAP judgment with the certified review appraiser, never automated |

## What it measures, and the number that matters most

Two models, same 55-report corpus, same judge, same guardrail rule — see the committed run
records in `results/` for the exact figures (`eval-r001-deepseek-v4-flash.json`,
`eval-r002-deepseek-v4-pro.json`).

**Recall on the review flag is the figure this kit exists to publish** — of every report with a
stated extraordinary assumption, how many actually got routed for review. Both tiers hit **1.0
recall and 1.0 precision, 55/55** — including all 11 embedded assumptions with no dedicated
heading. Extraction accuracy came in at 98.09% on both tiers identically, and refusal accuracy
(correctly returning null when nothing is stated) at 100%, with zero hallucinations. The one real
gap: `extraordinary_assumption_text` narrows to the core assumption sentence rather than gold's
full surrounding paragraph, on 10 of 29 stated cases, identically on both tiers — a text-boundary
choice that never once changed presence detection or the review flag, and is captured honestly in
`Eval.taxonomy` rather than smoothed into the headline number. This figure is reported separately
and never folded into the flag recall/precision. See `evals/judge.py::score_flags`.

## The baseline is shipped, including where it wins and where the gap actually is

`--baseline` is a non-LLM extractor: a heading-only floor, no key, no cost. It checks ONLY for a
section literally titled "Extraordinary Assumptions" and answers "no" whenever that heading is
absent — exactly the shortcut the prompt's guardrail exists to forbid a model from taking. It
scores a respectable 95.8% extraction accuracy on the other eight fields — a fixed report layout
is mostly regex work — but its flag recall is **62.07%, missing 11 of 29 review flags**: every one
of this corpus's assumptions embedded in Scope of Work or Comments prose with no dedicated
heading. Both model tiers caught all 11.

The deliberating tier is also notably more expensive here than in this kit's siblings: **51% more
per report** than the fast tier ($0.0021037 vs $0.0013947, projected onto the same rate card), and
its p95 latency ran to **34.7 seconds against the fast tier's 5.9 seconds** — one call took 154
seconds. That is the largest tier gap measured in this three-kit series so far. Per
`Eval.could_not_verify`, no diagnosis was attempted: no `thinking` parameter was sent on either
tier (see `src/adapters/__init__.py`), so this is provider-default behavior on this corpus, not a
setting this kit's own harness controls.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it —
adding an LLM judge would add cost and a second source of disagreement to a comparison that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one report, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here:
sending ten fields × the whole report is ten times the input tokens of sending each field the
section that could possibly state it. The extraordinary-assumption field pair is the one
exception, sent three sections (Extraordinary Assumptions, Scope of Work, Comments) rather than
one, because the corpus's own planted ambiguity means any of the three could carry it. **The bill
is driven by the context, not by the question.**

## Point it at your own appraisal reports

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
report with a `stated` flag for the optional text field. `SECTION_HINTS` in `src/select.py` maps
fields to section headings and **will** need editing for a different report layout; when it does
not match, selection falls back to the whole document — slower, more expensive, always correct.
The no-threshold review rule in `src/extract.py::compute()` is this kit's own policy, chosen to
match its own facet sheet's judgment that this field carries no materiality floor — replace it
with your own program's actual review policy before trusting the computed flag for anything real.

## What it does not do

Reads one report at a time and never cross-references a separate addendum, prior appraisal, or
title report — a real collateral review often corroborates a report against other file documents;
this kit's routing decision comes from the report's own text alone. It never judges USPAP
compliance or accepts a value — extraction and structuring only, per this kit's own facet sheet.
No OCR — scanned or image-only reports extract no text. No auth, no database, no multi-tenancy, no
deployment story. It runs once per model, locally, and that run is what gets published.
