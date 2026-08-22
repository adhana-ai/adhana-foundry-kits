# cam-precheck — check one CAM reconciliation line against the tenant's own lease terms

**UC044.** Point it at one line of a commercial-property operating-expense reconciliation, get a
field table back — plus a routing decision taken afterwards in pure code: does the amount billed to
this tenant match what its lease actually permits, and if not, has the statement already gone out?
Nothing here issues a corrected statement, credits a tenant or releases a reconciliation; a human
releases.

MIT. Python standard library plus a minimal JS UI. One model, one key. Two tiers measured, and the fast one twice.

```bash
python -m evals.check_labels                            # free — validates the gold set
python -m evals.run --run-id b000-tone --baseline tone  # free — the accountant-note floor
python -m evals.run --run-id b001-name --baseline name  # free — the category-name floor
python -m evals.run --run-id t000-stub --stub           # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>               # THIS SPENDS MONEY: one call per line
# a kit-local .env holding one MODEL= line pins this kit to a tier and inherits everything else
python -m src.app                                       # the local UI on 127.0.0.1:8844
```

## What makes this one different: the model has to COMPUTE, not copy

Every sibling extraction kit in this series asks a model to read values off a document and then
apply a comparison or a threshold to them. This one asks for a **dollar figure that appears nowhere
in the document**, arrived at through four dependent stages:

```
permitted(line):
    STAGE 1  poolable    landlord_overhead / leasing_cost        -> 0
                         capital_improvement, no amortization    -> 0
                         capital_improvement, amortized over N    -> gross / N     (ONE instalment)
                         routine_operating                       -> gross in full
    STAGE 2  gross-up    occupancy_sensitive == yes AND occupancy < 95
                                                                 -> x 95 / occupancy
    STAGE 3  pro rata    x (tenant_area + expansion x (13 - month) / 12) / building_area
    STAGE 4  cap         annual      -> min(amount, basis x (1 + pct/100))
                         cumulative  -> min(amount, basis x (1 + pct/100) ** periods)
    line_ok = "yes" iff |billed - permitted| <= 1.00
```

That rule lives in **one file** — `src/rule.py` — and five things read it: the generator that wrote
gold, the prompt that states it to the model in words, the extractor that re-runs it over the
model's own reply, the scorer that re-derives gold's truth at score time, and the pre-flight that
refuses the run if a single label disagrees with it. There is no second copy to drift, which is a
deliberate change from the sibling kit this one is modelled on: that one kept the same logic in two
files under a comment saying they were the same function, and nothing enforced it.

Four things about the rule are hard on purpose, and each appears on **both sides** of the verdict:

| | in this corpus |
|---|---|
| **an amortizable capital item is PARTLY billable** — "capital is excluded" is wrong here | 8 lines |
| **the category NAME is a label; `expense_class` is the classification** | 14 lines named "Parking lot resurfacing", "Property management fee", "Roof membrane patching"… on lines the lease permits in full |
| **gross up BEFORE you cap** — a ceiling with slack against the ungrossed share can bind against the grossed-up one | 3 lines, the sharpest in the corpus |
| **a mid-year expansion is a weighted average** — not the start area, not the expanded area for twelve months | 12 lines carry an expansion |

## What it measures, and the number that moved

Three scored runs across two tiers on the same 55-line corpus, same judge — see the committed run
records in `results/`. The fast tier was run **twice**, and that is the reason this table says
anything at all.

| | `r001` fast | `r002` fast | `r003` deliberating |
|---|---|---|---|
| extraction, 1,100 cells | **1,100** (100%) | **1,099** (99.91%) | **1,100** (100%) |
| arithmetic within $1.00, 55 lines | **55** (100%) | **54** (98.18%) | **55** (100%) |
| `line_ok` accuracy, 55 lines | **100%** | **100%** | **100%** |
| review flag, 7 to find | **7/7**, no false alarms | **6/7**, no false alarms | **7/7**, no false alarms |
| span rate, 506 returned values | **100%** | **100%** | **100%** |
| cost a line, published card | $0.0052898 | $0.0052298 | $0.0060963 |
| p50 latency | 9.6s | 9.8s | 22.7s |

⚑ **The tiers tie. The repeat does not, and that is the finding.** The deliberating tier costs
15.25% more a line and takes 136% longer at the median for a board identical to the fast tier's
first run. Meanwhile the fast tier's *second* run — same model, same prompt, same 55 lines, nothing
separating it but nondeterminism — came back on one line (`CAM-0032`) with a permitted amount of
**$45,941.25** where the lease permits **$25,835.88**, off by $20,105.37.

**Either tier, run once, would have published a clean sweep.**

Watch what that single number did to each published figure:

- **The verdict grade did not move.** The model still answered `line_ok = "no"`, and it was right —
  the line *is* billed wrong. 100% on all three runs.
- **The self-consistency diagnostic did not fire.** The reply's own verdict follows correctly from
  the reply's own (wrong) number. Zero disagreements on all three runs, which is exactly the blind
  spot that diagnostic is documented to have.
- **The guardrail missed it.** `CAM-0032` is a $1,116.97 **over**charge on a statement already
  issued — one of the seven lines the flag exists to catch. Because the model's permitted amount was
  *higher* than the billed amount, the overcharge read as an undercharge and the routing rule stayed
  quiet. Recall 0.8571.

**One field, one run, and only one of five published figures noticed.** That is why
`arithmetic_accuracy_pct` is reported on its own rather than folded into the extraction grade, and
why the guardrail's dependence on a computed field is stated on the page instead of buried.

## Two free baselines are shipped, because there are two shortcuts to convict

| floor | what it does | verdict accuracy | arithmetic | review flag |
|---|---|---|---|---|
| `--baseline tone` | reads the accountant's note and never does the arithmetic | **60.0%** — 22 of 55 wrong, 12 wrongly-billed lines called fine | 0 of 55 | **never fires at all** |
| `--baseline name` | does **every stage of the arithmetic correctly** and decides what is poolable from the expense's NAME instead of its class | **78.2%** — 12 of 55 wrong | 33 of 55 | 7/7 recall, **0.35 precision** (13 false alarms) |

The name floor is the interesting one. It imports `src/rule.py` for stages 2, 3 and 4, so nothing
about its failures can be blamed on it being sloppily written — it is **three characters from
correct**, and reading `expense_category` instead of `expense_class` costs it every amortizable
capital line (0 of 4) and three of the four decoy-named operating lines it was shown.

The tone floor's review-flag row is worth its own sentence: it scores **0.0**, not because it
guesses badly but because it cannot answer at all. A business-condition guardrail that reads a
computed field has nothing to read when the shortcut computes nothing, and the grader counts those
55 rows as `unanswered` rather than folding them into "no follow-up needed". An unknown is not a
pass.

Both floors' keyword lists were checked against the corpus's own vocabulary **before either was
first run** — `evals/check_labels.py` asserts that every note template classifies to the register it
was authored in and every expense category to the family it was authored in, before any run may
spend. A sibling kit earlier in this series shipped a keyword that fired on a negation inside a
breezy note and mis-registered four records for days.

## There is no LLM judge in this kit

Gold is exact and every answer is one value, so `==` settles it — and the thing being judged is
**arithmetic**, which is the last thing to ask a language model to adjudicate. One field is graded
to a tolerance rather than to equality: `permitted_amount_usd`, at $1.00, the same bar `line_ok` is
defined at, so a reply cannot be scored right on the verdict and wrong on the number the verdict
came from.

## MAX_TOKENS is a measurement here, and most of it is invisible

Three calibration calls on the most arithmetically loaded lines returned 1,909 / 1,420 / 1,644
output tokens — of which **1,675 / 1,190 / 1,414 were reasoning tokens the provider reports and
nobody reads**. The JSON that actually arrives is about 234 tokens. A ceiling set from the length of
the visible reply would be 250 and would truncate every call.

The shipped ceiling is 6,000. The scored runs then went as high as **3,708** output tokens on a
single line — 94% above the calibration maximum — so three records were not enough to bound it, and
the run records carry `output_tokens_max`, `replies_at_ceiling` and every reply's `finish_reason` so
that gap is a fact rather than an inference. Nothing was truncated on any of the three runs.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| the rule | `src/rule.py` — the four stages, the only copy |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
twenty fields × the whole record is twenty times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the instructions, not by the document** — on
the worked example the system prompt and field schema are 1,995 of 2,318 input tokens and the
reconciliation line itself is 323.

Note what `SECTION_HINTS` maps the two computed fields to: the thirteen sections the arithmetic
actually reads, and **not** the accountant's note and **not** the expense category. That is not a
saving — both reach the model anyway, as fields in their own right. It is the map of where the
answer actually lives.

`Managing Agent` is mapped by nothing and is therefore never sent. It is the one part of the saving
a reader can point at.

## Point it at your own reconciliations

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per line.
`SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need editing for a
different statement layout; when it does not match, selection falls back to the whole document —
slower, more expensive, always correct.

**`src/rule.py` is the first thing to replace.** Its four stages, its 95% gross-up floor and its
$1.00 tolerance are this kit's own invented lease structure. No executed lease, published lease form
or industry standard form was consulted, and none is reproduced. In particular this kit caps the
**line**, and a real operating-expense cap almost always ceilings the tenant's total controllable
pool for the year.

If your lines are unlabelled — the normal case — the field grade, the arithmetic figure and both
confusion matrices go away, and the self-consistency diagnostic does not. That is the one figure
here you can still compute on day one, and this kit's own `r002` is the proof of how little it
catches: it stayed silent through the only error either run made.

## What it does not do

It never issues a corrected statement, credits a tenant, files an audit response or releases a
reconciliation. `line_ok` is a computed field and `needs_review` is a routing signal; a human
releases. It reads one line at a time and never compares a line against the prior cycle's, against
the same pool at a neighbouring property, or against a base-year stop. It does no OCR — a scanned or
rendered statement extracts no text. It does not know that a cap normally applies to an aggregate,
that an admin fee is often computed on a pool that already contains it, or that two buildings under
one lease allocate between themselves. No auth, no database, no multi-tenancy, no deployment story.
It runs locally, once per model, and that run is what gets published.
