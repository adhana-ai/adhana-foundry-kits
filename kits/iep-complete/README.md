# iep-complete — name every component that is missing, or present but not measurable

**UC057.** Point it at an individualised education plan, get a state back for every component in
the shipped rulebook — plus a worklist decision taken afterwards in pure code: does somebody have to
open this plan, and is a pupil already being taught against it?

> **⚠︎ This produces a reviewer's worklist. It never approves, signs, files or amends a plan.**
> Nothing here is a decision about a pupil; the team that writes the plan decides what goes in it.
> **The component rulebook shipped with this kit (`data/rulebook.json`) is invented and is not an
> authority** — it was written for this kit and reproduces no statute, no regulation, no state or
> district plan template, no agency guidance and no published checklist, and its transition age of
> 14 is a number this kit chose. Replace it with your own before you review anything real by it.
> **Every plan in `data/corpus/` is generated.** No real pupil, school or district appears anywhere:
> no names, no dates, no dates of birth, no diagnosis and no eligibility label. Each file says so on
> its own first line. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                  # free — validates the gold set
python -m evals.run --run-id b000-iep-complete-checkbox --baseline
                                                              # free — the checkbox-review floor
python -m evals.run --run-id t000-iep-complete-stub --stub    # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model> --yes               # THIS SPENDS MONEY: one call per plan
python -m src.app                                             # the local UI on 127.0.0.1:8957
```

## The thing this kit is actually for

A completeness check on a plan has two halves and they are nothing like each other.

**An ABSENT section is easy.** The heading is not there. Any checklist catches it, and this
repository's free floor (`evals/baseline.py`) catches **26 of 26** of them without a model.

**A section that is PRESENT AND CANNOT BE MEASURED AGAINST is hard.** A goal with no baseline, no
criterion or no measurement method is a heading with prose under it. It passes every checkbox
review, the box gets ticked, and a year later nobody can say whether the goal was met. The free
floor waves through **32 of 32** of them, by construction — that is what a checkbox review *is*.

That gap is the whole kit. Everything else here exists to make it a number.

| | the checkbox floor | one model call |
|---|---|---|
| absent components missed | **0 of 26** | **0 of 26** |
| **present-but-unmeasurable waved through** | **32 of 32 (100%)** | **2 of 32 (6.25%)** |
| false defects raised on sound components | **14 of 306** | **0 of 306** |
| plan outcome, four-way | 32 of 52 (61.5%) | **52 of 52 (100%)** |
| plans needing work that were cleared | **20 of 40** | **0 of 40** |

## Two vocabularies, and keeping them apart is the design

**A COMPONENT STATE** describes one section of the plan. `absent`, `present_not_measurable`,
`present_complete`, `not_required`. It is declared once, in `src/prompt.py` as `VERDICTS` /
`VERDICT_MEANINGS`, and the prompt, the parser, the scorer and the published app panel all read it
from there.

**A PLAN OUTCOME** describes the plan those seven sections add up to, and is computed from them in
pure code by `src/rulebook.py::decide()` — four checks, stopping at the first that fires:

```
decide(component_states, pupil_age):
    any REQUIRED component absent                    -> components_missing
    any REQUIRED component present-and-unmeasurable  -> not_measurable
    no age stated AND transition not present-complete -> undetermined
    otherwise                                        -> complete
```

`undetermined` is a first-class answer, not a failure to produce one, and it means something narrow
and useful: *this plan is otherwise complete, and nobody can tell whether it needed transition
content, because the age is not on it.* Go and find the age.

⚠︎ **Why `undetermined` is third and not first.** The sibling kit this shape was taken from puts its
unknown first, because an unrecorded prior cargo makes every later check unanswerable. Here a
missing age makes exactly *one* component unanswerable and leaves the other six perfectly readable —
so reporting `undetermined` ahead of a genuinely absent section would hide a defect the reviewer can
act on today behind one they cannot.

**The rulebook is sent with every call.** A completeness check is a lookup against somebody's list of
required elements, and a model cannot look up a list it has never been shown.
`src/prompt.py::rulebook_block()` renders `data/rulebook.json` into the prompt rather than restating
it in prose, so the model's instructions and the gold labels cannot drift apart about the same rule.
Measured: 983 of 3,594 input tokens (27%) on the worked example, and the four states cost another
241.

## The two decoys, and where they live

Two fields are on every plan, are extracted, and decide nothing:

| decoy | what it is | why it is there |
|---|---|---|
| `checklist_claim` | a **previous reviewer's own tick-box result**, printed on the plan | it is the checkbox review this kit exists to go past. **18 of 52 plans** carry a checklist claiming every required component is present while the rulebook finds a defect |
| `case_manager_note` | one person's free-text remark before the meeting | **21 of 52 plans (40%)** carry a note whose tone contradicts the outcome — a reassuring note on a defective plan (15), a worried note on a sound one (6) |

Note what `SECTION_HINTS` in `src/select.py` maps `plan_outcome` to: the seven component sections
and the pupil's age, and **neither decoy**. That is not a filter — both still reach the model, as
fields in their own right. It is the map of where the answer actually lives. What selection
genuinely saves is the `Synthetic Record` banner and the `School and District` section, which no
field maps to and which are therefore never sent.

## The four hard cases, each measured rather than asserted

`evals/check_labels.py` asserts a floor on every one of these before any run may spend, and fails
the run if a floor is not met.

| case | why a careless reader gets it wrong | plans |
|---|---|---|
| **present is not the same as complete** | every section is there; a goal states no baseline, no criterion or no measurement method. A checkbox review passes it outright | 20 |
| **the checklist's own claim is not evidence** | a tick-box sheet says every component is present, and the rulebook finds one absent or unmeasurable | 18 |
| **transition is conditional on the pupil, not the plan** | no transition section, and that is CORRECT below the rulebook's age. Asserted directly: the same document read for an older pupil must come out `components_missing` | 5 |
| **the defective goal is not always the first one** | the section opens with a sound goal and breaks a later one. A reader who checks goal 1 and stops scores as one who read the section | 5 |

## What it measures

One scored run over 52 plans (`results/eval-r001-iep-complete.json`), one call per plan, 12
concurrent workers, 46.4 seconds of wall clock.

**726 of 728 extracted cells, 362 of 364 component states, 52 of 52 plan outcomes, 20 of 20 worklist
flags with no false alarms, 200 of 200 spans, 0 hallucinations — and 2 present-but-unmeasurable
components waved through.**

**Those two are the interesting number on this page**, and they are the same failure twice:

> `accommodations` on IEP-0013 and IEP-0016. Both plans list an accommodation with no setting
> attached beside one that has a setting — *"Extended time, 1.5x, on written assessments."* and
> *"Text-to-speech for reading passages."* — and the run read the trailing phrase as the setting.
> That is an arguable reading of an accommodation name and an unarguable failure against the shipped
> rulebook, which asks for a setting *per accommodation*. It is this corpus's weakest construction
> and the run's only miss, and the two facts are the same fact.

**And the plan-level number hides both of them.** Outcome accuracy is 52 of 52 *because* each of
those two plans already carried another defect, so the outcome was unchanged by the miss. A kit that
published only the plan-level figure would have reported a clean sweep over a corpus it got wrong
twice. That is why the component state is scored on its own, and why `passed_unmeasurable` is in the
headline rather than a footnote.

## The floor is shipped, including exactly what it cannot say

`--baseline` is a non-LLM extractor: it finds each component's heading, checks the body is not a
placeholder, and ticks the box. No key, no cost. It is **perfect on every absent component** —
26 of 26 — and it is structurally incapable of two of the four states.

It scores **87.36% on component states** and **61.54% on plan outcomes**, and it clears **20 of the
40 plans that need somebody to open them**. Two things about it are worth more than the headline:

1. **It waves through every unmeasurable component, all 32.** Not because the keyword list is
   weak — because counting headings cannot see inside one. Tone can express alarm; a checklist can
   express presence; **neither can express a requirement.**
2. **It raises 14 false defects, and every one of them is the same one:** the missing transition
   section on a plan whose pupil is below the rulebook's threshold, where the component was never
   required. On a worklist that is 14 rows a person has to clear for nothing, and it is the
   commonest way a completeness check loses its reader.

**Making the floor better would take two lines** — it already parses the age perfectly, and the goal
blocks are labelled. Not doing so is the design: the gap it opens is the gap between counting
sections and reading them.

## The consistency diagnostic, and the thing it cannot see

`evals/judge.py` re-runs the rulebook over each reply's *own* seven states and counts the replies
whose stated outcome disagrees with it. No gold needed, so a forker can compute it on unlabelled
plans.

⚠︎ **On this kit it caught 0 of the floor's 20 outcome errors**, and that is not a defect in the
diagnostic — it is the honest limit of the whole idea. The floor is *perfectly self-consistent*: it
reads a section wrongly and then computes the outcome flawlessly from that reading. The same is true
of the model's two misses. **A self-consistency check is blind to exactly the failure this kit cares
about most**, and a sibling kit whose shortcut was a *tone* read got the opposite result — 35 of 35
caught — which is what made this one worth measuring rather than assuming.

## There is no LLM judge in this kit

Gold is exact and an answer is one value per cell, so `==` with light normalisation settles it — and
the outcome is a rulebook lookup, which is the one thing you should never ask a model to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the answer |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## Point it at your own plans

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per plan.
**Replace `data/rulebook.json` first** — it is this kit's own construction and reproduces no rule
anybody wrote. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different plan layout.

⚠︎ **And read `src/select.py` before you change it.** Every sibling kit falls back to the whole
document when a field's section is not found: slower, more expensive, always correct. Here that
would be *wrong* — an absent section is the finding, half this corpus is missing at least one, and a
per-field fallback would fire on all of them. The fallback lives one level up instead, and only
fires when nothing matched at all.

## What it does not do

It never approves, signs, files or amends a plan, never schedules or attends a meeting, never
contacts anybody, and it is not a substitute for the team that writes the plan. It reads one plan at
a time, in plain text, with headings it recognises. It does no OCR — scanned or image-only plans
extract no text. It does not know whether a goal is the *right* goal, whether a service is
appropriate, or whether a stated baseline is accurate; it knows only whether the plan states the
things the shipped rulebook asks for. It has no view on eligibility, on placement, or on anything
about a pupil. No auth, no database, no multi-tenancy, no deployment story. It runs once per model,
locally, and that run is what gets published.
