# rcv-disc — resolve a receiving discrepancy against its BOL, scan and carrier exception

One receiving-discrepancy case, one model call, a proposed liable party with a documentary
citation. Every case carries 2-4 SKU lines -- PO quantity, BOL quantity, receiving-scan quantity,
all always present -- plus one carrier exception note that is either absent or names exactly one
SKU. Exactly one line per case is genuinely discrepant; the rest are clean filler, so the model has
to find the right line among several, not just notice something is off.

```bash
python -m src.app                                   # the local UI on http://127.0.0.1:8790

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-exception-first   # free. no key, no spend.
python -m evals.run --run-id t000 --stub                  # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                 # THIS SPENDS: 36 calls, one per case.
```

## Four values, and why the last one is the whole kit

| liable_party | means | what decides it |
|---|---|---|
| **vendor** | The BOL states less than the PO ordered, and receiving matches the BOL. | The carrier delivered everything it was given -- the vendor gave it less than the PO called for. |
| **carrier** | The BOL states the full PO quantity, receiving recorded less, AND the carrier's own exception note names THIS exact SKU. | The carrier picked up the full order and delivered less, and its own paperwork corroborates a transit loss for this line. |
| **internal** | Same shortfall shape as carrier, but nothing on file corroborates it for THIS SKU -- no exception at all, or one naming a different SKU. | Likely a dock miscount, not a proven transit loss -- an unrelated exception on file does not excuse this line. |
| **insufficient_evidence** | The BOL and receiving agree with each other but not the PO (an apparent over-shipment), or more than one quantity disagrees at once. | There is no clean documentary basis for a liability call, so the kit says so instead of guessing. |

**Why silence gets its own value instead of collapsing into a guess.** A carrier exception on a
case is not, by itself, evidence about any particular line -- it is evidence about whatever SKU it
actually names. A checker that reads "an exception exists somewhere" as "the carrier is liable
here" produces a liable-party call the documents do not support. `insufficient_evidence` is what a
genuinely unclear case gets instead of a confident guess in either direction.

## The guardrail

**This kit never issues a chargeback or a credit, and it never makes the final liability
determination.** It builds the case file and proposes a probable liable party with its
documentary basis; receiving/AP confirms the call before anything is issued. This is
non-configurable -- there is no flag anywhere in this kit that turns it off.

## What was measured

<!-- TODO: fill in after the real run -->

## The trap, planted on purpose

6 of the corpus's 14 `internal` cases (~43%) carry a carrier exception note that is real, on file,
and names a DIFFERENT SKU than the case's own discrepant line -- a plausible, non-adversarial
scenario: a case can legitimately have an unrelated carrier note on file from a different line's
minor issue. `evals/baseline.py` is a rule someone would write in five minutes -- "if there's an
exception note, blame the carrier" -- and it is the honest floor for exactly that reason: it scores
**83.3%** liable_party accuracy and gets every one of those 6 trap cases wrong, while scoring 100%
on discrepant-SKU and quantity citation, because finding the discrepant line is a mechanical check
this baseline never gets wrong. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus
design and its limits.

## The gold determinations cannot drift from the cases

Nothing is hand-labelled. `tools/build_corpus.py`'s `classify_case()` is the single implementation
of the four-way rule above; it labels gold at generation time and, independently, via
`--verify`, re-derives every gold row from the case record actually written to disk and asserts no
drift. Cases are built FOR a target category and then independently reclassified -- the gold label
is never the target category string itself, precisely so a bug in the case-construction code
cannot silently ship a mislabelled row.

## Layout

```
data/cases.jsonl            36 receiving-discrepancy cases
data/gold.jsonl              36 gold determinations, one per case, derived mechanically
data/SOURCES.md               why the corpus is synthetic, and what it does and doesn't test
src/prompt.py                the taxonomy and citation vocabulary, declared ONCE
src/resolve.py                the AI layer: load case, one call, done
src/app.py                    the local UI (port 8790)
evals/scoring.py              pure-code scoring: 4-way match plus the two named failure metrics
evals/baseline.py             the free "blame the carrier on any note" floor, honestly narrow
evals/run.py                   the real eval harness
tools/build_corpus.py         renders cases, derives the gold determinations
```

MIT, like every kit here.
