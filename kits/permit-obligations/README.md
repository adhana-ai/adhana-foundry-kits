# permit-obligations — which permit obligations need action, by when, and which cannot be determined

**UC049.** Point it at one site's permit obligation register and get a row per condition back — plus
a status decided afterwards in pure code: overdue, due inside the action window, not yet due, does
not bind at all, or *cannot be determined from what is recorded*.

> **⚠︎ THIS KIT WATCHES NOTHING.** It reads one snapshot that somebody else assembled, as at the
> register date printed on it, and proposes a worklist. It does not poll, subscribe, schedule,
> alert, escalate, file, submit, renew or clear. Nothing in it runs unattended, and nothing in it
> continues after the call returns.
>
> **⚠︎ It proposes a status. It never files or clears anything.** A qualified person reads the
> permit. **The obligation rulebook shipped with this kit (`data/rulebook.json`) is illustrative and
> is not an authority** — it was written for this kit and reproduces no permit, licence condition,
> regulator's guidance or statutory schedule. Replace it with your own before you put a single
> obligation on a worklist by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once.

```bash
python -m evals.check_labels                                    # free — validates the gold set
python -m evals.run --run-id b000-permit-obligations-flag --baseline   # free — the register-flag floor
python -m evals.run --run-id t000-permit-obligations-stub --stub       # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model> --yes                 # SPENDS: one call per register
python -m evals.ablate --run-id a001-<model> --yes              # SPENDS: is the rulebook block earning its tokens?
python -m src.app                                               # the local UI on 127.0.0.1:8853
```

## What a monitor kit is here

`monitor` is the pattern in this estate with no prior kit, so this one had to settle what the shape
is. It is not a daemon, a stream or a dashboard: **a monitoring snapshot is the document.** Each of
the 50 registers is one site's current state at one moment — the conditions that bind it, the
intervals they run on, what the record shows has been done, and enough noise that the answer is not
a template fill. The model reads it and returns structured fields. **Pure code, never the model,
then decides the status.**

## The decision: five checks with a stopping order

```
status(register_date, obligation):
    no readable register date, unknown state, unknown type      -> not_determinable
    superseded by an amendment, or waived in writing             -> not_binding   (dates irrelevant)
    event-triggered and the trigger has NOT occurred             -> not_yet_due   (a recorded fact)
    event-triggered and the register does not say                -> not_determinable
    cycle type with no last-done date                            -> not_determinable
    annual report with no reporting period credited              -> not_determinable
    -- otherwise derive the due date --
      cycle:            last_done + the type's interval (90 / 180 / 365 days)
      annual report:    31 March of the year after the year AFTER the period credited
      event-triggered:  the due date the register states
    due date before the register date                            -> overdue
    due date within the TYPE'S OWN action window (30, or 60)     -> due_in_window
    beyond it                                                    -> not_yet_due
```

`not_determinable` is a first-class answer, not a failure to produce one. **A monitor that never
says "cannot determine from this record" is not being cautious, it is guessing** — and on a
monitoring queue a confident wrong "clear" is the failure that actually hurts. 26 of the 268
obligations here are `not_determinable`, and how often the kit reaches for it correctly is a
published number rather than a class hidden inside an accuracy figure.

`not_binding` is the fifth status and it earns its place. Calling a superseded condition "not yet
due" is a lie a reader acts on later, because it will never be due — and folding those rows into the
worklist is the single easiest way to make a monitoring queue cry wolf.

## Four numbers, scored separately, and the fourth is the headline

| what | why it is its own number | r001 |
|---|---|---|
| field extraction | the reading half, comparable to every other kit in this series | **2,294 of 2,294 cells** |
| status verdict, five-way | the deciding half — what the pure-code rule computes from what was read | **268 of 268** |
| **date arithmetic** | an obligation found but mis-dated is a different failure from one missed | **172 of 172 derived due dates** |
| **FALSE-ALARM RATE** | ⚑ **the number that matters most in a monitor kit** | **0.0% — 0 of the 126 obligations it raised did not need to be there** |

And its mirror, published beside it and never averaged into it: **0 missed actions** of the 126 that
need one.

**Why the false-alarm rate is the headline.** A monitoring queue that cries wolf is worse than no
queue, because a person has to clear every row on it by hand and that cost falls on them every
single day. An accuracy figure hides it: a run can be 95% accurate and still fill a worklist with
rows that should never have been on it, and the person clearing them has no way to tell which.

## The two decoys, and where they live

Two things are on every register, are extracted, and decide nothing:

| decoy | what it is | why it is there |
|---|---|---|
| `register_flag` | the **site's own** self-assessment of the row: `on track` / `attention` / `closed` | it is written by the party whose obligations are being checked. **107 of 268 rows (40%)** carry a flag that contradicts the rulebook — an overdue condition marked `on track`, a superseded one marked `attention` |
| `last_done` on an annual report | the date the last filing went in | only `period_credited` decides a report's status. **22 rows** are overdue while showing a filing dated inside the last 90 days |

The `Register Note` — the site's own summary compliance position — is mapped by nothing in
`src/select.py` and is **never sent to the model at all**. That is the one part of selection a reader
can point at; the rest of the saving is real but invisible.

## The trap that has two directions

The action window is **60 days for a financial assurance and 30 for everything else**, because
re-lodging a security is arranged with a third party and 30 days is not enough notice. So an
obligation falling due in 45 days is *inside* the window if it is a security and *outside* it if it
is a reading. **13 financial assurances and 17 readings/inspections on this corpus fall due 31–60
days out** — the same distance to the day, opposite answers. A reader who flattens the window to one
number gets both classes wrong, in opposite directions: false alarms on the readings, missed
renewals on the securities. `evals/check_labels.py` puts a floor on both before any run may spend.

## What it measures

One scored run over all 50 registers (`results/eval-r001-permit-obligations.json`), on the fast
tier: **2,294 of 2,294 extracted cells, 268 of 268 obligation rows found with 0 invented, 268 of 268
statuses, 172 of 172 derived due dates, 26 of 26 `not_determinable` calls with no false ones, 0
false alarms and 0 missed actions, and 31 of 31 escalations with no false alarms.**

**That is a reason to verify harder, not to trust more**, and this kit did. The model here never
computes a status, so the rulebook block riding in every call — **458 of 2,223 input tokens on the
worked example, 20.6%** — describes a calculation the model is explicitly told it will not perform.
`evals/ablate.py` removes it, keeps the system prompt and the field schema exactly as shipped, and
re-fires the 17 registers carrying the wrong-period decoy. **763 of 763 cells, 89 of 89 statuses, 65
of 65 due dates, 0 false alarms, all 22 decoy rows still correct** — on 21.0% fewer input tokens per
call. The rulebook block is **not load-bearing on this corpus**, which is a real and immediately
actionable finding, and it is also more evidence that the corpus has stopped discriminating.

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM reader: it regexes every value out of every condition block — **all 2,294
cells, perfectly, for free** — and then takes the status from the site's own `Register flag` instead
of running the rulebook. That is what a great many real monitoring spreadsheets actually do.

It scores **42.16% five-way (113 of 268)**, raises a worklist with a **25.51% false-alarm rate (25
of the 98 rows it raised)** and **misses 53 of the 126** obligations that need action. And note what
a flag read cannot reach *at all*:

- **`due_in_window` and `not_determinable` are impossible for it** — 68 of 268 rows carry a status a
  three-valued self-assessment is structurally incapable of saying. A flag can express concern; it
  cannot express a deadline.
- **It scores 0 of 172 on derived due dates.** A flag has no arithmetic in it. That is the clearest
  evidence on this page that *which obligations need action* and *by when* are two different
  questions, and it is why they are two graders.
- **Its escalation flag can never fire.** The guardrail asks "is anything overdue while the flag is
  quiet", and the floor has defined overdue *as* the flag — so it is a tautology and scores 0 of 31.
  A business-condition guardrail is only ever as good as the field it reads.

## The no-gold diagnostic, and what it is blind to

`evals/judge.py` also compares the **site's own flag** against the status the rulebook computes from
the same row. It uses no labels at all, so a forker can compute it on registers nobody has scored.
On r001 it found **107 of 268 disagreements — exactly the 107 planted misflags, with none spurious.**

⚠︎ **And it is blind by construction to the free floor.** The floor takes its status *from* the
flag, so this diagnostic reports **0 disagreements** on a run that got 155 of 268 statuses wrong. A
consistency check between two things cannot see a reader who copies one into the other. It is
reported as a diagnostic and deliberately not as this kit's guardrail.

## There is no LLM judge in this kit

Gold is exact and every answer is one value, so `==` with light normalisation settles it — and the
status is a rulebook lookup over dates, which is the one thing you should never ask a model to
adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one register, one call, on your machine; serves the rulebook beside the worklist |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py`, `evals/ablate.py` |

## Point it at your own registers

**Replace `data/rulebook.json` first** — it is this kit's own construction and resembles no real
permit. Then replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record
per register. `SECTION_HINTS` and `SECTION_PREFIXES` in `src/select.py` map fields to section
headings and **will** need editing for a different register layout; when they do not match, selection
falls back to the whole document — slower, more expensive, always correct. `compute()` in
`src/extract.py` is this kit's own escalation rule and is the second thing to replace.

If your registers are unlabelled — the normal case — the cell grade and every confusion matrix go
away, and the **register-flag diagnostic** does not: it compares each row's own self-assessment
against the status the rulebook computes from the same row. No gold needed, and it caught every
planted contradiction here. Read the caveat above about what it cannot see.

## What it does not do

It never files, submits, notifies, escalates, renews or clears anything, and it contacts nobody. It
reads one register at a time and it does not remember the last one. It does not know whether the
permit was amended after the register was drawn, whether a due date was extended by correspondence
that never reached the register, or whether the evidence behind a "done" entry actually discharges
the condition it is filed against. It cannot resolve a condition whose own text is ambiguous about
its frequency, and it treats a recorded completion as true because it is recorded. It does no OCR —
scanned or image-only registers extract no text. No auth, no database, no multi-tenancy, no
deployment story, and — deliberately — no scheduler. It runs once, locally, and that run is what
gets published.
