# docs-redact — mask sensitive spans in a document

**UC006.** One document in, a masked document out. A single model call finds every span of PII —
name, SSN, email, phone, address, date of birth, card number — and pure code does the rest: masking
each span to `[CATEGORY]` for the redacted output, and wrapping it for a highlighted view, with no
second model call involved in either.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once.

```bash
python -m tools.build_corpus                     # free — writes the 18 documents + labels
python -m evals.check_labels                      # free — validates every label is a real substring
python -m evals.run --run-id t000 --stub          # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>         # THIS SPENDS MONEY: one call per document
python -m src.app                                 # the local UI on 127.0.0.1:8770
```

## What it is measuring, and why it is two numbers that are never one

A redactor can fail in two directions, and they do not cost the same:

| | question | the miss |
|---|---|---|
| **leaked** | a real sensitive span the detector never reported | ships in the "redacted" output — the failure this kit exists to prevent |
| **over-redacted** | a reported span that was not actually sensitive | a false `[NAME]` where real text belonged — annoying, sometimes damaging, never a disclosure |

**These are never averaged into one number.** A detector that flags every word of a document as
every category catches 100% of the real spans and posts a perfect "recall" while making the output
useless; a detector that flags nothing posts perfect "precision" on the zero spans it dared to claim
while leaking everything. `evals/judge.py` reports leaked and over-redacted, plus precision and
recall, side by side — F1 is printed too, but only as a dashboard summary, never as the number a
change here should be tuned against.

## The corpus is invented, on purpose

The other kits in this repo build their corpora from real public records, because the property
under test is reading comprehension of a real document. This kit's property under test is *whether
a detector finds real people's sensitive data* — so testing it against real people's data is the
one thing it must never do. All 18 documents are original work, authored specifically for this kit,
fabricated end to end. See [data/corpus/SOURCES.md](data/corpus/SOURCES.md).

`tools/build_corpus.py` renders each document from a small dict of named entities and reads the
labelled spans back out of that same dict — so a document's text and its labels are never
independently retyped and cannot drift apart the way two hand-authored files can.

## Why there is no segment/select layer

docs-extract's documents run to several thousand tokens, so it sends each of nine fields only the
sections that could plausibly contain it — nine times the whole document would be nine times the
bill. These documents are a few hundred words each; the whole thing goes in the one call this kit
ever makes per document, and there is nothing to select from.

## There is no LLM judge in this kit

Same reasoning as docs-extract: the gold is exact spans of text and a detected span either matches
one (case- and whitespace-insensitively) or it does not. A judge would add cost, latency and a
second source of disagreement to a question `==` already settles.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one document, one call, on your machine |
| pure code | `src/redact.py` — locate spans, mask them, build the highlighted view. No model call anywhere in this file. |
| AI layer | `src/prompt.py`, `src/detect.py`, `src/adapters/` — one provider, one key, one call |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/check_labels.py` |

## Point it at your own documents

Replace `data/corpus/*.txt`, write your own `data/labelled.jsonl` (one line per document: `{"doc":
"<filename>", "spans": [{"text": "<exact substring>", "category": "..."}]}`), and run
`evals/check_labels.py` before spending anything — it fails loudly on a label whose text is not a
literal substring of its document. `data/categories.json` is the schema the prompt is generated
from; add an eighth category there and nowhere else.

## What it does not do

No OCR — scanned or image-only documents extract no text and there is no vision step. No auth, no
database, no deployment story, and no claim about categories this kit does not name: an eighth kind
of sensitive data (a passport number, a national ID outside the US) is not detected unless you add
it to `data/categories.json` yourself. It runs once, locally, and that run is what gets published.
