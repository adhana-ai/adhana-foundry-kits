# ae-seriousness — classify an adverse event's regulatory seriousness and route the urgent cases

**UC036.** Point it at an adverse-event case report, get a field table back, plus one flag
computed afterwards in pure code: is this case *regulatorily* serious, and does the reporter think
the drug may have caused it. The computed flag never files a report and never starts a reporting
clock — it is a routing signal for a human case processor.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the severity-register floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per case
python -m src.app                                      # the local UI on 127.0.0.1:8772
```

## The guardrail: "severe" is not "serious"

This kit is built on a distinction that is real, public and constantly collapsed. Across
pharmacovigilance reporting, **serious** is a defined regulatory classification: the case is
serious when the event caused death, was life-threatening, required hospitalisation or prolonged
an existing admission, produced a persistent or significant disability or incapacity, produced a
congenital anomaly or birth defect, or was medically important enough to need an intervention to
prevent one of those. **Severe** is a description of how bad the event felt.

They come apart in both directions, and both directions are in this corpus:

> a **severe** headache that resolved at home with no medical attention — **not serious**
> a **mild** rash that led to a three-day admission — **serious**

`is_serious` is the one judgment field of ten. The prompt states all six criteria in full and
forbids the shortcut explicitly (`src/prompt.py`). See [data/SOURCES.md](data/SOURCES.md) for the
planted ambiguity and how gold is derived.

**Two thirds of this corpus's serious cases cannot be found by reading a field.** Hospitalisation
and death are the only criteria the record layout states in a structured field of their own; the
other four appear only in the narrative, sitting under a `hospitalization: no` and a non-fatal
outcome.

One computation runs downstream, in pure code (`src/extract.py::compute`), never a judgment the
model makes on top of its own classification:

| | rule | not a real program's rule |
|---|---|---|
| `needs_review` | the model's own `is_serious` is `yes` AND `causality_assessment` is `related` or `possibly-related` | this kit's own flat routing rule. A real expedited reporting obligation is a **clock** — it starts on a defined awareness event and runs a defined number of days, and which cases start it depends on product, market and report type. **None of that is modelled here.** |

Seriousness and causality are kept apart on purpose: a case can be serious *and* unrelated — a
hospitalised patient who was hit by a car. 16 of this corpus's 31 serious cases are exactly that,
and they are true negatives for the flag rather than misses.

## What it measures, and the finding that matters most

Two models, same 55-case corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-deepseek-v4-flash.json`, `eval-r002-deepseek-v4-pro.json`).

| | fast tier | deliberating tier | severity-register floor |
|---|---|---|---|
| extraction accuracy (550 cells) | 99.64% | **99.82%** | 94.91% |
| `is_serious` correct | 53 / 55 | **54 / 55** | 27 / 55 |
| …in the confusable register | 23 / 25 | **24 / 25** | **0 / 25** |
| review-flag recall | **1.00** (15/15) | 0.93 (14/15) | 0.47 (7/15) |
| review-flag precision | 1.00 | 1.00 | 0.78 |
| p50 latency | **3,538 ms** | 7,084 ms | 0 ms |

**The most useful thing this run found is the disagreement between the last two rows.** The
deliberating tier classified *more* cases correctly and scored *worse* on the flag. It made one
error where the fast tier made two — but its one error landed on a case whose reporter had called
the drug `related`, so it became a false negative. The fast tier's two errors both landed on cases
the flag would have dropped anyway (`unrelated` and `not-assessed`).

**So the fast tier's perfect 1.00 recall is luck, not safety.** Had either of its two
misclassifications fallen on a triggering case, recall would have been 13/15. Aggregate accuracy
and the safety-critical recall figure are not the same number, and on 55 cases neither of them is
a strong claim. This is written up on the kit page under `Business.not_good_enough` rather than
rounded away.

**Every classification error either model made is the same criterion.** All three misses across
both tiers — and every mild→serious miss the free floor makes — are *"medically important enough
to require an intervention to prevent one of the other outcomes"*: the one criterion of the six
that is a judgment rather than a fact. Both models read "no admission was required" and stopped.

Both tiers returned the correct `null` on all 7 cases whose report uses no severity word, with
zero invented values.

## The baseline is shipped, including where it wins

`--baseline` is a non-LLM classifier: it asks one question — does the report call the event
"severe"? — and returns that as the regulatory classification. No key, no cost.

It scores **55 of 55 on every one of the nine structured fields**; a fixed record layout is mostly
regex work, and a floor that lost there too would let a reader credit the model for the wrong
reason. **The entire gap is `is_serious`**: 23 of 23 right in the matching register, **0 of 25 in
the confusable register**. The zero is by construction and stated rather than hidden — the
confusable slice is *defined* as the records where this floor's one signal is inverted. It misses
8 of the 15 cases that should be flagged.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` (with light normalisation) settles it — adding
an LLM judge would add cost and a second source of disagreement to a comparison that needs
neither.

⚠︎ One scorer change was needed and it is worth naming: `narrative_severity_word` is legitimately
null on 7 records, and the sibling kits' scorer marked *any* null extraction a miss before it ever
looked at gold — a branch no sibling corpus ever exercised. Correct abstention is scored as a hit
here (`evals/judge.py`), and a null where gold has a value is still a miss.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
ten fields × the whole report is ten times the input tokens of sending each field the section that
could possibly state it. **The bill is driven by the context, not by the question** — on the
measured example the system prompt and field schema are 1,117 of 1,313 input tokens (85%), and the
case report itself is 196.

Two fields deliberately get more than one section: `narrative_severity_word` and `is_serious` are
the pair this kit keeps apart, and narrowing either to one section would hand the model the
half-view that produces the mistake being measured.

## Point it at your own case reports

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per case.
`SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need editing for a
different record layout; when it does not match, selection falls back to the whole document —
slower, more expensive, always correct.

⚠︎ **`CAUSALITY_TRIGGERS` in `src/extract.py` is this kit's own simplification, not any real
program's documented case-processing timeline or regulatory reporting deadline.** Replace it with
your own program's actual criteria before trusting the flag for anything real.

## What it does not do

Reads one case report at a time and never reconciles a follow-up report against the case it
amends — a real intake queue is full of follow-ups that change a case's seriousness after it was
first assessed, and nothing here models that. It never files a report, never starts a reporting
clock and never makes the seriousness determination final — it classifies and routes for a human
case processor. It does not check whether the reporter's stated causality is *reasonable*; it
copies it. `hospitalization: unknown` and `event_outcome: unknown` are allowed values that this
corpus never exercises, so nothing measured here says how the classification behaves when the
deciding fact is simply absent. No OCR — scanned or image-only reports extract no text. No auth,
no database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run
is what gets published.
