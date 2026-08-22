# cargo-compat — check a tank's prior cargo against the product about to go in

**UC048.** Point it at a bulk-tank pre-load check sheet, get a field table back — plus a hold
decision taken afterwards in pure code: is this tank clear to load as it stands, and if it is not,
has the product already gone in?

> **⚠︎ This proposes a verdict. It never authorises a load.** A qualified person authorises the
> load, against the incoming product's safety data sheet and the tank's real cleaning record.
> **The compatibility matrix shipped with this kit (`data/matrix.json`) is illustrative and is not
> an authority** — it was written for this kit and reproduces no commercial, industry-body or
> proprietary chart, no carrier's own prior-cargo list and no regulatory schedule. Replace it with
> your own before you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the inspector-tone floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model> --yes       # THIS SPENDS MONEY: one call per sheet
python -m evals.ablate --run-id a001-<model> --yes    # SPENDS: where does the accuracy come from?
python -m src.app                                     # the local UI on 127.0.0.1:8797
```

## The decision: a matrix lookup with a stopping order

Four checks, in order, stopping at the first that fires. The order is the whole difficulty.

```
verdict(incoming_product, grade, prior_cargo, two_back_cargo, wash_certified_for):
    prior cargo not recorded, or a cargo not in the matrix  -> undetermined
    prior class + incoming class is a reactive pair          -> refuse   (no cleaning clears it)
    any cargo within the grade's LOOK-BACK DEPTH is banned   -> refuse   (cleaning does not cure a ban)
    certified wash >= minimum for prior class at this grade  -> accept
    otherwise                                                -> clean_then_load
```

`undetermined` is a first-class answer, not a failure to produce one. A tank whose prior cargo
nobody wrote down is exactly the case a pre-load check must escalate, and the kit says so rather
than inventing a verdict.

**The matrix is sent with every call.** A compatibility decision is a lookup, and a model cannot
look up a table it has never been shown. `src/prompt.py::matrix_block()` renders `data/matrix.json`
into the prompt rather than restating it in prose, so the model's instructions and the gold labels
cannot drift apart about the same table. On the worked example it is 473 of 2,100 input tokens.

## The two decoys, and where they live

Two fields are on every sheet, are extracted, and decide nothing:

| decoy | what it is | why it is there |
|---|---|---|
| `wash_performed` | the **tank log's** own claim about what was done to the tank | only a **certificate** counts. When the two disagree the tank is credited with the certificate's regime; an uncertified tank is credited with no wash at all. **8 of 55 sheets** have a certificate covering less than the log claims, and the log always claims the more thorough one |
| `inspector_notes` | one person's free-text remark at the hatch | **22 of 55 sheets (40%)** carry a note whose tone contradicts the matrix — a relaxed note on a tank that must be refused, an alarmed note on one that is genuinely fine |

Note what `SECTION_HINTS` in `src/select.py` maps `verdict` to: the five facts the rule actually
reads, and **neither decoy**. That is not a filter — both still reach the model, as fields in their
own right. It is the map of where the answer actually lives. What selection genuinely saves is the
`Terminal and Berth` section, which no field maps to and which is therefore never sent.

## The four hard cases, each measured rather than asserted

`evals/check_labels.py` asserts a floor on every one of these before any run may spend, and fails
the run if a floor is not met.

| case | why a careless reader gets it wrong | sheets |
|---|---|---|
| **a ban is not a cleaning problem** | methanol before a food-grade load is water-miscible, non-reactive and trivially rinsed out — and banned anyway. Cleaning does not cure it | 3 |
| **the certificate governs, not the log** | the log says `steam_and_dry`, the certificate says `not_certified`. The tank has had no wash | 8 |
| **food grade reads TWO cargoes back** | an innocuous prior cargo in front of a banned one. Read only the prior cargo and the sheet looks like a clean `accept` — asserted directly, not hoped for | 5 |
| **the worst-sounding residue often rinses out** | caustic, acid and hypochlorite heels are water-soluble. What is expensive to clean here is fat and hydrocarbon | 6 |

## What it measures

Three scored runs over the same 55 sheets, same judge — two on the fast tier
(`eval-r001-cargo-compat.json`, `eval-r002-cargo-compat.json`) and one on the deliberating tier
(`eval-r003-cargo-compat.json`), all in `results/`.

**All three: 550 of 550 extracted cells, 55 of 55 verdicts, 0 unsafe releases, 0 over-blocks, 19 of
19 hold flags with no false alarms.** Identical, three times, across two tiers. The deliberating
tier costs 13.8% more per sheet and takes 99.8% longer at the median to produce byte-identical
answers; the two fast-tier runs differ from each other by 306 output tokens (1.1%) and by nothing
else.

**That is a reason to verify harder, not to trust more**, and this kit did: a perfect score on
55 sheets is equally consistent with "the model reasons over the matrix" and with "the prompt hands
it the procedure and the model follows instructions". Those are very different claims about what a
forker gets. `evals/ablate.py` separates them — it strips the four ordered checks, the
certificate-governs rule and the note-is-not-evidence rule out of the system prompt, keeps the
matrix, and re-fires the 26 sheets where the removed text could possibly change an answer.
**26 of 26 still correct** (`results/eval-a001-cargo-compat.json`). The accuracy survives losing the
procedure, which is a real finding — and it is also further evidence that the corpus has stopped
discriminating: it cannot separate two tiers, two runs of one tier, or a stripped prompt from a full
one. See `Business.not_good_enough` on the published kit page.

### The headline number is a safety number

The four-way verdict is collapsed onto the one distinction that matters: **is this tank clear to
load as it stands, or is it not.** `not accept` is the positive class, and the expensive direction —
a tank the matrix would have stopped that the run cleared — is counted and named separately as
`unsafe_release`. It was **0 of 39 on all three scored runs, and 0 of 26 on the ablation.**

## The baseline is shipped, including exactly what it cannot say

`--baseline` is a non-LLM extractor: eight fixed worried-sounding phrases in the inspector's note,
no key, no cost. It is perfect on the parts that are regex work — **all nine structured fields, 495
of 495 cells** — and a deliberate *tone floor* on the tenth.

It scores **36.4% verdict accuracy (20 of 55)** and releases **15 of the 39 tanks the matrix would
have stopped**. And note what a tone read cannot reach *at all*: `clean_then_load` and
`undetermined` are the two verdicts that carry the actual work of a pre-load check — "this tank
needs a specific regime first" and "nobody can say yet" — and no amount of reading a note produces
either. **21 of 55 sheets have a verdict the floor is structurally incapable of saying.** Tone can
express alarm; it cannot express a requirement.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` with light normalisation settles it — and the
verdict is a table lookup, which is the one thing you should never ask a model to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the matrix beside the verdict |
| the matrix | `data/matrix.json` → `src/matrix.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py`, `evals/ablate.py` |

## One thing this kit fixed in the shared adapter

The first paid pass over the 55 sheets lost **two** of them — one `urlopen` timeout, one connection
reset. Neither is a model result. `src/adapters/__init__.py` retried HTTP *status codes* only, so a
transport failure (a bare `OSError`, not an `AdapterError`) flew straight past four perfectly good
backoff attempts and was recorded as a failed document. A dropped connection returns no completion
and is billed for none — exactly like the busy-provider case the same file already argued about —
so it is now treated as transient. The superseded pass is kept as
`results/eval-r000-transport-dropout.json` rather than deleted, and the scored runs were fired
afterwards over all 55.

## Point it at your own sheets

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per sheet.
**Replace `data/matrix.json` first** — it is this kit's own construction and resembles no real
compatibility chart. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will**
need editing for a different sheet layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct.

If your sheets are unlabelled — the normal case — the field grade and both confusion matrices go
away, and the **consistency diagnostic** does not: `evals/judge.py` re-runs the matrix over each
reply's own extracted values and counts the replies whose stated verdict disagrees with it. No gold
needed. It is blind to a reply that misreads a cargo name and then reasons correctly from the
misreading, and it is reported as a diagnostic rather than as this kit's guardrail.

## What it does not do

It never authorises a load, never releases or quarantines a tank, never contacts anybody, and it is
not a substitute for the incoming product's safety data sheet or a competent person's assessment.
It reads one sheet at a time. It does not know the volume of the heel, only its name. It does not
know the tank's internal coating, its history of coating repair, or whether a discharge was partial.
It cannot resolve a cargo carried under a trade name that maps to several compositions, and it
treats a cleaning certificate as trustworthy without asking who issued it. It does no OCR — scanned
or image-only sheets extract no text. No auth, no database, no multi-tenancy, no deployment story.
It runs once per model, locally, and that run is what gets published.
