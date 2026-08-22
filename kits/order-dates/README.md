# order-dates — every deadline a scheduling order sets, and the day it lands on

**UC054.** Point it at a scheduling order, get a row per obligation back — what must be done, how
the paragraph fixes its date, what it counts from — plus the calendar date, recomputed afterwards
in pure code from a shipped counting rulebook.

> **⚠︎ This computes a proposed calendar. It never files, serves, dockets or waives anything.**
> Nothing here is legal advice and nothing is a substitute for the file and the rules that actually
> govern it. **The counting rulebook shipped with this kit (`data/rulebook.json`, "MV-CR-1") is
> invented and is not an authority** — Meridian Vale is not a place, the Meridian Vale Civil Court
> is not a court, and every court holiday on its list was made up for this kit. It reproduces no
> procedural code, court rule, local rule, standing order or published holiday schedule. No real
> court, judge, case, docket number, party or jurisdiction is named anywhere in this kit. Replace
> the rulebook with your own before you calendar anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                        # free — validates the gold calendar
python -m evals.run --run-id b000-order-dates-desk-calendar --baseline   # free — the counting floor
python -m evals.run --run-id t000-order-dates-stub --stub           # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-order-dates --yes                 # THIS SPENDS MONEY: one call per order
python -m src.app                                                   # the local UI on 127.0.0.1:8854
```

## The decision: extract, then count

The model reads the order and returns structured values. **Pure code, never the model, then
recomputes the date** — from the same rulebook, over the model's own extracted values.

```
due_date(basis, period_days, order_date, trigger_event_date, stated_date):
    explicit_date              -> the day the Order names. NEVER moved, weekend or not.
    calendar_days_from_order   -> day zero is the Order; every day counts; ROLLS forward
    calendar_days_from_event   -> day zero is the event; every day counts; ROLLS forward
    business_days_from_order   -> day zero is the Order; business days only; never rolls
    business_days_from_event   -> day zero is the event; business days only; never rolls
    ... and if the triggering event has NO recorded date -> there is no date at all.
```

**`cannot be dated` is a first-class answer, not a failure to produce one.** An obligation whose
trigger the order leaves undated cannot go on a calendar from the four corners of the order — and
it is not the order date, not zero days and not a guess. **24 of the 260 obligations are that
case.** On a docketing queue a confident wrong date is worse than a blank, because a blank gets
chased and a date gets diarised.

**The rulebook is sent with every call.** Counting a deadline needs a definition of a business day
and the list of days the court is shut, and a model cannot apply a holiday list it has never been
shown. `src/prompt.py::rulebook_block()` renders `data/rulebook.json` into the prompt rather than
restating it in prose, so the model's instructions and the gold dates cannot drift apart about the
same calendar. On the worked example it is 904 of 2,644 input tokens (34%).

## The two decoys, and where they live

| decoy | what it is | why it is there |
|---|---|---|
| `party_calculated_date` | a parenthetical carrying **somebody else's arithmetic** — `(counsel's calendar: 19 March 2027)` | extracted as a field, and it decides nothing. **96 of 260 obligations carry one and 40 of those are wrong** — 28 of them exactly the answer a desk calendar gives, 12 an ordinary diary slip on an obligation that was not even hard |
| a **struck** paragraph | a numbered paragraph that names an item, a number and a unit and then strikes, withdraws or disapplies it | it sets no date and must produce **no row**. **30 of the 78 non-deadline paragraphs** are this shape. A row for one of them is a diary entry nobody owes |

Note what `SECTION_HINTS` in `src/select.py` maps `deadlines` to: the Order Date, the Recorded
Events table and the ordered paragraphs — because an obligation cannot be dated from its own
paragraph alone. What selection genuinely saves is the `Court` and `Division and Courtroom`
sections, which no field maps to and which are therefore never sent.

## What it measures — four numbers, never folded together

Scored run **`r001-order-dates`** over 52 orders and 260 obligations (`results/`):

| | model (r001) | the free desk-calendar floor (b000) |
|---|---|---|
| obligations found / invented | **260 of 260, 0 invented** | 260 of 260, 0 invented |
| structured-field extraction | 1,891 of 1,924 cells (**98.28%**) | 1,924 of 1,924 (**100%**) |
| **date accuracy** | **259 of 260 (99.62%)** | **144 of 260 (55.38%)** |
| **found the obligation, got the date wrong** | **1 of 227 rows read perfectly (0.44%)** | **116 of 260 (44.62%)** |
| a date on a row nothing dates (`false_dated`) | **0 of 24** | **24 of 24 (100%)** |
| said "cannot be dated" correctly | **24 of 24** | 0 of 24 |
| `undatable` flag vs gold | 1.00 recall, 1.00 precision | 1.00 recall, 1.00 precision |

### The interesting number is the third row, and the fourth explains it

`found_but_misdated` is the one figure that separates *reading* from *counting*: obligations where
every structured value is exact and the date is still wrong. The floor gets **116 of 260** — it
reads the orders perfectly and cannot count them. The run gets **one**, on `ORD-0029` ¶1: 35
calendar days from a recorded event, answered 2027-12-20 where the rulebook gives 2027-12-17. That
single error was **caught by the no-gold consistency diagnostic**, which re-runs the rulebook over
the reply's own values and needs no labels at all.

### And the floor's own worst number is the one about honesty

The desk-calendar floor never says *"cannot be dated"*. Faced with a period running from an event
the order leaves undated, it counts from the order date anyway and produces a confident date on all
**24 of 24**. The scored run produced none. That is the failure that actually hurts on a docketing
queue, and it is why `false_dated` is published as its own number rather than averaged into a date
accuracy figure where it disappears.

## The failure this run DID produce, and it is not a date

**33 of 1,924 extraction cells were wrong and all 33 are the same field, `item`.** On **7 of the 52
orders** the model included the verb — `"file the witness list"` where gold has `"the witness
list"` — and it did so **consistently within an order**: whole orders are all-verb or all-no-verb,
never mixed. That is a per-document convention choice, not a per-row mistake, and the schema is
genuinely ambiguous about it: *"what must be done"* can reasonably be read to include the doing.

**It moved no date.** `basis`, `period_days`, `trigger_event`, `trigger_event_date`, `stated_date`
and `party_calculated_date` were **260 of 260 each**. What it did move is a denominator: the
headline above says *1 of 227 rows read perfectly* rather than *1 of 260*, because those 33 rows
fail an all-fields-exact test on a field the arithmetic never touches.

**It was not fixed after the fact, and that is deliberate.** Normalising a leading verb in the
scorer, or tightening the field hint, would be writing a rule after seeing the answers — the run
would then be scored against a target it did not have. A forker doing this for real should do both;
this kit publishes the number it actually got. See `Business.not_good_enough` on the kit page.

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM extractor: a desk calendar with three clauses, all three of them things a
real person does. Take the date somebody already wrote next to the obligation; otherwise count
forward on a wall calendar, **treating business days and calendar days alike and never moving a
date off a weekend or a holiday**; and when the triggering event has no date, **count from the
order anyway**.

It is perfect on the parts that are reading work — **all 260 obligations found, none invented, and
1,924 of 1,924 structured cells exact** — and it is a deliberate *counting floor* on the date. It
scores **55.38%**, and its errors are exactly the three things the rulebook exists to settle: 46 of
46 rolled deadlines dated on a closed day, business-day periods counted as calendar days (25% right
on both business-day buckets), and all 24 undatable obligations given an invented date.

⚠︎ **And note what the floor does NOT get wrong.** The pure-code `undatable` flag scores 1.00/1.00
on the floor's own output, because the flag reads two regex-reachable values and the floor reaches
them. That is worth publishing rather than hiding: on this shape of work, *which rows cannot be
dated* does not need a model. The arithmetic does.

## There is no LLM judge in this kit

Gold is exact, an answer is one ISO date, and the rulebook is arithmetic — which is the one thing
you should never ask a model to adjudicate. `==` with light normalisation settles it.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the dates |
| the rulebook | `data/rulebook.json` → `src/calendar_rules.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## What the calibration run bought

`results/eval-c000-order-dates-calibration.json` fired 6 orders at `max_tokens=16000` **before**
anything was scored. The largest reply used **9,521** output tokens; the first value written into
`src/extract.py::MAX_TOKENS`, borrowed from a sibling extraction kit's shape, was **8,000**. The
calibration caught a truncation that would have cost whole orders — and the scored run then
produced a reply of **10,862**, larger than anything the calibration saw. The published cap is
32,000, and the ceiling itself was probed with one live call rather than assumed.

**91.3% of this run's output tokens (244,308 of 267,600) were provider-side reasoning**, not the
JSON record — the highest share of any lens in this kit, and the direct cost of asking for
day-by-day counting.

## Point it at your own orders

**Replace `data/rulebook.json` first.** It is this kit's own construction and reproduces nobody's
rules; `src/calendar_rules.py` reads whatever is in the file, `src/prompt.py` renders whatever
`calendar_rules` loaded, and `tools/build_corpus.py` writes gold with it — so one edit moves the
rule, the instructions and the labels together. Then replace `data/corpus/*.txt`, write your own
`data/fields.json`, and supply a gold record per order. `SECTION_HINTS` in `src/select.py` maps
fields to section headings and **will** need editing for a different layout; when it does not
match, selection falls back to the whole document — slower, more expensive, always correct.

If your orders are unlabelled — the normal case — the field grade and the date grade go away, and
the **consistency diagnostic** does not: `evals/judge.py` re-runs the rulebook over each reply's own
extracted values and counts the rows whose stated date disagrees with it. No gold needed. It caught
**the run's only date error and all 116 of the floor's**. It is blind to a row that misreads the
period or the event date and then counts correctly from the misreading, and it is reported as a
diagnostic rather than as this kit's guardrail.

## What it does not do

It never files, serves, dockets, waives or extends anything, never contacts anybody, and it is not
legal advice or a substitute for the rules that govern your matter. It reads one order at a time
and knows nothing about the docket it sits on: it cannot see an earlier order this one modifies, an
extension granted later, a period tolled while a motion is pending, a service-method extension, or
the difference between filing and service. It cannot count backwards from a trial date. It does no
OCR — a scanned or photographed order extracts no text. No auth, no database, no multi-tenancy, no
deployment story. It runs once per model, locally, and that run is what gets published.
