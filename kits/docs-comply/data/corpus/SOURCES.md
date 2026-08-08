# Corpus sources — docs-comply

## The documents

**30 clinical trial registration records** from [ClinicalTrials.gov](https://clinicaltrials.gov),
pulled through the public API v2 on **2026-08-08** and rendered to plain text by
`tools/build_corpus.py`.

| | |
|---|---|
| Source | ClinicalTrials.gov API v2 (`https://clinicaltrials.gov/api/v2/studies`) |
| Licence | **Public domain** — ClinicalTrials.gov is operated by the National Library of Medicine, an agency of the U.S. Government, and its records are therefore works of the U.S. Government under **17 U.S.C. §105**, which are not subject to copyright protection. Basis checked **2026-08-08**. |

> **On how that licence was checked.** The grant rests on the **statute**, not on a scraped terms
> page. `clinicaltrials.gov/about-site/terms-conditions` answers `200` but is a JavaScript-rendered
> application whose served HTML contains no licence text at all — so a script that fetched it and
> looked for the words "public domain" would find nothing and could not tell that apart from a page
> that denied the grant. This note exists because the first draft of this file claimed the licence
> was "verified against" that URL, which was not a claim the fetch supported.
| Documents | 30 `.txt`, one per registered study |
| Total size | ~160 KB |
| Selection | 5 records in each of 6 recruitment statuses, chosen by the deterministic greedy in `tools/build_corpus.py` |

Raw API responses live in `data/_fetched/` and are **not shipped** — `.gitignore` holds them.
`data/` ships the rendered corpus, which is what the kit reads.

### Why these records and not UC007's

UC007 (`docs-verify`) ships a ClinicalTrials.gov corpus already, and reusing it was proposed for
this kit and then **measured and rejected**. Its fetcher hard-filters `overallStatus=COMPLETED`,
which flattens the rules a compliance rulebook turns on. Over those 20 documents, 6 candidate rules
were satisfied by all 20 and 7 by none; only 2 discriminated at all.

`Why Study Stopped` is the clearest case: the regulation requires it *"for a clinical trial that is
suspended or terminated or withdrawn prior to its planned completion"*, so on a corpus filtered to
COMPLETED it is a constant. This corpus spreads across six statuses precisely to keep it a variable.

The full measurement is in [`docs/CORPUS.md`](../../docs/CORPUS.md).

Conditions searched here overlap neither UC002's ten nor UC007's ten, on the reasoning recorded in
UC007's own fetcher: *"two kits measuring different things over the same documents is a weaker
demonstration than two corpora."*

## The rulebook

**42 CFR Part 11 §11.28(a)(2)** — the data elements a responsible party must submit to register an
applicable clinical trial — with each element's definition from **§11.10(b)**.

| | |
|---|---|
| Source | [eCFR](https://www.ecfr.gov) versioner API, `title-42.xml?chapter=I&subchapter=A&part=11` |
| Edition | **2025-01-01** (a past date is required; the current date has no snapshot and 404s) |
| Licence | **Public domain** — a work of the U.S. Government, 17 U.S.C. §105 |
| Rules | **41**, matching the regulation's outline exactly: 24 descriptive + 8 recruitment + 3 location/contact + 6 administrative |

**The rulebook is transcribed by code, never typed.** `tools/build_rulebook.py` parses the element
names, their citations and their definitions straight out of the regulation's XML. A rule that is
wrong here is wrong in the eCFR. Regenerate with:

```bash
python -m tools.build_rulebook --fetch
```

## What this corpus is not

It is **not** a compliance audit of these trials, and nothing here should be read as one. The kit
checks whether a *rendered registration record* states the elements Part 11 lists. A real audit
would work from the sponsor's full submission, would account for the waivers and deadlines in
§§11.44 and 11.54, and would be done by someone qualified to do it. Several elements Part 11
requires — `Human Subjects Protection Review Board Status` is the clearest — are simply **not
exposed by the public API**, so they read as never-addressed on every document here. That is a fact
about the API, not a finding about the trial.
