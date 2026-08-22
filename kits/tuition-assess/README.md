# tuition-assess — check a student account's assessed tuition and fees against the rate table

**UC041.** Point it at a student account's tuition assessment for one term, get a field table back —
plus a routing decision taken afterwards in pure code, from two of the extracted values: does the
assessed total match what the rate table entitles this account to, **which single step of the table
does it depart from**, and has the bill already posted? Nothing here re-bills an account, reverses a
charge, adjusts aid or contacts a student; the flag is a routing signal.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the bursar-note floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per assessment
python -m src.app                                      # the local UI on 127.0.0.1:8841
```

**You do not need a key to see this kit work, and it will never ask you for one.** The corpus and
the recorded runs ship in the repository, so `python -m src.app` starts, the 55-record picker
populates and the field table draws its twelve empty rows with nothing configured. Clicking Extract
returns a plain sentence saying nothing was called, not a stack trace. `check_labels` and
`--baseline` need no network at all.

## ⚠︎ No real student data, and none of it is derived from any

Tuition assessment is an **education-records** domain. A real record names a real student, their
enrolment, their aid, and often their residency history — none of which belongs in a public
repository under any licence. **Every record here was written by `tools/build_corpus.py` from a
fixed seed (`SEED = 20260822`).** Nothing is drawn from, sampled from, anonymised out of or
paraphrased from a real student account. No real institution, published tuition schedule, fee bill,
waiver programme or residency regulation is named or reproduced. The rebuild is byte-identical, and
`data/SOURCES.md` documents the whole construction.

**The rate table below is invented too.** It resembles no institution's approved schedule, and it
should be the first thing a forker replaces.

## Correctness is arithmetic with an order. Neither free-text line is evidence about it.

```
correct_total(residency_tier, enrolled_credits, course_level, waiver_type):

  a. TUITION        credits >= 12  ->  flat term rate   In-State 4600   Out-of-State 13200
                    credits <  12  ->  credits x        In-State  410   Out-of-State  1180
  b. DIFFERENTIAL   credits x  Lower Division 0   Upper Division 38   Graduate 65
  c. MANDATORY FEE  full-time 612                part-time 306
  d. WAIVER, LAST   None                          waives nothing
                    Employee Tuition Remission    100 pct of (a) only
                    Staff Dependent Waiver         50 pct of (a) only
                    Regents Fee Waiver            100 pct of (a) AND 100 pct of (c)

  total = (a) + (b) + (c) - (d)          NO waiver ever reduces (b).
```

Four things about that table are stated to the model in full, because each is a reading a model
falls into on its own:

| | |
|---|---|
| **the full-time threshold is inclusive, and the flat band is cheaper** | exactly 12 credits is full-time, so tuition is the flat rate — **not** 12 × the per-credit rate. The two differ by **$320** in-state (4,920 against 4,600) and **$960** out-of-state (14,160 against 13,200), so reading the band wrong is worth money rather than being a rounding difference. **13 of these 55 records sit exactly on the threshold** and 7 sit one credit under it |
| **a mid-term reclassification does not reprice this term** | **20 records carry a residency reclassification** effective after the term's census date. It applies from the *following* term. **6 of them were assessed at the new tier anyway** — that is the fault — and **14 carry the same line correctly ignored**, so "a reclassification is on file" is a decoy rather than a giveaway |
| **the differential fee is zero for Lower Division and per credit for the other two** | and it is charged on top of the flat full-time band as well as on top of a part-time load. Being full-time does not fold it in |
| **a waiver that does not cover a charge is not an error** | three of the four waivers cover base tuition only, and none of the four ever touches the differential fee. A model that "corrects" an account because the mandatory fee survived a tuition waiver is wrong about the account, not about the fee |

The table lives in one function, `assess()`, and is used in three places — the corpus generator that
wrote gold, the prompt that asks the model, and the scorer that grades it — so the kit cannot drift
about what "correct" means. **The bursar's own note and the residency action line are fields to copy
and nothing else.** Both reach the model on every record; neither is an input to any rule.

## Every variance has exactly one explanation — and the corpus asserts it per record

`variance_reason` is only an honest field if a wrong total has one true cause. So each mis-assessed
record is built by re-running `assess()` with **exactly one** decision substituted, and then
`_verify()` checks that **no other** single substitution reproduces the same number. A total two
different single mistakes could both explain is re-drawn under the seed rather than shipped with an
arbitrary label; **one re-draw** was needed on this seed. `evals/check_labels.py` re-runs that check
independently before anything may spend.

The mix on this seed: 28 correctly assessed, 27 mis-assessed — 8 credit band, 6 residency tier,
6 differential fee, 4 waiver coverage, 3 mandatory fee. **The variances are not all large:** the
smallest is **$110**, the median **$320**, the largest **$8,600**. A corpus whose planted errors are
all four-figure measures whether a model can spot a big number, not whether it can run a rate table.

## The guardrail is a business condition, and it needs labels — which is the honest half

> **Is this the account somebody has to fix today?**

`src/extract.py::compute()` routes an account when the assessed total is wrong **and** the bill has
already posted. A mis-assessed account still in draft can simply be corrected before it goes out;
the same variance on a posted bill means a corrected bill or a refund against a balance the student
may already have paid — and, in a real office, an aid recalculation behind it. **14 of the 55
records are mis-assessed and already posted.**

⚠︎ **This is the kit's own simplification, not any institution's billing-adjustment policy.** No
published schedule, regulation or bursar procedure was consulted, and none is reproduced. A real
office weighs the dollar size of the variance, whether aid has disbursed against it, and any
refund-deadline rule. Two booleans is the smallest rule that is genuinely useful and readable off a
single reply, and it should be the first thing a forker replaces.

Because it is a business condition, **it can only be scored where somebody wrote down the right
answer.** The kit is explicit about that, and it reports a no-gold *consistency diagnostic* beside
it — does the reply's own verdict survive the rate table re-run over the reply's own values? — so a
forker with unlabelled records still has one figure to watch on day one. That diagnostic is **not**
called the guardrail, and it is blind to the same case the guardrail is: a reply that misreads the
credit load and then judges its own misreading correctly.

## What it measures, and the two accounts that were never judged

Two models, same 55-record corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-tuition-assess.json`, `eval-r002-tuition-assess.json`).

**Assessment accuracy against gold is the headline**, because whether the total is right is the
whole question, and *variance* is the positive class: an account charged the wrong amount that gets
called correct is the error a bursar's office pays for. On the accounts each tier actually answered,
**neither got a single verdict wrong** — 26 of 27 variances caught, 28 of 28 correct assessments
left alone, 1.00 precision on both, 0.963 recall. The review flag fired on 14 of 14 with no false
alarms on both tiers, and no reply on either tier disagreed with its own numbers.

**But coverage is 98.18 %, not 100, on both tiers — and each lost a different account for a
different reason. Neither loss is a wrong answer, which is what makes them worth printing:**

| tier | lost | why |
|---|---|---|
| fast | `STU-0050` | `finish_reason: "length"` at **exactly 4,000 output tokens** with an **empty** reply. The ceiling was a measurement, not a guess: a three-record calibration run at a deliberately loose 8,000 returned at most **1,209** output tokens with `finish_reason: "stop"` on all three, which made 4,000 look like 3.3× of headroom. Record 50 of 55 went straight through it. The deliberating tier answered the same record in 3,202 tokens |
| deliberating | `STU-0011` | `<urlopen error [Errno 60] Operation timed out>`. `src/adapters/__init__.py` backs off on HTTP 408/429/5xx, because those arrive as an `AdapterError` carrying a status; a socket timeout arrives as a bare `URLError` and falls straight through. **The model was never asked twice.** That is a defect in the retry policy, not a model failure, and it is four lines to fix |

**An account that returned nothing is not a clean bill of health**, and nothing downstream can tell
the difference by reading the verdict alone. Every rate on this page silently re-based onto 54.
`evals/run.py` records the cause, the finish reason and the token count for each one, and
`Guardrails.add_first` on the published kit page names the missing assertion: *every record in the
corpus must appear in the scored set, or the run fails.*

On extraction the deliberating tier was exact — 648 of 648 cells. The fast tier missed one: the
`variance_reason` on `STU-0027`, discussed below. All 324 returned values on the six spannable
fields located back to their own section of the record on both tiers.

**Only one published figure separates the two tiers**, and it separates them by one record: the
variance reason, **25 of 27** on the fast tier against **26 of 27** on the deliberating one. Neither
invented a reason on any of the 28 correctly assessed accounts. Everything else ties. See
`Business.not_good_enough` on the published kit page for what 55 records cannot tell you.

### The one substantive model error is a finding about the vocabulary

`STU-0027`, fast tier. An Out-of-State Upper Division account at 5 credits with a Regents Fee
Waiver: tuition 5,900, differential 5 × 38 = 190, mandatory 306, waiver 100 pct of tuition **and**
mandatory = 6,206, so the table says **190**. The bursar system assessed **0**.

Gold calls that `differential fee` — the differential was charged at Lower Division's zero rate. The
model answered `waiver coverage` — the waiver reached a charge it does not cover. **Both describe
the same missing $190.** The corpus's five-member departure vocabulary has no member for *"the
waiver swallowed the differential"*, so the single-explanation assertion passes and the model is
scored wrong for an answer a bursar would accept.

That is a finding about the vocabulary rather than about the model, and it is the reason the reason
grade is the figure that does **not** travel to your own accounts.

## The baseline is shipped, including where it wins and exactly where it does not

`--baseline` is a non-LLM extractor: eight fixed concerned-sounding phrases in the bursar's note, no
key, no cost. It is very good at the parts that are regex work — **all ten structured fields, 550 of
550 cells, perfect** — and it is a deliberate *tone floor* on the two decided ones: it reads the
bursar's prose and never runs the rate table, which is precisely the shortcut the prompt forbids.

It scores **60.0 % assessment accuracy — 22 of 55 records wrong**, with **9** mis-assessed accounts
called correct and 13 correct ones called failures. Every one of those 22 is a register mismatch
this corpus planted on purpose, and both model tiers got all 22 right. The variances it walked past
run from **$160 to $4,300**.

On `variance_reason` it scores **18.5 %** — and even that overstates it, because the floor answers
the corpus's modal reason on every record it calls wrong, so those 5 hits are the modal class coming
up rather than a reason being named. It also invented a reason on 13 of the 28 correctly assessed
accounts; neither model tier did that once.

Making the floor perfect would take twelve lines of arithmetic over values it already extracts
correctly. Not doing so is the design — the floor is the *shortcut*, and the gap it opens is the gap
between reading prose and running the table.

**And watch what happens to the guardrail downstream.** The floor extracts `bill_status` correctly
every single time, by regex — and its review flag still scores only **10 of 14 with 8 false alarms**
(0.5556 precision), because it inherits the tone-derived verdict. That is the honest lesson of
shipping a business-condition guardrail: *it is only ever as good as the field it reads.* The
no-gold consistency diagnostic, by contrast, catches **all 22** of the floor's verdict errors with
no labels at all.

The floor's keyword list was checked against **both** note registers before it was ever run — a
sibling kit earlier in this series shipped a keyword that fired on a negation inside a breezy note
and mis-registered four records for days. `evals/check_labels.py` asserts that property here for
free, before any run may spend.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and
the assessment verdict is arithmetic, which is the one thing you should never ask a model to
adjudicate. Adding an LLM judge would add cost and a second source of disagreement to a comparison
that does not need one.

One scoring choice is worth calling out. **The reason grade's denominator is the 27 records that
carry a variance, not 55.** Twenty-eight of the fifty-five rows have the answer `none`, which is
also what a model gets for free by saying nothing interesting; scoring the reason over all 55 would
report better than 50 pct for a run that never named a single real variance correctly. The
opposite-direction error — a reason offered on an account that is fine — is counted beside it and
never inside it.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
twelve fields × the whole record is twelve times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the instructions, not by the record** — on the
worked example the system prompt is 934 tokens and the field schema 823, against 206 for the account
itself: **1,757 of 1,963 input tokens, 89 pct, are the same on every call.** This kit's fixed prefix
is larger than its siblings' because the whole rate table is stated in it.

The saving is usually invisible, because the sections that get sent would have been sent anyway.
Here there is one you can point at: **`Campus` is mapped by no field at all**, so the union of the
mapped sections leaves it out and it never reaches the provider. And note what `SECTION_HINTS` maps
`assessment_correct` and `variance_reason` to — the five facts the table reads, and **neither**
free-text line. That is not a fence: both decoys reach the model anyway, as fields in their own
right. It is the map of where the answer actually lives.

⚠︎ **`_locate()` scopes each span search to the field's own sections first, and on this corpus that
is measured to change nothing** — re-locating all six spannable fields across all 55 records
unscoped produces 0 differences out of 324 values, because the field the scoping was written for is
an enum and is never spanned at all. It is kept as precaution against a class that is real in the
sibling kits, and it is recorded here as precaution rather than published as a saving.

## `MAX_TOKENS` is a measurement, and the measurement is in the repository

`results/eval-c000-calibrate.json` is a three-record run at a ceiling of 8,000, made before either
scored run: 382, 460 and 1,209 output tokens, `finish_reason: "stop"` on all three. The shipped
`MAX_TOKENS = 4000` is that observed maximum with about 3.3× of headroom. One record in 55 blew
through it anyway, which is the finding rather than the footnote: **a ceiling measured on three
records is a fact about three records.** `evals/run.py` publishes `output_tokens_max`,
`output_tokens_min` and the `finish_reasons` histogram on every run so the next ceiling problem
arrives as evidence rather than as a mystery. `--max-tokens` on the harness is how the calibration
above was taken; it is a measurement tool, not a knob to turn when a run misbehaves.

## Point it at your own assessments

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
account. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different bursar extract; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct. `assess()` and `compute()` in `src/extract.py`
are this kit's own invented rate table and routing rule; replace them with your own board-approved
schedule before trusting anything this computes.

**Know which claim stops being true first.** Every score here was measured on a corpus where each
account departs from the rate table in **at most one place** and the variance vocabulary has exactly
five members. A real mis-assessment with two causes has no single correct `variance_reason`, so the
reason grade does not carry over even where the yes/no verdict does.

If your accounts are unlabelled — the normal case — the field grade, the confusion matrix, the
reason grade and the review flag's score all go away. What does not go away is the consistency
diagnostic, and that is the one figure you can compute on day one.

## What it does not do

It never re-bills an account, reverses a charge, releases a hold, adjusts aid or contacts a student,
and it is not a substitute for a bursar signing against an approved schedule. The guardrail reads
two fields out of the reply: if the model misreads the credit load and then judges that misreading
consistently, the account is routed — or not routed — on a wrong number, and nothing here re-reads
the document to catch it. **And an account that returned no reply at all is flagged by nothing** —
it is simply absent from the scored set, which is how both tiers lost one.

It reads one account for one term at a time. It never prorates a partial withdrawal, handles a
student who drops below the threshold after the census date, stacks two waivers with an ordering
rule between them, prices a programme on its own board-approved rate outside the standard bands, or
applies a differential course by course rather than one level for the whole load. No OCR — a PDF
bill or a screenshot of a student information system extracts no text, which is how a great many
real assessments arrive. **No red-team run exists for this kit:** it carries *two* externally-authored
free-text fields, and whether an instruction hidden in either could move the verdict is unmeasured
and named as unmeasured rather than quietly counted as a boundary that holds. No auth, no database,
no multi-tenancy, no deployment story. It runs once per model, locally, and that run is what gets
published.
