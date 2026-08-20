# fin-payrun — trace a vendor invoice through payment run and draft its status reply

One vendor payment-status inquiry, one invoice's full 4-stage record — match, approval, run
inclusion, remittance — one model call, a traced current stage and a reply grounded in it. The
record is read **in order**: the true current stage is the first of the four that is not cleanly
complete, never whatever a downstream field happens to show. That is the trap this kit measures —
a downstream field that looks done (a real scheduled run, a real remittance reference) does not
override an earlier stage that is not.

```bash
python -m src.app                                  # the local UI on http://127.0.0.1:8789

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-ruleorder    # free. no key, no spend.
python -m evals.run --run-id t000 --stub            # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>           # THIS SPENDS: 35 calls, one per invoice.
```

## What this kit never does

It never releases a payment, never changes a remittance detail, and never commits to a payment
date beyond the invoice's own scheduled run. The drafted reply is **informational only** — it
reports the invoice's actual traced state to the vendor, it never promises to accelerate or move a
payment off-cycle, and any invoice with an open match or approval exception is flagged
`requires_ap_review: true` so it is never sent without AP review first. If you are looking for the
line that enforces this, there isn't one function to point at — there is no function anywhere in
`src/payrun.py`, `src/app.py` or the UI that writes a payment as released or a remittance detail as
changed.

## The five stages, read in order, and the fourth field derived from them

| stage | what decides it | if a vendor asks |
|---|---|---|
| **match_exception** | `match.matched` is false | no payment timeline — item needs AP review |
| **approval_exception** | match clean, `approval.status` is `exception` | no payment timeline — item needs AP review |
| **awaiting_run_inclusion** | match + approval clean, `run_inclusion.included` is false | approved, not yet on a scheduled run — no date to give |
| **in_scheduled_run** | match + approval + run_inclusion clean, `remittance.remitted` is false | state ONLY the real `scheduled_date` |
| **remitted** | all four stages clean and `remittance.remitted` is true | state the real `remittance_date` and reference |

`requires_ap_review` is never authored independently — it is true if and only if the governing
stage is `match_exception` or `approval_exception`. Getting the stage right and the boolean wrong
(or vice versa) is a real failure mode the eval scores separately; see `evals/scoring.py`.

**Why the read order is the whole job.** Every invoice carries all four stages fully populated,
always — there is no partial record. A downstream field can carry a value that looks complete (a
real `run_id` and `scheduled_date`, a real `remittance_date` and reference) while an earlier stage
is the one that actually governs. This is not adversarial text designed to trick a reader — nothing
in any field is false — it is a data-shape trap: the only way to get an invoice's true current stage
right is to read match and approval before trusting what run_inclusion or remittance show. See
[`data/SOURCES.md`](data/SOURCES.md) for exactly how often, and how, this corpus plants it.

## The metric this kit exists to measure

`false_paid` in `evals/scoring.py` counts a model that says an invoice is paid — either
`current_stage: remitted` or a reply that otherwise claims payment happened or is imminent — when
the invoice's true governing stage is actually an open exception, over the corpus's planted trap
set (invoices where `remittance` shows a real remittance record despite an unresolved match or
approval problem). This is the exact failure the guardrail exists to prevent: telling a vendor an
invoice is paid when it is actually held. It is reported as its own count and rate, never folded
into overall accuracy, the same discipline fin-invval's `false_fully_explained` and fin-close's
`false_clean` get.

Two smaller fields are scored alongside it, also kept separate: `requires_ap_review` accuracy, and
whether the reply's stated date (if any) matches the one real date the record supports — the
`scheduled_date` for `in_scheduled_run`, the `remittance_date` for `remitted`, or correctly no date
at all for the other three stages.

## What was measured

<!-- TODO: fill in after the real run -->

## What it cannot do, stated up front

- **Assumes match, approval and run-inclusion status all live in systems this kit can query
  directly.** A manually tracked approval step — an email sign-off that never made it into the
  approval system — has no trace to follow, and this kit has no way to notice that the trail it is
  reading is incomplete rather than merely unfavourable. Every invoice in this corpus has a
  complete trail by construction; a real deployment would need to detect "the trail is missing a
  step" as its own state.
- **At most one trap pattern per invoice.** A real payment run can carry a stale-looking field at
  more than one stage on the same invoice at once; this corpus plants at most one to keep the
  failure mode legible.
- **The trap denominator is small.** 4 remittance-trap invoices is what a corpus of this scale
  supports honestly — see `data/SOURCES.md` for why, and why it is reported as a raw count
  alongside the rate.

## The gold labels cannot drift from the invoice records

Nothing is hand-labelled. `tools/build_corpus.py` computes every gold `current_stage`,
`requires_ap_review` and `expected_date` from the same 4-stage record that ships in
`data/invoices.jsonl`, by one precedence function (`derive_stage()`), used both to label gold at
generation time and, independently, by `--verify` to re-check every row against the record actually
written to disk — so a bug in the corpus's own field construction cannot silently ship a
mislabelled row. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus design, the trap
fraction, and its limits.

## Layout

```
data/invoices.jsonl        35 synthetic invoices, each a full 4-stage record plus one vendor inquiry
data/gold.jsonl            35 gold rows: current_stage, requires_ap_review, expected_date, trap flags
data/SOURCES.md            why the corpus is synthetic, the trap design, and what it does and doesn't test
src/prompt.py              the stage taxonomy and precedence rule, declared ONCE
src/payrun.py              the AI layer: one call, parse the field set
src/app.py                 the local UI (port 8789)
evals/scoring.py           pure-code scoring: stage accuracy, review accuracy, false_paid, date accuracy
evals/baseline.py          the free rule-order floor, honestly narrow
evals/run.py                the real eval harness
tools/build_corpus.py      renders invoice records and inquiries, derives the gold labels, verifies them
```

MIT, like every kit here.
