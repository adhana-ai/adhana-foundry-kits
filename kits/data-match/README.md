# data-match — is this one customer entered twice, or two customers who look alike?

Any list that people typed into holds the same person more than once. She books as **Kathryn A.
Muller**, phones back a year later and is entered as **Kate Muller** — and now two customers are one
person: two renewal letters, a churn number that is wrong, and no single history when she complains.

This kit takes two records, decides **same** or **different**, and merges only the pairs that clear a
threshold you set. Insurers do it to claimants, banks to account holders, retailers to loyalty
accounts, hospitals to patients.

```bash
python3 tools/build_corpus.py      # the corpus, byte-identical every time, MIT
python3 -m evals.check_labels      # refuses a label set that cannot be scored honestly
python3 -m evals.baseline          # a WORKING matcher, measured. 0 model calls, $0.00
python3 -m src.app                 # the panel — http://127.0.0.1:8011
```

**No key is needed for any of that.** Only `evals/run.py` and the app's *Judge* button call a model.

## Why "just compare the text" does not work

Because it is wrong in **both** directions, and the two mistakes cost different amounts.

| | record A | record B | text says | truth |
|---|---|---|---|---|
| Same person, spelled differently | Kathryn A. Muller · 88 Ferndale **Rd** · k.muller@ | Kate Muller · 88 Ferndale **Road** · kmuller@ | *different* | **same** |
| Different people, identical fields | J. Smith · born **1985** · 5 Larch Ave Apt 2 | J. Smith · born **1961** · 5 Larch Ave Apt 2 | *same* | **different** |

A model can know that Kate is short for Kathryn and that Rd is Road — facts about the world, not about
strings. It will also merge the father and the son, confidently. That is why this kit publishes where
it fails, not only where it wins.

⚑ **Merging is one-way.** Leaving a duplicate is annoying and somebody fixes it next quarter. Fusing
two real customers destroys records that **cannot be un-merged**. So the two mistakes are counted apart
and never averaged into a single score — you will not find an F-score anywhere in this kit.

## The free floor, measured — read this before any model number

`evals/baseline.py` scores weighted string similarity at nine thresholds, through the **same scorer**
the model's answers go through. On 78 candidate pairs (60 same / 18 different):

| threshold | precision | recall | false merges | missed |
|---|---|---|---|---|
| 0.70 | 76.9% | 100.0% | **18** | 0 |
| 0.80 | 85.3% | 96.7% | 10 | 2 |
| 0.85 | 89.8% | 88.3% | **6** | 7 |
| 0.90 | 87.5% | 70.0% | 6 | 18 |
| 0.95 | 76.9% | 33.3% | 6 | 40 |

⚑ **No threshold avoids a false merge — that is the finding, and it is what makes the kit worth
running.** At every setting the free matcher fuses the 12 `relative` pairs and the 6 `twin` pairs,
because every field it can compare agrees. There is no way to deduplicate this corpus safely by string
comparison, so there is a real gap for a model to close and a clear definition of closing it: keep the
nicknames and abbreviations merging, stop merging the relatives and the twins.

## What the model is asked, and what it may answer

`src/prompt.py` is the single source of the vocabulary — the prompt, the parser and the scorer all read
it from there. **Three verdicts**, and the third is not optional:

| verdict | means |
|---|---|
| `SAME` | one entity, entered twice — safe to merge |
| `DIFFERENT` | two entities that resemble each other — must stay apart |
| `UNSURE` | the fields do not settle it; hand it to a person |

`UNSURE` exists because the corpus contains a pair no field can settle — twins at one address with one
date of birth — and the right answer there is to say so rather than guess.

⚠︎ **`UNSURE` is not the same as no answer.** A model that says UNSURE has read the pair and declined. A
model that returns an empty string has failed. They are counted apart, and an empty reply is **never**
scored as "keep apart" — that would convert a reliability failure into a quality figure.

## The five outcomes, and why none of them collapses

| outcome | what it is |
|---|---|
| `merged_correct` | merged, labels agree |
| `false_merge` | **merged two different entities** — destroys data, cannot be undone |
| `missed_match` | kept apart, labels say same — a duplicate survives |
| `apart_correct` | kept apart, labels agree |
| `no_verdict` | nothing usable came back |

They reconcile against the pair count, so a silent model cannot be scored as a careful one.

## Where it breaks

**Pair count, not context window.** Comparing everything with everything is n(n−1)/2: 288 records is
41,328 pairs, 50,000 records is 1.25 **billion**. `src/block.py` cuts that to pairs sharing a cheap key
— here **128 candidate pairs, a 99.7% reduction, with blocking recall 1.0** on this corpus. Blocking is
also the step that can silently lose true matches, so its recall is measured and published beside every
score: a pair that is never generated can never be judged, and no model quality recovers it.

**The corpus is invented,** so it holds the eight traps we thought to plant and no others. A real
customer list will contain kinds of mess this set does not. See `data/SOURCES.md`.

**Nicknames are not in the normaliser, on purpose.** `src/normalise.py` knows that `Rd` is `Road`; it
does **not** know that Kate is Kathryn. Teaching it would raise the free floor, shrink the measured gap,
and report the model as less useful than it is — moving work across the line without saying so.

## The seams

| seam | file | swap it for |
|---|---|---|
| the model | `src/adapters/__init__.py` | any provider; `.env` plus the same run again |
| the comparer | `src/similarity.py` | `recordlinkage`, `dedupe`, `splink` — anything better than difflib |
| the blocker | `src/block.py` | more keys, or a real index; measure recall after |
| the decision | `src/decide.py` | a different threshold, or a review queue instead of a merge |

MIT. Part of [adhana-ai/adhana-foundry-kits](https://github.com/adhana-ai/adhana-foundry-kits).
