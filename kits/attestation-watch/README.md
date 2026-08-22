# attestation-watch — whose attestation is missing, stale, or contradicted by what else is on file

**UC053.** Point it at one engagement's independence attestation register, get the whole roster back
as structured fields — plus a status per person taken afterwards in pure code: who needs chasing
today, who owes nothing, and whose record the register simply cannot answer for.

> **⚠︎ THIS KIT WATCHES NOTHING.** It reads one snapshot that somebody else assembled and proposes a
> worklist. It does not poll, subscribe, schedule, alert, escalate, chase, file, sign a register off
> or clear anybody. Nothing in it runs unattended, and nothing in it writes anywhere.
>
> **⚠︎ It proposes a status with its reasoning, names what it could not determine, and never
> authorises, writes, dispatches, releases or clears anything.** A qualified person decides what to
> do about it. **The cycle rulebook shipped with this kit (`data/rulebook.json`) is illustrative and
> is not an authority** — it was written for this kit and reproduces no real professional standard,
> standard-setter's rule, regulator's requirement or firm policy. Replace it with your own before
> you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                        # free — validates the gold set
python -m evals.run --run-id b000-attestation-watch-boxtick --baseline   # free — the box-tick floor
python -m evals.run --run-id t000-attestation-watch-stub --stub     # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-attestation-watch --yes           # SPENDS: one call per register
python -m src.app                                                   # the local UI on 127.0.0.1:8802
```

## What a "monitor" kit is, and what it deliberately is not

`monitor` sounds like a daemon, a stream or a dashboard. It is none of those here, and building one
would have been the wrong answer. **A monitoring snapshot is the document.** Each corpus file is one
engagement's register at one moment, carrying the obligations that apply, what has actually been
filed, and enough noise that the answer is not a template fill. The model reads it and returns
structured fields; **pure code, never the model, then decides the status.**

The question the kit answers is:

> **which of these obligations needs action, by when, and which ones cannot be determined from
> what is on the page?**

There is no scheduler, no poller, no queue and nothing stateful anywhere in the repository.

## The decision: five gates with a stopping order

```
status(person, register):
    role vacated / joined mid-cycle / a role with no requirement  -> not_required
    no cycle date, or a return whose covered period is not stated -> not_determinable
    no return on file at all                                      -> missing
    two returns that disagree, or a relationship the register
      records as disposed BEFORE the return that declares it      -> contradicted
    filed later than due + grace, or covering a period that ends
      before the due date                                         -> stale
    otherwise                                                     -> satisfied
```

**`not_required` is first and the position is the whole point.** A vacated role, a mid-cycle joiner
and a role the rulebook puts no requirement on all have no return on file, and a queue that equates
"no form" with "gap" chases every one of them. That is the error that gets a monitoring queue
ignored, and on this corpus it is 40 of 280 people.

**`not_determinable` is second and is a first-class answer**, not a failure to produce one. A monitor
that never says "cannot determine from this record" is not cautious, it is guessing — and on a
monitoring queue a confident wrong "fine" is the failure that actually hurts.

**The due date is derived, never read.** No register states one. It is `cycle_opened_on +
cycle_days[role]`, and for a role the rulebook gives no cycle length the correct answer is *no date
at all* rather than a guess.

**The rulebook is sent with every call.** `src/prompt.py::rulebook_block()` renders
`data/rulebook.json` into the prompt rather than restating it in prose, so the instructions and the
gold labels cannot drift apart about the same arithmetic.

## Four numbers, scored separately, and the fourth is the headline

A monitoring kit that publishes one number has hidden the only one anybody acts on.

| | what it measures | r001, the fast tier | the free floor |
|---|---|---|---|
| 1. field extraction | the reading half | **2,926 of 2,926 cells** (100%) | 2,868 of 3,000 (95.6%) |
| 2. status verdict | the deciding half — pure code over the model's values | **273 of 280** (97.5%) | 148 of 280 (52.86%) |
| 3. date arithmetic | the model's own derived due date | **273 of 273** (100%) | 280 of 280 (100%) |
| 4. **FALSE-ALARM RATE** | of everybody flagged, how many did not belong | **0.0% — 0 of 101** | **51.61% — 32 of 62** |

**Chasing a partner whose attestation is fine is the error that gets a monitoring queue ignored**, so
it is in the headline rather than a footnote. It is counted strictly: a false alarm is a row the kit
flagged whose gold status is `satisfied` or `not_required` — the two answers that mean nothing
needed doing. A `not_determinable` row wrongly flagged is counted separately as *misrouted*, because
somebody does have to open that file; they have to open it for a different reason. Both were 0 on
r001.

Beside them, two numbers that are not one of the four:

- **`not_determinable` recall: 16 of 18 (88.89%), precision 100%.** How often the kit reaches for
  "cannot determine from this record", and is right to. The two it missed are on the one register
  that never answered at all — see below.
- **missed breaches: 0 of 104.** The other direction: somebody who needed action and was told they
  did not. The floor missed 74 of 104 — every `stale` row and every `contradicted` one.

## What it measures, and the register it lost

One scored run over the 50 registers, `results/eval-r001-attestation-watch.json`.

**49 of 50 registers answered; 273 of 280 people.** Every published denominator on the kit page says
so. The 50th, `ATT-0015`, is the failure this kit publishes loudest:

> its reply hit **exactly 16,000 output tokens** with `finish_reason: length` and **no text at all**
> — the entire ceiling went on provider-side reasoning and the JSON never started. The largest reply
> that *did* finish used 13,333.

`MAX_TOKENS` was not guessed: a three-register calibration
(`results/eval-c000-attestation-watch-calibration.json`) measured a largest reply of 6,574, and the
constant was set at 16,000 — **2.4× the calibrated maximum, and still not enough once.** On a
monitoring kit that is worse than a wrong answer: a register that produces no worklist looks exactly
like a register with nothing to do. Three of the seven people it lost needed action.

The constant is deliberately **not** raised after the fact — every figure this kit publishes was
measured under 16,000, and moving it now would put the code and the published run under different
ceilings. That is the same discipline `--max-tokens` enforces for calibration runs.

**88.3% of this run's output tokens were provider-side reasoning** (229,975 of 260,390), left at the
provider's default. That is the same knob, and the same unmeasured question: nobody here knows what
turning it off would do to the statuses.

## The free floor is the incumbent, not a straw man

`--baseline` is a non-LLM monitor: it regexes every field out of the register and then decides the
status by asking one question — **is there a line in `Returns Filed` for this person?** A line means
`satisfied`; no line means `missing`. That is what a spreadsheet does, it runs in a second, and it is
what most attestation monitoring actually is.

It reads **perfectly**. `evals/check_labels.py` asserts before any run may spend that its regexed
values reproduce gold exactly on every field except `status`, and the judge measures the same thing
live: **the rule re-run over the floor's own extracted values scores 100%.** So the whole gap is the
deciding half, by construction — one call to `src/rulebook.py::decide()` would make the floor
perfect, and not making it is the design.

What the box-tick costs:

- **32 false alarms, every single one a person who owed nothing** — 14 vacated roles, 14 mid-cycle
  joiners and 12 roles with no requirement. A 51.61% false-alarm rate: every other row on its
  worklist is somebody with nothing to do.
- **74 missed breaches of 104** — all 44 `stale` and all 30 `contradicted`. It called every one of
  them `satisfied`, because a form exists.
- **`not_determinable` recall 0 of 18.** Four of the six statuses are unreachable for it: `stale`,
  `contradicted`, `not_required` and `not_determinable`. A box-tick can say a form is absent. It
  cannot say a form was late, that a register disagrees with itself, that nothing was owed, or that
  the record cannot be read.
- **the routing flag: 0 of 29 registers.** It inherits a box-tick status, so it can never produce
  either of the two statuses it looks for. A register-level guardrail is only as good as the
  statuses it reads.

## There is no LLM judge in this kit

Gold is exact and every answer is one value, so `==` with light normalisation settles it — and the
status is a date comparison plus a table lookup, which is the one thing you should never ask a model
to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the worklist |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## Point it at your own registers

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
register. **Replace `data/rulebook.json` first** — it is this kit's own construction and reproduces
no real standard or policy. `SECTION_HINTS` in `src/select.py` maps fields to section headings and
**will** need editing for a different register layout; when it does not match, selection falls back
to the whole document — slower, more expensive, always correct.

If your registers are unlabelled — the normal case — the field grade and every confusion matrix go
away, and the **consistency diagnostic** does not: `evals/judge.py` compares each reply's own stated
`status` against the rulebook re-run over that reply's own extracted values. No gold needed. It is
blind to a reply that misreads a date and then reasons correctly from the misreading, which on this
corpus is most of the ways to be wrong, and it is reported as a diagnostic rather than as this kit's
guardrail.

## What it does not do

It watches nothing. It never chases anybody, never files a return, never signs a register off,
never clears a person and never contacts anyone. It reads one register at a time. It does not know
whether a person sits on another engagement with another cycle, whether a return was filed against
the wrong engagement, whether a relationship belongs to a family member rather than the attester, or
whether the rulebook changed part-way through a cycle. It has no notion of "not due yet" — every
required attester in this corpus is past their due date by construction, and on a real register that
case is common. It does no OCR — scanned or image-only registers extract no text. No auth, no
database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run is
what gets published.
