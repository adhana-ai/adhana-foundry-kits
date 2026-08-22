# ctr-precheck — pre-check a draft currency-transaction filing against the log it came from

**UC056.** Point it at a QC pack — a draft filing beside the cage transaction log it was prepared
from — and get a field table back, plus a defect list produced afterwards in pure code: does the
drafted total survive re-adding the log under the right window, is the patron split across two
records, is the identification block complete and current, is every transaction coded the way the
log codes it, and was the threshold ever crossed at all?

> **⚠︎ This pre-checks a draft. It files nothing and it clears nothing.** It proposes a worklist
> with the rulebook's own reasoning attached and names what it could not determine; a qualified
> person decides what is submitted. Nothing here lodges, transmits, approves, signs or closes
> anything. **The rulebook shipped with this kit (`data/rulebook.json`) is invented and is not an
> authority** — the threshold, the aggregation window, the staleness horizon, the identification
> elements and the transaction codes were all written for this kit, and they reproduce no real
> regulation, form, filing instruction, supervisory guidance or compliance manual. Amounts are in
> **CU**, an invented unit that is not a currency. No real casino, gaming operator, regulator,
> agency, form number or regulation is named anywhere in this kit. Replace the whole rulebook with
> your own programme's before you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                     # free — validates the gold set
python -m evals.run --run-id b000-ctr-precheck-note --baseline    # free — the preparer-note floor
python -m evals.run --run-id t000-ctr-precheck-stub --stub        # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model> --yes                   # SPENDS: one call per pack
python -m evals.ablate --run-id a001-<model> --yes                # SPENDS: where does 0 come from?
python -m src.app                                                 # local UI on 127.0.0.1:8856
```

## The headline is the false-alarm rate, not the accuracy

**A QC queue that cries wolf is worse than no queue at all**, because a person has to clear every
row it produces, and the first thing a team does with a queue full of noise is stop reading it. So
the false-alarm rate gets its own denominator, its own block in every result file, and the first
line of every report.

**Run `r001-ctr-precheck`: 0 of 18 clean filings flagged — 0.00 pct.** The free preparer-note floor
on the same 56 packs: **7 of 18 — 38.89 pct.**

The clean bucket is 18 of the 56 packs and every one of them is **built to bait a careless checker**:

| bait | what it looks like | why it is not a defect |
|---|---|---|
| a non-reportable entry | a wire or a promotional credit sitting in the log, sometimes for a large amount, absent from the drafted total | the rulebook marks it non-reportable. It is not currency and is never part of a currency total |
| an opposite-direction entry | a cash-out in the log of a cash-in filing | directions aggregate separately and are never netted. It belongs to a different filing |
| an entry the wrong side of 06:00 | 03:15 on the gaming day's own date, or 09:25 the following morning | the gaming day runs 06:00 to 06:00. Both belong to a different gaming day |
| a second patron record that IS the same person | two records, matching date of birth and identification reference | on these four packs the draft **did** aggregate it. Flagging an identity split here is a false alarm |

## The seven answers, and the stopping order that makes them countable

```
assess(drafted_total, qualifying_total, window, linked_record, includes_linked,
       missing_elements, captured_on, gaming_day, miscoded_ids):
    qualifying total cannot be computed        -> insufficient_information   (stop)
    qualifying total <= threshold              -> threshold_not_crossed      (stop)
    window is not the gaming day               -> window_misapplied
    else linked record exists and is excluded  -> identity_split
    else qualifying > drafted                  -> missed_aggregation
    then, independently:                       -> identification_gap, type_miscode
```

**Three of the seven defects surface identically** — the drafted total is lower than it should be.
Without a stopping order a checker reports one difference three times, and the false-alarm rate
stops being a property of the filing and becomes a property of the checker. The order names **one
cause per difference**, and `evals/check_labels.py` asserts that every gold row is that pack's own
`assess()` output before any run is allowed to spend.

`insufficient_information` is a **first-class answer, not a failure to produce one**. A pre-check
that never says "this record does not carry what the check needs" is not cautious, it is guessing,
and a confident wrong "clean" is the failure that actually hurts on a filing queue. Three packs
carry a qualifying entry whose amount the log never captured; `r001` reached for it correctly on
**3 of 3, and raised it wrongly 0 times**.

**The rulebook is sent with every call.** A threshold this kit invented is not something a model can
look up, and `src/prompt.py::rulebook_block()` renders `data/rulebook.json` into the prompt rather
than restating it in prose, so the model's instructions and the gold labels cannot drift apart about
the same table. On the worked example it is **1,083 of 3,439 input tokens (31 pct)**.

## The decoy: the preparer's own note

One field on every pack is free text written by the person whose work is being checked, and it is
never an input to the rulebook. **22 of 56 packs (39 pct)** carry a note from the register that
contradicts the answer — a confident sign-off on a defective filing, an anxious one on a filing
with nothing wrong with it. `SECTION_HINTS` in `src/select.py` maps `defects_found` to the eight
sections the rule actually reads, and **not** to `Preparer Note`. That is not a filter — the note
still reaches the model as a field in its own right. It is the map of where the answer lives.

## What it measures

One scored run over 56 packs, `results/eval-r001-ctr-precheck.json`:

| | |
|---|---|
| extraction accuracy | **784 of 784 cells** (14 fields × 56 packs) |
| arithmetic accuracy | **112 of 112** — both total cells, on all 56 packs |
| defect sets exactly right | **56 of 56** |
| defect detection | **100 pct recall, 100 pct precision** over 38 seeded defects |
| **false-alarm rate** | **0.00 pct — 0 of 18 clean filings flagged** |
| `insufficient_information` | 3 of 3 reached correctly, 0 raised wrongly |
| `needs_recompute` flag | 25 of 25 fired, 31 of 31 left alone, 1.00 recall and precision |
| span rate | 346 of 346 returned values on the seven copyable fields |
| hallucinations | 0 |
| latency | 13,883 ms p50 / 29,239 ms p95; 84.3 s wall for all 56 at 12 workers |

**That is a reason to verify harder, not to trust more.** A perfect score on 56 packs is equally
consistent with "the model applies the rulebook" and with "this kit's prompt tells it not to
over-flag, and it follows instructions" — and those are very different products for a forker who
replaces the prompt. So this kit paid for a probe rather than publishing the zero on its own.

## The ablation: the zero is the model's, not the prompt's

`evals/ablate.py` removes the two rules that exist purely to suppress false alarms —

- *"A NON-REPORTABLE ENTRY IS NOT A DEFECT … reporting them as a missed aggregation is a false
  alarm"*
- *"A FILING WITH NOTHING WRONG WITH IT IS 'none'. Answer 'none' and do not manufacture a finding to
  look thorough."*

— keeps the rulebook and the stopping order, and re-fires the **18 clean packs**, because those are
the whole denominator of the number it probes. **0 of 18 flagged again**
(`results/eval-a001-ctr-precheck.json`). The zero survives losing 499 characters of anti-false-alarm
instruction, which is a real finding about the model — and it is also more evidence that this corpus
has stopped discriminating. See `Business.not_good_enough` on the published kit page.

⚠︎ **The ablation does NOT re-fire the 38 defective packs.** Whether the stripped prompt still
*finds* the real defects is unmeasured and is named in `Eval.could_not_verify` rather than glossed.

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM extractor: it regexes the totals, the window, the identification block,
both patron records and every transaction code straight out of the pack, and then decides the defect
list from **eight anxious-sounding phrases in the preparer's note**. No key, no cost.

It is **perfect on the thirteen fields that are regex work — 728 of 728 cells, including all 112
arithmetic cells**, because re-adding a cage log under a stated window is arithmetic and a computer
does arithmetic. Every one of its 44 wrong cells is the fourteenth field.

| | free floor | r001 |
|---|---|---|
| defect sets exactly right | 12 of 56 (21.43 pct) | 56 of 56 |
| defect recall | 2.63 pct | 100 pct |
| **false-alarm rate** | **38.89 pct (7 of 18)** | **0.00 pct** |
| `needs_recompute` | 0.60 recall, 0.50 precision, **10 filings that needed rework left alone** | 1.00 / 1.00 |

**Note what a tone read cannot reach at all.** It can express concern; it cannot name *which* of
seven defects a filing carries, and it can never distinguish "this filing should not exist" from
"this filing is missing a field". **Six of the seven defect codes are outside what tone can say, by
construction** — the floor's per-code breakdown reports 0 of 7, 0 of 6, 0 of 6, 0 of 3 and 0 of 3
rather than hiding it. Making the floor perfect would take one line: it already regexes every value
the rulebook needs. Not doing so is the design — the gap it opens is the gap between reading prose
and doing the arithmetic.

**And the no-gold consistency diagnostic caught every single one of the floor's 44 errors, with 0
false alarms and no labels at all.** That is the strongest evidence here that it is worth computing
on packs nobody has labelled.

## There is no LLM judge in this kit

Gold is exact and an answer is a set drawn from a closed seven-code vocabulary, so set equality with
light normalisation settles it — and the defect list is a rulebook pass, which is the one thing you
should never ask a model to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the answer, and shows the reply's own defect list next to the pure-code one so a disagreement is visible |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py`, `evals/ablate.py` |

## What the calibration got wrong, and why it is recorded

A 6-pack calibration at `max_tokens=16000` measured the largest reply at **2,682 output tokens**
(`results/eval-c000-ctr-precheck-calibration.json`), so `MAX_TOKENS` was set to **8,000**, about 3x
it. The scored run's largest reply was **3,981** — **48 pct above what six packs predicted**. The cap
held with room to spare and nothing truncated, but the margin is narrower than the calibration
implied, and the reason is worth naming: **91 pct of every reply on this task is provider-side
reasoning**. The model is re-adding a cage log, applying an 06:00 boundary and walking a stopping
order, and none of that is transcription. Re-check the margin from `output_tokens_max` on a scored
run rather than trusting a small calibration.

## Point it at your own packs

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per pack.
**Replace `data/rulebook.json` first** — the threshold, the window, the codes, the elements and the
staleness horizon are all this kit's own inventions and resemble no real programme. `SECTION_HINTS`
in `src/select.py` maps fields to section headings and **will** need editing for a different pack
layout; when it does not match, selection falls back to the whole document — slower, more expensive,
always correct.

If your packs are unlabelled — the normal case — the field grade, the defect grade and the
false-alarm rate all go away, and the **consistency diagnostic** does not: `evals/judge.py` re-runs
the rulebook over each reply's own extracted values and counts the replies whose stated defect list
disagrees with it. No gold needed. It is blind to a reply that mis-adds the log and then reasons
correctly from the wrong total — which on this kit is the commonest way to be wrong — and it is
reported as a diagnostic rather than as this kit's guardrail.

## What it does not do

It **watches nothing and files nothing**. It reads one pack that somebody else assembled and
proposes a worklist. It does not poll, subscribe, schedule, alert, escalate, lodge, transmit,
approve, sign or close anything, and nothing in it runs unattended. It reads one pack at a time and
knows nothing about the patron's other gaming days, other properties, or any history before the log
in front of it. It cannot tell a genuine second patron record from a duplicate created by a typo,
because the link keys are the only identity evidence on the page. It seeds **at most one defect per
pack**, so nothing here measures a filing carrying three defects at once — which is what a real
queue looks like. It does no OCR — a scanned cage report extracts no text. No auth, no database, no
multi-tenancy, no deployment story. It runs once per model, locally, and that run is what gets
published.
