# docs-redline — compare two versions of a document, flag what materially changed

**UC005.** A rule and its own later correction go in, paired by the publisher's Regulation ID
Number. The two texts are aligned by pure code first; the model sees only the one span that
changed and answers one question — **material or editorial**. There is no publisher label to
score that against, so this kit does not claim accuracy. It claims **agreement**: run the same
question through two independent models and measure how often they land on the same verdict.
Where they disagree is the actionable output — that is the pair a person needs to look at.

Runs on a laptop. Standard library only. One model call per pair.

```bash
cp ../../.env.example ../../.env      # one shared connection for every kit; per-kit .env optional
python -m tools.fetch_corpus          # free — pulls rule/correction pairs from the Federal Register API
python -m tools.build_corpus          # free — builds the corpus, keeps the two versions separate
python -m evals.run --run-id b000 --baseline regex   # free — the thing a model has to beat
python -m src.app                     # the local UI, http://127.0.0.1:8769
python -m evals.run --run-id t000 --stub              # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>              # THIS SPENDS MONEY: one call per pair
python -m evals.run --run-id r002-<model-2>             # a second, DIFFERENT model — required, see below
python -m evals.compare --a r001-<model> --b r002-<model-2>   # free — the agreement score
```

## The question this kit exists to answer

Not "is the model right about what changed" — there is no publisher-assigned answer to be right
against, and pretending otherwise would mean grading the model against our own guess dressed up
as ground truth. The real question: **when two independent models read the same change, how
often do they agree**, and **is a free regex over the surface text agreeing with them just as
often** — because if it is, the model is not adding judgment, only cost.

## Why a rule and a correction, not a proposed rule and a final rule

Federal Register documents that share a Regulation ID Number track one regulatory action through
its life — proposed, final, and any later correction. A proposed-to-final pair changes the most
(the whole comment-and-revision process happens in between) but has no clean single point of
comparison. A rule-to-correction pair changes at exactly one point, described in the correction's
own abstract, which is what makes "align the two texts, then judge the one span that differs" a
well-posed pipeline instead of an open-ended diff.

## What this kit is not

It does not read the full legal text of either document — like docs-route, it works at
title + action + abstract, the fields the Federal Register API returns without a second fetch.
A correction whose substance lives only in the body text will show no detectable change here and
is skipped at the corpus boundary, counted, not hidden — see `Data.breaks_on` on the published kit.
