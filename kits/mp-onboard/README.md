# mp-onboard — cross-check a seller onboarding application against its documents

One third-party seller application, seven declared-vs-document field pairs — business identity,
banking details, owner identity — one model call, a `match` / `mismatch` / `mismatch_explained`
flag per field and a summary drafted for a verification analyst. The tool never approves, denies,
or escalates the application itself; it extracts and cross-checks, and every flagged
inconsistency stays flagged, even one that looks minor. The decision belongs to the analyst.

```bash
python -m src.app                                  # the local UI on http://127.0.0.1:8791

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline                            # free. no key, no spend.
python -m evals.run --run-id t000 --stub             # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>            # THIS SPENDS: 36 calls, one per application.
```

## What this kit never does

It never approves, denies, or escalates a seller application, and it never auto-clears a flagged
inconsistency, even one that looks minor. If you are looking for the line that enforces this,
there isn't one function to point at — there is no field, no endpoint and no return value anywhere
in `src/onboard.py`, `src/app.py` or the UI that writes a `verification_outcome`. The historical
outcome that ships in `data/gold.jsonl` exists only so the eval can show whether the model's flags
would plausibly have supported the verification team's real call — the model is never asked to
reproduce it.

## The seven field pairs, each flagged independently

| declared field | checked against | on |
|---|---|---|
| `business_name` | `legal_name` | the business registration document |
| `business_address` | `registered_address` | the business registration document |
| `tax_id` | `tax_id` | the business registration document |
| `bank_account_name` | `account_holder_name` | the bank verification letter |
| `bank_routing_number` | `routing_number` | the bank verification letter |
| `owner_name` | `full_name` | the government ID document |
| `owner_address` | `address` | the government ID document |

Each field gets exactly one of three flags:

| flag | means |
|---|---|
| `match` | the declared value and the document value agree |
| `mismatch` | they disagree, and nothing in `submission_note` explains why |
| `mismatch_explained` | they disagree, **and** `submission_note` specifically and genuinely names *that* field's discrepancy — a generic or unrelated note does not count |

**Why the specificity requirement is the whole job.** A genuinely explained discrepancy — "recently
changed business address, registration update pending" — is a real, legitimate outcome the tool
should recognize, not something to flag as suspicious by default. But a note that merely exists is
not the same as a note that explains *this* field, and reading it as if it does is exactly the
failure the over-explaining metric below catches. See
[`data/SOURCES.md`](data/SOURCES.md) for exactly how the corpus plants both directions of this.

## The metric this kit exists to measure

`missed_banking_mismatch` in `evals/scoring.py` counts the model's own `bank_routing_number` flag
being anything other than `mismatch` on the corpus's planted trap set — applications where
`bank_routing_number` is the *only* one of the seven fields that disagrees, and every other field
looks completely clean. This is the exact failure named in the product spec: a mismatched banking
detail on an otherwise-clean application is the pattern a fraudulent application produces, not
evidence the application is fine. It is reported as its own count and rate, never folded into
overall accuracy, the same discipline fin-payrun's `false_paid` and fin-invval's
`false_fully_explained` get.

A second, opposite-direction metric — `over_explained` — is scored alongside it, also kept
separate: a genuinely unexplained mismatch, on any of the seven fields, that the model calls
`mismatch_explained` anyway. That is the model reading an absent or unrelated note as covering a
discrepancy it never mentions.

## What was measured

One run, `r001-mp-onboard`, on 2026-08-20 — 36 applications, one model call per application, 0
failures, clean on the first attempt (largest call used 643 of the 3,000-token `MAX_TOKENS`
ceiling — real headroom, no truncation). Scored by `evals/scoring.py`, which is pure code; the
free floor below is scored by the identical function.

| | this run | free floor (`evals/baseline.py`) |
|---|---|---|
| field answered | 252 of 252 (100.0%) | 252 of 252 (100.0%) |
| field accuracy | **100.0%** | 91.7% |
| missed banking mismatch | **0 of 13 (0.0%)** | 10 of 13 (76.9%) |
| over-explained | **0 of 25 (0.0%)** | 21 of 25 (84.0%) |

39,006 input / 12,336 output tokens over the 36 calls. Latency p50 3,139 ms, p95 5,039 ms, 113.2 s
wall.

**Read the 100%s with the corpus in mind.** This is one run of one model over a corpus that was
written here and contains exactly one planted trap family (a lone unexplained `bank_routing_number`
mismatch on an otherwise-clean application) and no others. It is not a distribution, there is no
second model to compare against, and no red-team run was fired. What the table does show is
**separability**: the free note-presence floor misses 10 of the 13 planted banking-trap
applications — it reads any attached note as an explanation, whatever it actually says — so the
corpus discriminates, and a result of 0 is a real pass rather than a task nothing could fail.

**The reasoning-configuration gap.** The registered run left provider-side reasoning ("thinking")
at its documented default — **on** — while the shipped app's own `/api/check` hardcodes
`thinking=THINKING_OFF` on every live call (`src/onboard.py` takes the kwarg; `src/app.py` sets
it). Reasoning consumed 66.5% of this run's output-token budget (8,206 of 12,336 tokens). The
published latency and cost above are therefore not what a forker's own click through the live UI
will see — that configuration has never been separately measured.

## What it cannot do, stated up front

- **Assumes every submitted verification document already arrives text-extractable.** The
  business registration, bank letter and government ID blocks are clean fields, standing in for
  documents already OCR'd or otherwise extracted to text — this kit does not parse images or
  PDFs. A low-quality photo submission that OCRs poorly has no clean text for this kit to read,
  and this kit has no way to notice that a document it was given is degraded rather than simply
  mismatched. A real deployment needs a manual fallback for exactly that case.
- **At most one pattern per application.** A real application can carry discrepancies in more
  combinations than the five named patterns here cover; see `data/SOURCES.md`.
- **The trap denominator is small.** 13 trap applications is what a corpus of this scale supports
  honestly — reported as a raw count alongside the rate for exactly this reason.

## The gold labels cannot drift from the application records

Nothing is hand-labelled. `tools/build_corpus.py` computes every gold field flag and
`verification_outcome` from the same declared-plus-document record that ships in
`data/applications.jsonl`, by one rule (`derive_flags()` / `derive_outcome()`), used both to label
gold at generation time and, independently, by `--verify` to re-check every row against the record
actually written to disk — so a bug in the corpus's own field construction cannot silently ship a
mislabelled row. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus design, the trap
fraction, and its limits.

## Layout

```
data/applications.jsonl    36 synthetic applications, each a declared record plus 3 document blocks
data/gold.jsonl            36 gold rows: 7 field flags, verification_outcome, trap flags
data/SOURCES.md            why the corpus is synthetic, the trap design, and what it does and doesn't test
src/prompt.py               the field-pair taxonomy and flag rule, declared ONCE
src/onboard.py               the AI layer: one call, parse the field set
src/app.py                  the local UI (port 8791)
evals/scoring.py            pure-code scoring: field accuracy, missed_banking_mismatch, over_explained
evals/baseline.py           the free note-presence floor, honestly narrow
evals/run.py                 the real eval harness
tools/build_corpus.py       renders applications, derives the gold labels, verifies them
```

MIT, like every kit here.
