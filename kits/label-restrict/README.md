# label-restrict — read the use restrictions off a product label, and check one proposed application against them

**UC051.** Point it at a crop-protection label extract paired with one proposed application, get a
field table back — plus a decision taken afterwards in pure code that is **two answers, not one**:
may this application be made as proposed, and **which restriction settled it**.

> **⚠︎ This proposes a reading of a label. It never authorises an application.** A qualified adviser
> decides, against the approved label for the product in the territory it is being used in and the
> conditions of its registration.
> **The check set shipped with this kit (`data/checks.json`) is illustrative and is not an
> authority** — it was written for this kit and reproduces no real product label, no manufacturer's
> use instructions, no registration, no approved-use database and no regulator's guidance. Every
> product name, registration number and active substance in the corpus is coined. Replace all of it
> with your own before you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                   # free — validates the gold set
python -m evals.run --run-id b000-label-restrict-tone --baseline   # free — the tone floor
python -m evals.run --run-id t000-label-restrict-stub --stub       # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-label-restrict --yes         # THIS SPENDS MONEY: one call per case
python -m src.app                                              # the local UI on 127.0.0.1:8802
```

## The decision: a walk of eight checks with a stopping order

```
walk the eight checks in order, and STOP at the first that fires
  a check that is NOT APPLICABLE is skipped, and it passes
  a check whose value is NOT STATED  -> insufficient_information, naming that check
  a breach of checks 1-5   crop, tank mix, rate, season count, buffer
                                     -> outside_label,  naming that check
  a breach of checks 6-8   re-treatment interval, pre-harvest interval, re-entry interval
                                     -> wait_required,  naming that check
  nothing fires                      -> within_label,   deciding restriction `none`
```

Two properties of that walk are the whole difficulty.

**HARD BEATS TIMING.** A case that breaches both a hard restriction and an interval is
`outside_label`. Answering `wait_required` there tells a grower to wait a fortnight before making an
application that must not be made at all — the most expensive wrong answer this kit can give.
**4 of 52 cases** are built to test exactly that.

**EVERY LIMIT IS INCLUSIVE EXCEPT ONE.** A rate exactly on the maximum is inside the label; a
pre-harvest interval of 35 days is met by exactly 35 days to harvest; a 5 m buffer is met by exactly
5 m. But `maximum applications per season` is a **total**, so a proposal made when that many have
already been applied would be the next one and is over it. **6 cases** sit exactly on three
inclusive limits at once and are entirely inside the label; **5 cases** have used the whole season
allowance and are not.

`insufficient_information` is a first-class answer, not a failure to produce one, and it **names the
restriction it could not read**. A label extract that does not state its pre-harvest interval is
exactly the case a label check must escalate, and the kit says which one rather than inventing a
verdict or guessing at what an unstated interval probably is.

**The check set is sent with every call.** A precedence walk is a rule, and a model cannot walk a
rule it has never been shown. `src/prompt.py::check_block()` renders `data/checks.json` into the
prompt rather than restating it in prose, so the model's instructions and the gold labels cannot
drift apart about the same eight checks. On the worked example it is 1,201 of 3,558 input tokens.

## Two answers, scored separately — and the second one is the point

Every sibling kit in this series grades one guarded field. This one grades two, because on a label
check a verdict on its own is not actionable:

> `wait_required` naming the **pre-harvest interval** on a case that actually turns on the
> **re-entry interval** is right on the verdict grader and useless in the field. The grower waits
> the wrong number of the wrong unit from the wrong date.

So `evals/judge.py` counts **right verdict, wrong restriction** on its own and publishes it, never
averaged into the verdict figure where it would disappear. The corpus is built so that failure is
reachable: **20 of 52 cases turn on one of three confusable intervals** — re-treatment (days),
pre-harvest (days) and re-entry (**hours**) — and the re-entry cases deliberately put the same
numeral in the hours line and the days-to-harvest line.

## The two decoys, and where they live

Two fields are on every case, are extracted, and decide nothing:

| decoy | what it is | why it is there |
|---|---|---|
| `agronomist_note` | one person's free-text remark on the proposal | **21 of 52 cases (40.4%)** carry a note whose tone contradicts the walk — a relaxed note on a proposal that must not be made, an alarmed note on one entirely inside the label |
| `previous_season_applications` | how many applications were made **last** season | the label maximum is **per season**, so it is part of no check. **26 of 52 cases** change answer if a reader adds it to this season's count — measured by re-walking the check set, not by a proxy |

Note what `SECTION_HINTS` in `src/select.py` maps `verdict` and `deciding_restriction` to: the two
sections the checks actually read, and **neither decoy**. That is not a filter — both still reach
the model, as fields in their own right. It is the map of where the answer actually lives. What
selection genuinely saves is the `Product and Registration` section, which no field maps to and
which is therefore never sent — which also means the model is never shown one of this corpus's
coined active substances and asked to reason about it.

## What it measures

One scored run over 52 cases (`results/eval-r001-label-restrict.json`), on the fast tier.

**1,144 of 1,144 extracted cells, 52 of 52 verdicts, 52 of 52 deciding restrictions, 0 right-verdict-wrong-restriction, 0 unsafe clearances of the 38 proposals that must be stopped, 0 over-blocks, and 16 of 16 hold flags with no false alarms.** Every published figure is
perfect, on 52 calls.

**That is a reason to distrust the corpus, not to trust the model.** A corpus that nothing gets
wrong has stopped discriminating: it cannot rank two models, cannot tell a stripped prompt from a
full one, and cannot tell you which of this kit's own instructions is earning its place. Every
figure above means the run agreed with `data/checks.json` — a file this kit wrote and nobody
qualified has reviewed. See `Business.not_good_enough` on the published kit page for the full
version of this.

**And this kit measured less than the sibling it was built from.** One tier, one run, no ablation,
no red-team pass. The repeatability of that perfect score is unmeasured; so is whether a second tier
would move it; so is whether stripping the precedence rules out of the prompt would.

### The headline number is a field-safety number

The four-way verdict is collapsed onto the one distinction that decides whether a sprayer goes out:
**may this application be made as it stands, or must it not.** `not within_label` is the positive
class, and the expensive direction — a proposal the check set would have stopped that the run
cleared — is counted and named separately as `unsafe_clearance`. It was **0 of 38**.

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM extractor: eight fixed worried-sounding phrases in the agronomist's note,
no key, no cost. It is perfect on the parts that are regex work — **all twenty structured fields,
1,040 of 1,040 cells** — and a deliberate *tone floor* on the two that are not.

It scores **30.8% verdict accuracy (16 of 52)** and clears **15 of the 38 proposals the check set
would have stopped**. On the deciding restriction it scores **15.4% (8 of 52)**, and every one of
those eight is a `within_label` case it happened to call `none`. It never once names a restriction,
because a note does not carry one and no keyword list can invent it — so **8 of its 38 nameable
cases (21.1%) are right verdict, wrong (absent) restriction**, against 0 on the scored run. That
gap is the clearest single statement of what this kit's second grader is for.

And note what a tone read cannot reach *at all*: `wait_required` and `insufficient_information` are
the two verdicts that carry the actual work of a label check — "this may be fine in eighteen hours"
and "nobody can say from this page" — and no amount of reading a note produces either. **20 of 52
cases have a verdict the floor is structurally incapable of saying.** Tone can express alarm; it
cannot express a requirement, and it certainly cannot name which of eight restrictions is the
problem.

Its own hold flag inherits the damage: it reads `application_status` correctly by regex every single
time and still scores **9 of 16 with 3 false alarms**, because the flag reads a tone-derived
verdict. A business-condition guardrail is only ever as good as the field it reads.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` settles it — with numeric comparison on the
fourteen number fields, because a reply returning `3` where gold holds `3.0` has read the page
correctly and formatted it differently. The verdict is a rule walk, which is the one thing you
should never ask a model to adjudicate.

## Spans are anchored to the line, not to the section

Eight numeric restrictions share one section here. A section-scoped search for the buffer `5`
matches the `5` inside `2.5 L/ha` two lines above it — on a word boundary, correctly by the regex
and wrongly by every other measure. The span would point a reader at the rate line and invite them
to check a citation that appears to hold.

So `data/fields.json` carries the label **line** each field is stated on, and
`src/extract.py::_locate` anchors to that line first. A value that is not on its own line is
returned **without** a span rather than with a plausible wrong one. All 19 spannable fields located
on all 52 cases in the scored run.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the check set and the whole walk beside the verdict |
| the check set | `data/checks.json` → `src/checks.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py`, `evals/prompt_tokens.py` |

## The walk is served, not just its answer

`/api/extract` returns the state of **every** check — pass, breach, not applicable, not stated — not
only the one that fired, and the UI prints all of them with the remaining count named when the walk
stopped early. A verdict with one restriction under it is a claim; the same verdict with all eight
states beside it is something a reader can audit in ten seconds. That panel is the reason the
"right verdict, wrong restriction" number is worth publishing rather than hiding: it is the number,
and this is where somebody catches it happening.

## Point it at your own labels

Replace `data/checks.json` **first** — it is this kit's own construction and resembles no real
label. Then replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record
per case. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different layout; when it does not match, selection falls back to the whole document —
slower, more expensive, always correct. The `line` key in `data/fields.json` will need editing too,
and a field with no `line` falls back to a section-scoped search.

If your cases are unlabelled — the normal case — the field grade and the confusion matrices go away,
and the **consistency diagnostic** does not: `evals/judge.py` re-walks the check set over each
reply's own extracted values and counts the replies whose stated verdict *or* stated restriction
disagrees with it. No gold needed. On the free floor it caught 36 of its 44 answer errors with no
labels at all. It is blind to a reply that misreads a number and then walks the checks correctly
from the misreading, and it is reported as a diagnostic rather than as this kit's guardrail.

## What it does not do

It never authorises an application, never withdraws or releases a crop, never contacts anybody, and
it is not a substitute for the approved label or a qualified adviser's judgement. It reads one label
extract at a time. It does not know the growth stage, the soil, the slope, the nozzle, the boom
height or the weather. It cannot handle a rate or an interval that differs by crop on the same label
— this shape has one value per restriction. It does not know whether the label copy in front of it
is the current approval. It does no OCR — scanned or photographed labels extract no text, and a real
label very often arrives as a scan. No auth, no database, no multi-tenancy, no deployment story. It
runs once per model, locally, and that run is what gets published.
