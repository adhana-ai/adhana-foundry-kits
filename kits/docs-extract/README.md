# docs-extract — pull structured fields out of semi-structured documents

**UC002.** Point it at a document, get a table of fields back. Every value that can be located
names the section it came from, and a field the document does not state comes back **`not found`**
— which is a correct answer here, not a gap.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once.

```bash
python -m evals.check_labels                     # free — validates the gold set
python -m evals.run --run-id b000 --baseline     # free — the rules-and-regex extractor
python -m evals.run --run-id t000 --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>        # THIS SPENDS MONEY: one call per document
python -m src.app                                # the local UI on 127.0.0.1:8766 (docs-qa owns 8765; --port moves it)
```

## What it is measuring, and why it is two numbers

The corpus is 57 ClinicalTrials.gov study records (**public domain** — see
[data/corpus/SOURCES.md](data/corpus/SOURCES.md)). A document is built from the record's own
**prose**; the gold values come from the record's **structured modules**. The two are kept apart
deliberately: render the answers into the document and you have written the answer into the
question, and a fine accuracy figure would mean nothing.

It follows that a value can be **true but absent** — the registry knows a study's start date, the
prose never says it. So every (document, field) cell falls into one of two questions, and
`data/gold.jsonl` carries a measured `stated` flag saying which:

| | question | verdicts |
|---|---|---|
| **stated** | did it find the value that IS there? | `hit` · `miss` · `wrong` |
| **not stated** | did it correctly return nothing? | `abstained` · **`hallucinated`** |

**These are never averaged into one number.** A model that invents a plausible value for every
unstated field scores well on the cells that exist and fails every cell that does not — and a
single blended figure would go *up* as it got less trustworthy.

## The field set is evidence, not a wish

`tools/build_corpus.py --ceiling` reports how many documents state each value **at all**. That is
a property of the corpus and no model can exceed it. Five fields from the original sketch were cut
on this evidence — `start_date` and `completion_date` are stated in **0** of 57 documents, `phase`
in 1, `lead_sponsor` in 3. Publishing an accuracy for any of them would have looked like a finding
about the model and been a fact about ClinicalTrials.gov's house style.

The nine that remain are deliberately mixed: four sit in the record header and are near-certain,
three are buried in prose and are the real test, and two are stated so rarely that the honest
answer is usually `not found`.

## The baseline is shipped, including where it wins

`--baseline` is a non-LLM extractor: rules and regexes, no key, no cost. It scores **77.9%**
extraction and **84.4%** refusal with **25 hallucinations**, and it takes four of the nine fields
perfectly — `nct_id`, `brief_title`, `condition` and `primary_outcome` are 57/57 for free.

**So the model has to earn its keep on five fields, not nine.** It is scored by the same judge over
the same corpus, so the two are comparable by construction. A kit that reported only its model's
number would let a reader conclude the model earned all nine.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` settles it — a judge would add cost, latency
and a second source of disagreement. UC001 grades free prose against a reference and genuinely
needs one. That the evaluation method changes between two kits on the same framework is the point:
it is **pluggable**, and this is the first evidence for that rather than a second demonstration of
the same method.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one document, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists because these documents *do* fit in a context window: sending nine fields ×
the whole document is nine times the input tokens of sending each field the sections that could
possibly contain it. **The bill is driven by the context, not by the question.**

## Point it at your own documents

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
document with a `stated` flag. `SECTION_HINTS` in `src/select.py` maps fields to section headings
and **will** need editing — when it does not match, selection falls back to the whole document,
which is slower and more expensive and always correct.

## What it does not do

No OCR — scanned or image-only documents extract no text and there is no vision step, which is why
receipt and form datasets were rejected for this corpus. No auth, no database, no multi-tenancy, no
deployment story. It runs once, locally, and that run is what gets published.
