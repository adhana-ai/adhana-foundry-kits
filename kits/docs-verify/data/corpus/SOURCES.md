# Where this corpus came from, and why we may ship it

**20 study records. Public domain. Fetched 2026-08-08 from the ClinicalTrials.gov API v2.**

This file sits next to the documents on purpose. How the corpus was built is recorded in
`tools/fetch_corpus.py` and `tools/build_corpus.py` — but both of those scripts open by telling you
that **you do not need to run them**, so neither is a place a licence can live. A claim about the
right to redistribute twenty files has to travel with the files.

## The licence

ClinicalTrials.gov is operated by the National Library of Medicine at the National Institutes of
Health. Its study records are **works of the United States federal government**, which under
**17 U.S.C. §105** are not subject to copyright protection in the United States. There is no
attribution clause, no share-alike term, no notice file to propagate.

Verified against the registry's terms-of-use page on 2026-08-08. This is the same grant UC002
(`docs-extract`) ships under, established there on 2026-08-03 and unchanged since.

**Records are sponsor-submitted.** The registry is a government publication; the underlying study
is somebody's research. Nothing here is presented as this repo's work, no record is edited, and no
sponsor, investigator or institution named in a record is making any claim on this repo's behalf.
The records are reproduced as reference documents to check claims against — which is exactly what
a registry is for.

## Why this source, for this kit specifically

The other kits that use CTG want a document that is **hard to read correctly**. This kit wants
something different: a document **dense with short, specific, checkable assertions**.

A study record is unusually good at that. Phase, enrolment, allocation, masking, eligibility
bounds, sex, lead sponsor and the primary outcome's time frame are each a single factual statement
that a claim can agree with, contradict, or fail to mention — with no interpretation in between.
That is what makes a three-way verdict gradable at all. A narrative document would have forced a
judgement call on nearly every row, and a judgement call is not a label.

**Ten conditions, three studies each, none overlapping `docs-extract`'s ten.** Two kits measuring
different things over the same 57 documents would be a weaker demonstration than two corpora, and
a forker comparing the two kits should not be looking at the same text twice.

| | |
|---|---|
| conditions | osteoarthritis, anemia, COPD, hepatitis, lymphoma, endometriosis, tuberculosis, cataract, obesity, insomnia |
| filter | `overallStatus=COMPLETED` — a completed study has its enrolment as an ACTUAL count rather than an estimate, so the most quotable number on the record is a fact rather than a plan |
| shipped | the first 20 unique records, sorted by NCT id — deterministic, not sampled |

## Where the claims come from, and why they cannot be wrong

`data/claims.jsonl` is **not** hand-typed against the finished documents. That is the failure mode
this dataset is built to avoid: write 174 claims by hand, edit a document later, and some unknown
number of your labels are now wrong with nothing to tell you.

Every claim is **derived from the same structured field the document text is rendered from**, so
the text and the label come from one source by construction:

| label | how it is made | count |
|---|---|---|
| `supported` | a template filled with the record's **own** value | 88 |
| `contradicted` | the same template filled with a **different** value | 46 |
| `not_stated` | an assertion about something a protocol record does not carry at all | 40 |

**Every field produces both classes.** An earlier build contradicted only phase, enrolment and
allocation, which was two defects at once: the set came out 76% `supported`, so a grader that
answered "supported" to everything would have scored 76; and every falsehood lived in three field
types, so a model could have scored well by learning *"claims about phase are suspicious"* instead
of by reading the document. Rotating the perturbation across all eight fields fixed both. As
shipped, the majority-class floor is **51%** — which is what the `b000` baseline measures.

## The build refuses to ship a wrong label

`_verify()` in `tools/build_corpus.py` fails the build rather than emit a claim it cannot stand
behind. It has caught two real defects already, both on their first run:

- a `not_stated` claim about adverse events, on a record whose brief summary **discusses adverse
  events** — plausible, absent from the structured fields, and genuinely addressed by the prose.
  The builder now takes the first template whose trigger words are absent from *that* document.
- a `contradicted` claim asserting **120** participants against a record mentioning **1200** —
  `"120" in text` is true of `"1200"`. Matching moved to word boundaries, and the enrolment
  perturbation now searches for an offset the document genuinely does not contain.

Both directions are checked. A `supported` claim's own value must appear in its document. A
`contradicted` claim must have the true value present **and** its asserted value absent — a
contradiction is a relationship, not a value, and if there is nothing to contradict then the
honest label is `not_stated`.

## Reproducing this corpus

```bash
python -m tools.fetch_corpus     # network; writes data/_fetched/ (never shipped, see .gitignore)
python -m tools.build_corpus     # deterministic — same 20 documents and 174 claims every time
```

The registry is edited daily, so a fresh fetch will not reproduce these exact records. That is
why `_fetched/` and the built corpus are separate steps: the corpus in this repo rebuilds
byte-for-byte from a given pull, with no network involved.
