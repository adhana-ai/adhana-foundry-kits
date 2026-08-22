# partlife-recon — reconcile a life-limited part's hours and cycles against its record trail

**UC047.** Point it at a maintenance record pack for one life-limited component, get a field table
back — plus an escalation decision taken afterwards in pure code, from three of the extracted
values: does the record trail put this component inside both published limits, does the component's
own tag agree with the trail, and is somebody asking to put it back on an aircraft today?

⚠︎ **This reconciles records. It never issues an airworthiness determination and it releases nothing
to service.** Everything here is a statement about what a record trail substantiates and where it
disagrees with the tag. It reconstructs, it names every discrepancy and every gap, and it
escalates. A pack it does not flag has **not** been cleared by it — it has been left alone by it.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-tag --baseline      # free — the tag floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.measure_cap --run-id c001-<model>     # SPENDS a few calls: measures MAX_TOKENS
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per pack
python -m src.app                                      # the local UI on 127.0.0.1:8847
```

**You do not need a key to see this work, and the kit never asks you for one.** The corpus and all
the recorded results ship in the repo. `python -m src.app` renders offline with no key configured:
the 50-pack picker populates, the field table draws, the record pack is readable, and clicking
Reconcile returns a plain sentence saying nothing was called — not an error, and not a reassuring
blank. `python -m evals.check_labels` passes with no network access at all.

## The accumulated life is not printed anywhere on the pack

That is the whole kit. The totals a life limit is compared against are the **sum of every
installation period in the service record trail** — and the only totals that *are* printed sit on
the component's own tag, which is a transcription somebody made at some point.

```
life_status(trail_hours, trail_cycles, limit_hours, limit_cycles, record_gap):
    at or past BOTH limits                    -> both_exceeded
    at or past the hours limit                -> hours_exceeded
    at or past the cycles limit               -> cycles_exceeded
    a records gap is declared                 -> cannot_determine   (checked LAST)
    otherwise                                  -> within_limits
```

Six things are stated to the model in full, because each is a reading a reader going quickly falls
into on their own:

| | |
|---|---|
| **hours and cycles are summed separately** | each period ran on a different airframe at a different hours-per-cycle ratio, so one total can never be scaled off the other. `evals/check_labels.py` asserts that **no two periods within a pack share a ratio** |
| **an overhaul resets one counter and not the other** | *"time since overhaul reset to 0 hours / 0 cycles; time since new is unaffected"* — the limit is against time since **new**. Restarting the accumulation there undercounts the component, usually enormously. **16 of these 50 packs** carry an overhaul line, with accruing periods asserted on both sides of it, so restarting always costs something |
| **a declared gap contributes nothing** | a period marked `accrual NOT RECORDED` is stated and its accrual is not. The conservative move is to say so, never to interpolate it or fall back on the tag |
| **the exceedance checks outrank the gap check** | a missing period can only **add** accumulated life — it can never bring a component the surviving records already put at or past a limit back inside it. So a gap makes *within limits* undeterminable and leaves *exceeded* perfectly determinable. **5 of the 12 gapped packs are already past a limit**, so the case is measured rather than assumed away |
| **the limit is inclusive** | exactly at the published limit there is no life remaining. **8 packs sit exactly ON a limit** |
| **the reviewer's note is a field to copy, not evidence** | **20 of 50** carry a note written in the register that contradicts the record. `check_labels` asserts that no note template contains a digit or any of the words *hour, cycle, limit, exceed, within, gap, tag* — so it can never be evidence even by accident |

The rule lives in one function, `life_status()`, and is used in three places — the corpus generator
that wrote gold, the prompt that asks the model, and the scorer that grades it — so the kit cannot
drift about what "past its limit" means.

## The corpus is entirely invented, and it has to be

**No real manufacturer, engine type, part number, operator, airframe registration, airworthiness
directive or maintenance manual is named or reproduced anywhere in this kit.** *"Life limit"*,
*"cycles since new"*, *"time since overhaul"*, *"life-limited part"* and *"return to service"* are
ordinary continuing-airworthiness-records vocabulary; the **structure** of a record pack is modelled
and nothing else. Every limit, ratio, identifier and threshold below was invented for this corpus.
There is no personal data in it by construction.

`tools/build_corpus.py` generates all 50 packs from a fixed seed (`20260822`), byte-identically on
every run — a real pack names a real operator and a real part and is primary evidence in a regulated
file, so there is no public corpus of *(record trail, correctly-reconciled accumulated life)* pairs,
for the same reason there is no public corpus of bank statements. Generating it also makes the label
mechanical: gold's two totals are **re-read off the corpus text with a regex and re-summed** by
`evals/check_labels.py` before any run is allowed to spend. See `data/SOURCES.md`.

## The guardrail is a business condition, and it needs labels — which is the honest half

`src/extract.py::compute()` escalates a pack when it carries a discrepancy — the trail does not put
the component inside both limits, **or** the component's own tag disagrees with the trail — **and**
the requested disposition is *return to service*. The same discrepancy on a component headed for
shelf storage still has to be resolved; it does not have to be resolved before an aircraft moves.
That is what *escalated before release* means, and it is the only thing this flag does.

⚠︎ **This is the kit's own simplification, not any operator's or authority's release procedure.** No
airworthiness regulation, approved maintenance organisation exposition or continuing-airworthiness
management procedure was consulted, and none is reproduced. A real records desk weighs which
discrepancy it is, what evidence can still be recovered, and who is authorised to accept what. Three
fields and a boolean is the smallest rule that is genuinely useful and readable off one reply, and
it should be the first thing a forker replaces.

⚠︎ **A `no` means this rule found nothing to raise. It does not mean the component may fly.** The UI
says exactly that, and it prints `not computed — one of the three values the rule needs was missing`
rather than a comfortable "no" when the reply is short a field. An unknown is not a pass.

Because it is a business condition it can only be scored where somebody wrote down the right answer.
The kit reports two no-gold **consistency diagnostics** beside it — does the reply's stated life
status survive the rule re-run over the reply's *own* totals, and does its tag comparison survive
the same treatment — precisely so a forker with unlabelled packs has something to watch. Neither is
called the guardrail, and both are blind to the failure that matters most here: **a reply that sums
the trail wrong and then reasons about its own wrong total perfectly is self-consistent and still
wrong.**

## What it measures, and the number that matters most

Two models, same 50-pack corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-partlife-recon.json`, `eval-r002-partlife-recon.json`).

**The headline is cleared versus NOT cleared, and *not cleared* is the positive class** — a
component the records do not clear that gets called `within_limits` is the failure that matters on a
pack headed back onto an aircraft. **Both tiers refused to clear every one of the 26 not-cleared
packs they answered: 1.00 recall, 1.00 precision, zero false negatives.** Both were exact on every
reconstructed total — **198 of 198 across the two runs** — and both got all 12 gapped packs, all 5
where the surviving trail is already past a limit, all 8 sitting exactly on a limit, all 16 with an
overhaul line, and all 14 disagreeing tags. The escalation flag fired on 19 of 19 with no false
alarms on both tiers, and no reply on either tier ever disagreed with its own arithmetic.

**Neither tier came out clean, and they failed in different places.**

- The **fast tier** answered **49 of 50 packs**. REC-0029 was lost on call 43 to
  `<urlopen error [Errno 60] Operation timed out>` — a socket-level failure that never becomes an
  HTTP status, so the adapter's retry policy, which only understood status codes, treated it as
  terminal. Everything it *did* answer was exact: 637 of 637 cells, 343 of 343 spannable values
  located. On a scoreboard that is one point of coverage. On a records desk it is a component nobody
  reviewed, and the only place it appears is a `failures` array at the bottom of a JSON file. (The
  pack happened to be within limits. That is luck, not design.)
- The **deliberating tier** answered all 50 and was the tier that got something **wrong**. On
  REC-0026 and REC-0046 it returned the reviewer's note as *"…before anyone signs."* where both
  packs say *"…before anyone signs it."* — a silent one-word truncation of a field whose whole
  instruction is *copied verbatim*, on the easiest task on the page, from the tier costing 26% more
  and taking about twice as long. **648 of 650 cells**, and those same two cells are the run's only
  span failures (348 of 350), because `src/segment.py::locate()` is deliberately literal and gives a
  paraphrase no span rather than an approximate one.

**Two tiers clearing the arithmetic is a real result and a small one.** Fifty packs in one
consistent plain-text layout, with two to four periods each, is a floor test: it convicts the
shortcut decisively and it tells you nothing about a twenty-period trail, a scan, a handwritten
entry or a limit revised mid-life. See `Business.not_good_enough` on the published kit page.

### `MAX_TOKENS` is a measurement, not a guess

`evals/measure_cap.py` spends a handful of calls at a deliberately generous ceiling, on the
**longest** packs in the corpus rather than typical ones — the reply carries the reviewer's note back
verbatim, so the pack with the most trail lines is the one whose reply is biggest. Five probe calls
before either scored run returned **466, 506 and 809** output tokens on the fast tier and **834 and
976** on the deliberating tier, every one finishing on `stop` rather than `length`. So the probe
measured the *reply* and not the *ceiling*, and `MAX_TOKENS = 2000` is roughly twice the longest
reply the more verbose tier produced. A ceiling copied from a sibling kit is a number nobody measured
on this prompt; a ceiling with no headroom is a truncated reply that fails to parse and reads on a
results page as a model that could not do the task.

## The baseline is shipped, including where it wins and exactly where it does not

`--baseline` is a non-LLM extractor with a single named assumption — `TAG_IS_THE_RECORD` — and it is
the shortcut a rushed records review actually takes: read the figures printed on the component's own
tag, treat them as the accumulated life, and never reconstruct the trail. No key, no cost.

It is very good at the parts that are regex work: **all nine fields the pack states in one place,
450 of 450 cells, perfect** — both identifiers, both published limits, both tag figures, the declared
gap, the requested disposition and the reviewer's note. Its failures are concentrated in exactly the
four fields nobody can regex — the two summed totals and the two derived comparisons: **40 of 200
wrong** (`tag_agrees` 14, `trail_hours` 10, `life_status`
8, `trail_cycles` 8), for **93.85% overall**. Most of this task is not the hard part, and the honest
reading of that number is that the free floor gets most of it.

Where it fails, it fails in the direction that costs something:

- **84% life-status accuracy, 0.6923 recall on not-cleared — 8 components the records do not clear,
  called cleared.** Seven are the seven packs whose records are incomplete: the floor never looks at
  the trail, so a declared gap changes nothing for it.
- The eighth is **REC-0013**, and it is the clearest single statement of what the kit is for. The
  trail sums to exactly **24,000 hours** against a published limit of **24,000** — inclusive, so no
  life remains — and the component's tag reads **23,836**. The floor read the tag, found 164 hours of
  margin that does not exist, and answered `within_limits`. Both tiers reconstructed 24,000 and
  answered `hours_exceeded`. A transcription 0.7% low is the difference between a part on an aircraft
  and a part in a scrap bin.
- **0.00 recall on tag agreement.** It answers `yes` on all 50 by construction — a floor that
  believes the tag *is* the record can never find the tag disagreeing with anything. All 14 real
  disagreements missed; both tiers caught all 14.
- **And watch what happens to the guardrail downstream.** The floor reads `disposition_requested`
  correctly by regex every single time, and its escalation still fires on only **14 of 19**, missing
  5, because it inherits a tag-derived life status and a tag comparison that is constant. That is the
  honest lesson of shipping a business-condition guardrail: *it is only ever as good as the fields it
  reads.*

Making the floor much better would take three lines — every `accrued N hours / M cycles` line is one
regex away and summing them is trivial. Not doing so is the design: the floor is the *shortcut*, and
the gap it opens is the gap between reading the tag and reconstructing the trail.

**The consistency diagnostics catch some of that and are honest about the rest.** Run the floor's own
output through them and the life-status diagnostic fires on **7 of its 8** wrong verdicts with no
gold at all — but it is silent on REC-0013, whose numbers are internally consistent with its own
wrong answer, and it is silent on **all 14** tag errors for the same reason. That is the measured
shape of what a no-gold check can and cannot see.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and the
thing being graded is **arithmetic**, which is the one thing you should never ask a model to
adjudicate. Adding an LLM judge would add cost and a second source of disagreement to a sum that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py`, `evals/measure_cap.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
thirteen fields × the whole pack is thirteen times the input tokens of sending each field the
sections that could possibly state it. **The bill is driven by the context, not by the question** —
on the worked example, the system prompt and field schema are **1,686 of 2,039 input tokens** and the
pack itself is **353**. The instructions are long here on purpose: the accumulation rules and the
five-way priority order are stated in full rather than left to be inferred, and that decision is most
of the bill.

The saving is usually invisible, because the sections that get sent would have been sent anyway. Here
there is one you can point at: **`Holding Location` is mapped by no field at all**, so the union of
the mapped sections leaves it out and it never reaches the provider. And note what `SECTION_HINTS`
maps `life_status` to — the trail, the declared gap and the two published limits, and **not** the
component's tag. That is not a saving; the tag reaches the model anyway, as two fields in its own
right. It is the map of where the answer actually lives.

### A computed total has no span, and the schema says so

Every sibling kit derives spannability from the field *type*: an enum is a fixed value, everything
else can be located in the document. That rule is wrong here for exactly two fields. `trail_hours`
and `trail_cycles` are **sums** and appear nowhere in the pack — on REC-0015 the limit, the tag and
the reconstructed total are all `16000 / 20000`, so a document-wide search for `16000` would find the
tag and cite it, producing a span pointing at the one figure the total is deliberately *not* copied
from. So `data/fields.json` carries an explicit `"spannable": false` on those two and the span
denominator excludes them, rather than counting them as misses and punishing the kit for doing the
arithmetic. Every other value is searched **inside the field's own mapped sections first**, and only
falls back to the whole document when it is found nowhere.

## Point it at your own record packs

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold row per pack.
`SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need editing for a
different pack layout; when it does not match, selection falls back to the whole document — slower,
more expensive, always correct. **`life_status()` and `compute()` in `src/extract.py` are this kit's
own invented limit structure and escalation rule and must be the first things you replace with your
own approved procedure.** Any field of yours that is a *sum* rather than a quotation needs the
`spannable: false` flag too.

If your packs are unlabelled — the normal case — the field grade, the life-status matrix, the tag
matrix and the escalation score all go away. What does not go away is the two consistency
diagnostics, and those are the figures you can compute on day one, with the limits named above.

## What it does not do

**It never issues an airworthiness determination, a life-remaining certificate, a release to service,
a quarantine or a scrap decision, and it is not a substitute for a qualified records review.** It
raises packs for a person and does nothing else — `extract()` returns a boolean, `app.py` serves it
in a JSON body, and no code path performs a write or an outbound call other than the single
completion request.

The guardrail reads three fields out of the reply: if the model sums the trail wrong and then reasons
about its own wrong total perfectly, the pack is stopped — or not stopped — on a wrong number, and
nothing here re-reads the document to catch it. It reads one pack at a time and never compares a
component against its own earlier review, its sub-assemblies' separate limits, or a limit revised
part-way through its life by a later directive. It sums what the trail states and has **no notion of
a trail being internally impossible** — periods that overlap, run backwards or leave an unexplained
span between two dates are invisible, and that is the more common shape in a real file. It does no
unit conversion. No OCR — a scanned pack or a handwritten trail entry extracts no text, which is how
a great many real records arrive.

**Named gaps in what has been measured here:**

- **The transport fix is unmeasured.** `src/adapters/__init__.py` now carries a `transport` flag and
  retries a socket failure with the same bounded backoff. It landed **after** r001 and no run has
  been fired since, so the post-fix document-loss rate is unknown.
- **The deliberating tier's truncation is uncharacterised** — twice, on the same note template, out
  of 50 packs. Enough to record and not enough to say whether it is systematic. Nothing was re-run to
  find out.
- **There is no red-team run.** The reviewer's note is the one externally-authored field a live
  deployment would carry, and whether an instruction hidden inside it could move a life-status answer
  is **unmeasured**. On a kit adjacent to a release decision that is the gap to read first. The
  planted ambiguity in this corpus tests confusable plain *register*, not an adversarial attacker,
  and those are different tests.
- **The escalation rule is invented policy** scored against a gold built from the same three fields,
  so a perfect score means the code agrees with itself about packs the model read correctly. No
  records or quality reviewer has looked at the 19 packs it picked.

No auth, no database, no multi-tenancy, no deployment story. It runs once per model, locally, and
that run is what gets published.
