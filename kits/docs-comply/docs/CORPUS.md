# Why this kit fetched its own corpus — the measurement

The plan of record was to reuse `docs-verify`'s 20 ClinicalTrials.gov documents and add a rulebook
as one file. That was proposed, approved on that recommendation, and then **measured and found not
to work**. This is the measurement, kept because the reasoning is the reusable part.

## What was wrong with reusing UC007's corpus

A rule that every document satisfies, or that no document satisfies, measures nothing. It cannot
separate a checker that reads from one that guesses, and it inflates whatever headline number the
eval prints. Over UC007's 20 documents:

| | candidate rules |
|---|---|
| satisfied by **all 20** | **6** — primary outcome, brief summary, interventions, time frame, … |
| satisfied by **none** | **7** — official title, responsible party, facility, why stopped, … |
| discriminating at all | **2** |

Field *values* do vary there — `Phase` takes 7 distinct values including absent — but only into
19–1 splits, and the Eval lens requires a balanced set.

**The cause is in the fetcher, not the corpus.** `tools/fetch_corpus.py` in UC007 hard-filters
`overallStatus=COMPLETED`. That is the right call for claim-checking and the wrong one here,
because Part 11's most discriminating rule is conditioned on the opposite:

> **Why Study Stopped** means, *for a clinical trial that is suspended or terminated or withdrawn
> prior to its planned completion as anticipated by the protocol*, a brief explanation of the
> reason(s) why the clinical trial was stopped. — 42 CFR §11.10(b)

Filter to COMPLETED and that rule is a constant on every document.

## What was fetched instead

Same API, same public-domain licence, same `corpus_contract`-clean declaration. Only *which
records* changed: **117 records spread across six recruitment statuses**, then narrowed to 30.

Measured over the 117-record pool, against the 41 transcribed rules:

| | |
|---|---|
| rules that discriminate | **26 of 37 probed** (vs 2 of 15 in UC007's corpus) |
| `whyStopped` present | 50 / 117 — **0 / 20** in UC007's corpus |
| `secondaryOutcomes` present | 87 / 117 |

## Selecting the 30 that ship

Discrimination at pool size says nothing about the corpus that ships: a stratified-random subset
can flatten a 110/7 rule to 30/0. The selector in `tools/build_corpus.py` is a deterministic greedy
with a status quota (5 × 6) and a **lexicographic** objective:

1. distinct **(rule, breach) pairs** covered
2. rules that vary at all
3. raw breach count

Priority 1 exists because `Individual Site Status` alone accounts for **81 of the pool's 95**
breaches, and a selector optimising raw count would have bought 30 copies of one rule.

### What shipped

| verdict | count | share of applicable |
|---|---|---|
| met | 792 | 74.2% |
| **breached** | **38** | **3.6%** |
| never addressed | 238 | 22.3% |
| not applicable | 162 | — (dropped before scoring) |

**25 of 41 rules vary across the corpus.** All four breach-bearing rules are represented, and the
selector captured **every** rare breach the pool contained — 7/7 `Why Study Stopped`, 4/4
`Facility Information`, 3/3 `Enrollment`, plus 24 `Individual Site Status`.

## The imbalance is reported, not fixed

**Breach is rare in this data and the kit does not pretend otherwise.** The whole 117-record pool
is 2.3% breached, because ClinicalTrials.gov enforces most of these elements at submission time —
so a compliance checker run over a well-curated registry genuinely finds few breaches. That is a
property of the domain worth knowing, not a defect to engineer away.

The obvious way to balance the classes is to perturb the documents, which is what UC007 does. But
UC007 perturbs **claims** — text it generates itself — while here **the document is the evidence**.
Editing a federal record so that it fails a rule would mean shipping falsified public documents in
a public repo to make a metric look better. So:

- the selector takes every real breach it can find, and
- the eval **never prints a single accuracy number**. A checker that answers "met" to all 1,068
  applicable rules scores **74.2%**, which is why that number on its own is meaningless here.
  Per-class recall is the measurement, and false MET is counted separately as the expensive error.

## Two things this corpus cannot tell you

- **`Human Subjects Protection Review Board Status` is never addressed on all 30 documents.** The
  public API exposes no field carrying it. That is a fact about the API, not a finding about the
  trials, and the rule stays in the rulebook because dropping a real rule to flatter a distribution
  is how a compliance kit stops being one. The same applies to `IND or IDE Number` (0/117).
- **10 further rules are met on every document** — brief title, study type, condition, sponsor,
  org study id, record verification date and others — because the registry requires them at
  submission. "Met on every document" is the *true* answer for those rules, not a corpus defect.
