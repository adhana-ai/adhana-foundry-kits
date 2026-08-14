# docs-messy — extraction when the input is not clean text

Every other kit in this repo reads clean text. Real document pipelines do not: they read scans,
faxes-of-scans, and documents where two suppliers label the same field three different ways.

This kit measures the gap. It takes **sixty one-page business documents**, emits each one **twice**
— once as written, once as a mediocre scan hands it back — and extracts the same six fields from
both with two methods. One number falls out: **how much does extraction degrade when the input is
messy?**

```
python3 tools/build_corpus.py          # write the corpus (deterministic)
python3 tools/build_corpus.py --verify # prove the committed corpus matches the seed
python3 evals/baseline.py clean        # the free floor — pure code, $0.00
python3 evals/baseline.py messy
python3 evals/run.py --probe 3 clean   # 3 calls, proves the shape before the money
python3 evals/run.py clean             # 60 calls
python3 evals/run.py messy             # 60 calls
python3 -m src.app                     # the side-by-side UI on 127.0.0.1:8772
```

**The free floor needs no API key.** It is label-anchored rules, and it is the honest half of the
comparison: if the model degrades no better than rules do, the model is not buying you robustness.

## What is measured

| | |
|---|---|
| **Unit of work** | one document, in two conditions |
| **Fields** | document number, date, total, currency, counterparty, PO/customer reference |
| **Cells** | 360 — **340 stated**, **20 not stated** |
| **Extraction accuracy** | of the stated cells, how many were read correctly |
| **Refusal accuracy** | of the not-stated cells, how many were correctly left empty |
| **Hallucinations** | not-stated cells that came back with a value anyway |

Reading a total wrongly is a mistake. Inventing a purchase-order number that was never on the page
is a different and worse one, and on a damaged page it is the failure that grows — so the two
populations are scored separately and never averaged into one flattering number.

## The corpus is ours, and that is the point

Self-authored, MIT, generated from a fixed seed — `python3 tools/build_corpus.py --verify` rebuilds
it and diffs byte for byte. Two reasons, and the second is the one that mattered:

1. Real scanned enterprise documents cannot be published. They are third-party, usually
   confidential, and their licences do not permit redistribution.
2. This kit needs **the same page in two conditions with one ground truth attached to both**, and
   no public corpus ships that pair. We know what the page said before it was damaged, because we
   wrote it.

## ⚠︎ What this does NOT measure

**The degraded half is a model of scanner and OCR damage, not the output of a real scanner.** Every
error class in `src/corpus.py` is one OCR demonstrably makes — confusable glyphs (`0`/`O`, `l`/`1`,
`5`/`S`), swallowed spaces, dropped punctuation, `rn`→`m` ligature collapse, page furniture landing
mid-body, and failed de-hyphenation joining two lines — and the rates land the corpus at a **2.6%
character error rate**, which is where a decent scan of a clean printed page sits.

But it is a simulation. No number this kit publishes should be read as *measured against real
scans*. If you have real scanned documents with ground truth, point the kit at them — that is the
single most valuable thing a forker can contribute here.

## Swap seams

| Seam | File | Why you would |
|---|---|---|
| The degradation model | `src/corpus.py` | your scans are worse, or better, or fail differently |
| The free floor | `evals/baseline.py` | you have a real rules extractor to compare against |
| The prompt | `src/prompt.py` | your fields are not these fields |
| The provider | `src/adapters/` | any OpenAI-compatible endpoint, or Anthropic |
| The scorer | `evals/score.py` | your idea of "correct" is not exact match |

## The prompt is identical in both conditions

Deliberately. Telling the model "this came off a scanner, expect noise" measures how well a model
does when it is **warned**, and real pipelines do not know which of their inputs came back clean.
The page changes; nothing else does.
