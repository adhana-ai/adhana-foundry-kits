# option-clock — read a rights register and say which options are about to lapse

**UC050.** Point it at one property's rights-and-option register snapshot, get a field table back —
plus an expiry date and a status **counted afterwards in pure code**: which options have lapsed,
which are lapsing inside the window, which are live, and which the paperwork does not settle.

> **⚠︎ This proposes a worklist. It watches nothing.** It reads ONE snapshot that somebody else
> assembled, on the date that snapshot states. **It does not poll, subscribe, schedule, alert,
> escalate, file, exercise, renew, lapse or clear anything, and nothing in it runs unattended.**
> A qualified person reads the executed agreement.
> **The counting rulebook shipped with this kit (`data/rulebook.json`) is illustrative and is not an
> authority** — it was written for this kit and reproduces no option agreement, standard form,
> rights-management system's logic, guild or trade-body schedule or statute. Replace it with your
> own before you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                   # free — validates the gold set
python -m evals.run --run-id b000-option-clock-register --baseline   # free — the status-column floor
python -m evals.run --run-id t000-option-clock-stub --stub     # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model> --yes                # THIS SPENDS MONEY: one call per register
python -m src.app                                              # the local UI on 127.0.0.1:8843
```

## "Monitoring" here is a snapshot, not a daemon

This is the first kit in the estate for the **monitor** pattern, and the first thing to say about it
is what it is not. There is no scheduler, no poller, no queue, no subscription and no state between
documents. **The monitoring snapshot is the document**: one property's register as it stood on one
day, carrying the obligations that apply to it, what has actually happened so far, and what somebody
last typed in the status column. The kit answers one question about it —

> **which of these options needs action, by when, and which ones cannot be determined from what is
> on the page?**

— and hands the answer back. Everything a real monitoring system does around that (when to look,
what to do next, who to tell) is outside it and stays outside it.

## The model reads. The code counts.

That split is the whole shape of the kit and it is not a stylistic choice. A due date is arithmetic,
and arithmetic done in prose is arithmetic nobody can check. The model returns seventeen fields;
`src/rulebook.py::decide()` then does the counting in pure code, and **the counted answer is the one
this kit publishes**. The model's own `expiry_date` and `status` come back too, and the gap between
them and the count is the no-gold consistency diagnostic.

It earned that split on the first scored run. On `ROR-0033` the model clamped a 29th-of-the-month
start into February correctly and then added the extension's 6 months instead of the initial term's
18 — putting the expiry a year early and calling an option with six months left `lapsed`, next to a
clerk's note reading *"Chased the file twice and I am not confident the dates on it are settled."*
**Left to the model that is a false alarm with a plausible-looking corroboration beside it.** The
code counted `2027-02-28` and `live`. And the same register re-asked once afterwards came back
correct (`results/example-ROR-0033.json`): same prompt, same tier, same document, different
arithmetic.

## The count: four steps, in this order

```
1. WHAT STARTS THE CLOCK
     triggering_event, not occurred        -> not_determinable   (nothing to count from)
     grant_date, two entries disagreeing   -> not_determinable   (do not break the tie)
     otherwise                             -> the trigger date, or the grant date
2. WHICH EXTENSIONS COUNT
     payment-controlled: a payment reference AND a payment date must both be recorded
     notice-controlled:  notice must be served on the GRANTOR OF RECORD
     anything else recorded as exercised   -> does not stack
3. ADD THE MONTHS, consecutively from the clock start, one calendar step, clamped short months
4. COMPARE against the register's as-of date and the 45-day window
     expiry <= as_of -> lapsed    inside the window -> lapsing    beyond it -> live
```

`not_determinable` is a first-class answer, not a failure to produce one. An option whose clock
nobody can start is exactly the record a monitoring queue must escalate, and the kit says so rather
than inventing a date.

**The rulebook is sent with every call.** `src/prompt.py::rulebook_block()` renders
`data/rulebook.json` into the prompt rather than restating it in prose, so the model's instructions
and the gold labels cannot drift apart about the same count. On the worked example it is 1,039 of
3,292 input tokens.

## The two decoys, and where they live

Two fields are on every register, are extracted, and decide nothing about the count:

| decoy | what it is | why it is there |
|---|---|---|
| `register_status` | the **status column** — what somebody last typed | it is wrong on **29 of 50 registers**: 25 carried `live` that are not, 4 carried `lapsed` that are live. And note what it cannot do even when it is right: two values cannot express "lapsing inside the window" or "the paperwork does not settle it", which is **19 of 50** |
| `clerk_note` | one person's remark on the file | **20 of 50 (40%)** carry a note whose tone contradicts the count — a relaxed note on a lapsed option, a worried one on an option with two years to run |

Note that `register_status` **is** an input to the escalation flag, and is deliberately not an input
to the count. Reading a field for what it is evidence *of* — the desk's current belief, not the
arithmetic — rather than trusting or ignoring it wholesale, is the distinction this kit is built
around. `SECTION_HINTS` in `src/select.py` maps `status` to the eight facts the count actually reads
and to **neither decoy**. That is not a filter — both still reach the model as fields in their own
right. What selection genuinely saves is the `Filing History` block, which no field maps to and
which is therefore never sent.

## The five hard cases, each measured rather than asserted

`evals/check_labels.py` asserts a floor on every one of these before any run may spend, and fails
the run if a floor is not met.

| case | why a careless reader gets it wrong | registers |
|---|---|---|
| **"recorded: exercised" is not a perfected extension** | the entry is a clerk's; the payment or the notice is the act. Count the entry and every one of these reads `live` — asserted directly, not hoped for | 9 |
| **a clock that has not started is not a long time left** | reading it as `live` removes a row from the worklist and looks like good news | 5 |
| **a contradicted grant date is not settled** | and the rule explicitly forbids picking the earlier, the later, or the more official-looking source | 4 |
| **…but only where the clock runs from it** | the same disagreement on a triggering-event clock that has started changes nothing. Flagging it is a **false alarm** | 3 |
| **the short-month clause, exercised** | a 29th, 30th or 31st that cannot survive the addition | 6 |

## What it measures — and the number that matters most

Four things are scored separately and never folded together, because in a monitoring kit they fail
for different reasons and cost different amounts.

**`r001-option-clock`, 50 registers, one tier:**

| | |
|---|---|
| field extraction | **848 of 850 cells** (99.76%), 0 invented values, 458 of 458 spannable values located |
| status verdict, four-way | **50 of 50** — every `live`, `lapsing`, `lapsed` and `not_determinable` |
| **false-alarm rate** | **0 of the 17 options that are genuinely live** were put on the worklist |
| **missed lapses** (reported live) | **0 of the 33** that need somebody |
| date arithmetic | **41 of 41** counted expiries exact, 0 phantom expiries |
| escalation flag | **25 of 25** fired, 0 false alarms |

⚑ **The false-alarm rate is in the headline and not in a footnote, and that is the point of a
monitor kit.** A queue that cries wolf is worse than no queue, because a person has to clear every
row on it and the second week they stop reading it. The expensive error is the other direction — an
option wrongly reported `live` is an option nobody opens until somebody tries to exercise it — so
both are named, both have their own denominator, and neither is averaged into an accuracy figure
where it disappears.

The two cells the extraction grade lost were the model's **own** `expiry_date` and `status` on
`ROR-0033`. Every field the count actually reads was exact on all 50 registers.

## The free floor is the shortcut a desk actually takes

`--baseline` is a non-LLM extractor that **reads the status column and escalates on a worried clerk
note**, and counts nothing. That is what a spreadsheet with a status column and a comments column
gives you today, for free, on any desk.

It is near-perfect on the parts that are regex work — **15 of 17 fields exact, 770 of 850 cells** —
and it fails where counting starts:

| | |
|---|---|
| status accuracy | **40%** (20 of 50) |
| **false-alarm rate** | **47.06%** — 8 of the 17 live options put on the worklist |
| missed lapses | **33.33%** — 11 of the 33 that need somebody, reported live |
| date arithmetic | **0 of 41.** A status column has no due date in it at all |
| escalation flag | 14 of 25 fired, 4 false alarms, 11 missed |

And note what a two-value column cannot reach **at all**: `lapsing` and `not_determinable` are the
two answers that carry the actual work of a monitoring sweep — "this one needs somebody this month"
and "nobody can say from this file" — and no amount of reading a status column produces either.
**19 of 50 registers have a status the floor is structurally incapable of saying.**

Making the floor perfect would take one line — it already regexes every value the count needs.
Not doing so is the design: the gap it opens is the gap between reading a status column and doing
the arithmetic.

## The no-gold diagnostic earns its place here

`evals/judge.py` re-runs the count over each reply's **own** extracted values and counts the replies
whose stated status disagrees with it. No gold needed. On the free floor it caught **26 of its 30
status errors with no labels at all**; on the scored run it caught the one arithmetic slip the model
made. It is blind to a reply that misreads a date and then counts correctly from the misreading, and
it is reported as a diagnostic rather than as this kit's guardrail.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` with light normalisation settles it — and the
answer is a date and a comparison, which is the last thing you should ask a model to adjudicate.

⚠︎ And the scorer was **not** changed after the run to be kinder. The first pass returned a
typographic apostrophe where the register writes a straight one, and the normalisation was
deliberately left alone: a scorer changed after a run to accept an answer it has just rejected is a
scorer written to the result.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the count |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## What the calibration bought, and what it did not

Six registers were fired at `max_tokens=16000` before any scored run. It measured the ceiling
(largest reply 1,104 output tokens, 78.2% of it provider-side reasoning) and it caught an ambiguous
field hint that 3 of 6 replies tripped over.

**And the ceiling it measured was wrong.** `MAX_TOKENS` was set to 6,000 — 5.4x the largest reply
the calibration had seen — and the first 50-register pass **lost `ROR-0026` outright** to
`finish_reason=length` at exactly 6,000 tokens, on a run whose largest surviving reply was 5,456.
A six-document calibration measures the middle of a distribution and tells you nothing about its
tail, and on a monitoring worklist a register with no status is indistinguishable from a register
nobody read. The cap is 16,000 now; the superseded pass is committed at
`results/eval-r000-option-clock-ceiling.json` rather than deleted.

## Point it at your own registers

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
register. **Replace `data/rulebook.json` first** — it is this kit's own construction and reproduces
no agreement anybody signed. `SECTION_HINTS` in `src/select.py` maps fields to section headings and
**will** need editing for a different register layout; when it does not match, selection falls back
to the whole document — slower, more expensive, always correct.

If your registers are unlabelled — the normal case — the field grade and every confusion matrix go
away, and the **consistency diagnostic** does not.

## What it does not do

It never exercises, renews, lapses, releases or files anything, never contacts anybody, and it is
not a substitute for the executed agreement or a lawyer's reading of it. It reads one snapshot at a
time and watches nothing between them. It does not know whether anybody still wants the property, or
what exercising would cost. It cannot see a side letter that varies the agreement without appearing
on the register, an extension chain whose extensions are different lengths, a term stated as "the
later of" two dates, a notice served late rather than on the wrong party, or a payment made in the
wrong amount. It does no OCR — scanned or image-only registers extract no text. No auth, no
database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run is
what gets published.
