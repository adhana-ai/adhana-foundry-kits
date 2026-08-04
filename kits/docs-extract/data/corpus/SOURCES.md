# Corpus sources — docs-extract

**57 study records from ClinicalTrials.gov**, fetched 2026-08-03 through the public CTG API v2
(`https://clinicaltrials.gov/api/v2/studies`).

## Licence

**Public domain.** ClinicalTrials.gov is a service of the U.S. National Library of Medicine, part
of the National Institutes of Health. Its records are **works of the U.S. Government and are not
subject to copyright protection in the United States** under 17 U.S.C. §105. There is no
attribution clause, no share-alike term and no notice file to carry.

NLM asks that use of its data not imply NLM endorsement. **This kit makes no such claim** — it
uses these records as a corpus of semi-structured documents and takes no position on any study,
sponsor, treatment or result described in them. Nothing here is medical information and none of it
should be read as such.

## What was fetched, and what is shipped

| | |
|---|---|
| Query | `query.cond=<condition>`, `filter.overallStatus=COMPLETED`, 6 per condition |
| Conditions | diabetes, asthma, melanoma, stroke, epilepsy, hypertension, psoriasis, migraine, sepsis, glaucoma |
| Records returned | 60 (3 duplicates across conditions, dropped) |
| **Shipped** | **57 documents**, one `NCT*.txt` each, 261,317 bytes |

Ten conditions rather than one so the documents do not all phrase things the same way. A corpus of
sixty records about a single disease would measure how well a model reads one house style.

## How a document was built — and why it is not the whole record

`tools/build_corpus.py` writes **only the record's own prose**: the identity header, Brief Summary,
Detailed Description, Interventions, Primary Outcome Measures and Eligibility Criteria.

**The structured modules are deliberately left out of the document and used only as gold.** Had
the design/status values been rendered into the text as labelled lines, extracting them back would
have measured nothing — the answer would have been written into the question. Keeping the two
apart is what makes a correct extraction evidence of reading, and a `null` evidence of restraint.

It follows that some values are **true but absent**: the registry knows a study's start date, the
prose never states it. `data/gold.jsonl` carries a `stated` flag per field recording exactly this,
measured — not assumed — by `tools/build_corpus.py --ceiling`.

## Reproducing this corpus

```bash
python tools/fetch_corpus.py     # network; the registry is edited daily, so this drifts
python tools/build_corpus.py     # deterministic from whatever was fetched
```

`data/_fetched/` holds the raw API responses and is **gitignored** — a kit ships a licensed corpus,
never the raw pulls.
