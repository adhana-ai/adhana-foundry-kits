# usage-variance — reconcile a telecom invoice line against its mediated usage

**UC040.** Point it at one invoice line and the mediated-usage summary behind it, get a field table
back — plus a routing decision taken afterwards in pure code, from two of the extracted values:
does the charged quantity match the usage that should have been billed, **why not**, and has the
invoice already gone out? Nothing here raises a credit, reverses a charge, re-rates a suspense
bucket or contacts a customer; the flag is a routing signal.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the analyst-note floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per record
python -m src.app                                      # the local UI on 127.0.0.1:8811
```

**You do not need a key to see this work, and you are never asked for one.** The corpus and all
five recorded run files ship in the repo, so `python -m src.app` renders and stays browsable
offline: with no `API_KEY` configured, Extract returns a plain sentence saying nothing was called
rather than an error, every field reads *"not extracted yet"*, and the credit row reads *"not
computed — one of the two values the rule needs was missing"* rather than *"no"*. An unknown is
not a pass, in the UI as well as in the grader. `python -m evals.check_labels` passes with no
network access at all. A key is needed only to reconcile a **new** record or to re-run the eval
against your own numbers.

## The cause of a variance is arithmetic. The analyst's note is not evidence about it.

A reconciliation record puts five quantities, an invoice status and a billing analyst's own account
of the line on the same page. Only the quantities and the service type decide anything. The
mediated total is four **disjoint** parts:

```
mediated = rated + unrated + prior_period + confirmed_duplicates

billable = mediated - prior_period - confirmed_duplicates      (unrated STAYS in)
expected = round_up(billable, increment(service_type))
gap      = invoiced - expected
```

**The billing increment is a property of the service, and it is the first test.**

| service | unit | increment | why it matters |
|---|---|---|---|
| voice | seconds | 60 | whole-minute rounding — a 59-second gap is not a variance |
| data | KB | 1024 | whole-megabyte rounding |
| sms | messages | **1** | **no rounding tolerance at all** — a one-message gap *is* a variance |

One tolerance applied to all three is wrong in both directions at once: it forgives real SMS
variances and invents voice ones. **13 of these 55 records are SMS lines and none of them can carry
a `rounding` label** — `evals/check_labels.py` asserts that directly, and separately asserts the
boundary itself on every non-SMS row, at the edge rather than in the interior: a gap of one unit
under the increment must classify as rounding, and a gap of exactly the increment must not.

Then the gap is classified in a **priority order**, first match wins:

```
1. gap == 0                                         -> none
2. abs(gap) < increment                             -> rounding
3. gap < 0 and matches unrated_quantity             -> unrated_usage
4. gap > 0 and matches confirmed_duplicate_quantity -> duplicate_records
5. gap > 0 and matches prior_period_quantity        -> late_records
6. otherwise                                        -> unexplained
```

**Rounding is checked before any cause is named**, and that ordering is the point of the step. A gap
smaller than one increment is indistinguishable from a small missed block, so naming a cause for it
is a guess dressed as a finding.

The rule lives in three functions — `increment()`, `expected_invoiced()` and `classify()` — and
each is used in three places: the corpus generator that wrote gold, the prompt that asks the model,
and the scorer that grades it. So the kit cannot drift about what a variance cause means.

## Four decoys, and three of them are numbers

This is what makes the corpus harder than a tone-versus-values one: **the loud number on the page is
the wrong number**, and reaching for it produces a confident, well-formed, wrong answer.

| | |
|---|---|
| **A. prior-period usage that is correctly excluded** | records that arrived after the collection cutoff belong to *last* month's invoice. **37 of 55 records state a non-zero late-arrival figure and only 8 are the `late_records` case**; 7 of them are exactly correct invoices. Reading "late CDRs present" as "variance" fails all 7 |
| **B. duplicate suspects that are not duplicates** | every record states both the raw figure de-duplication **flagged** and the figure review **confirmed**. **44 of 55 flag more than review confirmed, and on 22 of those review confirmed none of it** — two genuinely distinct sessions that looked alike. Subtracting suspects invents a gap |
| **C. unrated usage that was already re-rated and billed** | unrated stays *inside* billable, because usage that failed rating is still this period's usage and is still owed. **8 records carry a non-zero suspense bucket on a perfectly correct invoice** |
| **D. an analyst note naming the wrong cause** | exactly **22 of 55 (40%)** — a note naming duplicates on a rounding line, late records on a duplicate line, and so on |

Gold's `variance_cause` is **never** derived from the note. It is the arithmetic, run over the same
quantities the record itself states. The class composition is an exact **count** and then shuffled,
not drawn per record: 16 `none`, 8 `rounding`, 11 `unrated_usage`, 8 `duplicate_records`, 8
`late_records`, 4 `unexplained`, across 21 voice, 21 data and 13 SMS lines. See `data/SOURCES.md`.

## The guardrail is a business condition, and it needs labels — which is the honest half

`src/extract.py::compute()` raises a customer credit when the variance **over**-billed —
`duplicate_records` or `late_records` — **and** the invoice has already been issued. Either
variance on a draft can simply be corrected before it goes out; the same variance on an issued
invoice means the customer has paid for usage they do not owe.

> **Is this the line a customer is owed money on today?**

⚠︎ **It deliberately ignores half the problem, and that is a choice worth arguing with.**
`unrated_usage` is *under*-billing — real revenue leakage, and a real revenue-assurance team cares
about it — but nobody is owed money and no customer is waiting, so it does not fire this flag. **11
of the 55 records are `unrated_usage` and `compute()` routes none of them, on either tier, whatever
the invoice status.** That is defensible as a *credit* rule and indefensible as the only rule.
Splitting the two is the whole reason `compute()` is a separate function from `classify()`:
changing **who gets a credit** must not change **what the variance is**.

⚠︎ **This is the kit's own simplification, not a real carrier's billing-adjustment policy.** No
published tariff, settlement rule, regulatory requirement or operator's own credit procedure was
consulted, and none is reproduced. A real desk weighs the dollar size of the credit, the dispute
window, and whether the line sits inside a contracted tolerance. One enum test and one boolean is
the smallest rule that is genuinely useful and readable off a single reply, and it should be the
first thing a forker replaces.

Because it is a business condition, **it can only be scored where somebody wrote down the right
answer**. The kit is explicit about that, and it reports a no-gold **consistency diagnostic** beside
it — does the reply's stated cause survive the arithmetic re-run over the reply's *own* quantities?
— precisely so a forker with unlabelled records still has one figure to watch. That diagnostic is
**not** called the guardrail, and it is blind to the same case the guardrail is: a reply that
misreads a quantity and then classifies its own misreading correctly.

## What it measures, and the number that matters most

Two models, same 55-record corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-usage-variance.json`, `eval-r002-usage-variance.json`).

**Variance-cause accuracy against gold is the headline**, because the cause is the whole question.
It is reported in two shapes that are never averaged: a **six-way exact** grade (did it name the
right cause) and an **actionable / not-actionable** confusion matrix collapsed onto the same rows,
where anything other than `none` and `rounding` is the positive class — because a real variance
called clean is the error a revenue-assurance desk pays for.

**The fast tier scored 55 of 55 causes exactly, across all six classes**, with 1.00 recall and 1.00
precision on the 31 actionable lines — including all 7 correctly-invoiced records that state
prior-period usage, and every record whose suspect figure disagrees with its confirmed one. Field
extraction was exact: **605 of 605 cells**, with all 440 returned values on the eight spannable
fields located back to their own section. The credit flag fired on **8 of 8 lines with no false
alarms**, and no reply ever disagreed with its own quantities.

**The deliberating tier matched it on every record it reached — and it reached 54, not 55.** Its
run lost `TLV-0014` to a TLS handshake that never completed, so it scores 594 of 594 cells and 54
of 55 causes, the missing row counted **unanswered** rather than as a miss. See the next section:
that is a transport fact, not a model fact, and it is the only thing that separated the two tiers.

**Two tiers clearing a corpus is a real result and a small one.** It convicts the shortcut and it
cannot rank the models — the fast and deliberating tiers are separated here by about **8% more
output tokens and 48% more p50 latency** (4,824 ms against 7,125 ms) and by nothing the models
actually did. See `Business.not_good_enough` on the published kit page.

## A defect found in the run itself, and left on the record

`r002` lost `TLV-0014` to:

```
<urlopen error _ssl.c:1011: The handshake operation timed out>
```

No HTTP response was ever received, so there was no status code, no `HTTPError`, and nothing for
the adapter's retry policy — which keyed entirely on `exc.status in {408, 429, 500, 502, 503, 504}`
— to match. The exception propagated straight out and the harness recorded a failed document, on a
run where the model got every single cell it saw exactly right.

`src/adapters/__init__.py` now treats `URLError`, `TimeoutError` and `ConnectionError` as transient
and retries them with the same bounded backoff. Two things about that fix are stated rather than
glossed:

- **it was written after the run, not before it**, so the published `r002` still carries the loss
  and its coverage is 54 of 55. Quietly re-firing one document into a finished result file would
  have made the run look like something it was not;
- **it is reasoned, not measured.** No live handshake timeout has been reproduced against it.

One transport failure in 110 calls is one line at this size. At a carrier's volume it is thousands,
which is why it is on the page rather than in a commit message.

## `MAX_TOKENS` is a measurement, and the measurement found something

`evals/measure_max_tokens.py` fires **one** call at a deliberately oversized ceiling of 8000 so the
reply cannot be clipped, and records what it actually used
(`results/calib-c001-usage-variance.json`):

| | |
|---|---|
| output tokens billed | **552**, `finish_reason` `stop` |
| of which **reasoning** tokens | **444 — 80%**, and they never reach the text |
| visible reply | 381 characters of JSON, about 108 tokens |

So `MAX_TOKENS = 3000`: 5.4× the measured total, sized to cover the **reasoning pass**, not the
answer. Sizing it off the JSON alone is the obvious reading and it would have clipped every reply at
the moment the model stopped thinking and started answering. The worked example repeated the finding
independently — 390 reasoning tokens of 502.

**Nothing in this kit requested that reasoning pass.** `src/adapters/__init__.py` sends a `thinking`
parameter only when a caller passes one and the harness never does, so it is the provider's own
default and every recorded run paid for it. Output is priced up to six times input on the published
rate cards, which makes it the largest single line on this kit's bill. Both figures come from two
single calls, not from all 109 — `evals/run.py` records token totals, not the per-call completion
breakdown — and the kit page says so.

## The baseline is shipped, including where it wins and exactly where it does not

`--baseline` is a non-LLM extractor: a five-entry keyword table over the analyst's note, no key, no
cost. It is very good at the parts that are regex work — **all ten structured fields, 550 of 550
cells, perfect, including every stated zero** — and it is a deliberate *note floor* on the
eleventh: it reads the analyst's prose and never does the arithmetic, which is precisely the
shortcut the prompt forbids.

It scores **60.0% cause accuracy — 22 of 55 records wrong**, and those 22 are exactly the 22 the
corpus plants a contradicting note on. Both model tiers got every one they saw right. The *shape* of
the wrongness is the useful part:

| cause | floor got right |
|---|---|
| `duplicate_records` | **2 of 8** — the register most often used against type |
| `none` | 8 of 16 |
| `unrated_usage` | 7 of 11 |
| `unexplained` | 3 of 4 |
| `rounding` | 6 of 8 |
| `late_records` | 7 of 8 |

On the actionable collapse it is 78.2% accurate, with 9 false alarms and 3 real variances called
clean. Overall extraction lands at 96.4% (583 of 605) — the ten regexed fields carry it.

Making the baseline perfect would take about ten lines of integer arithmetic: it already regexes
every quantity the rule needs. Not doing so is the design — the floor is the **shortcut**, and the
gap it opens is the gap between reading prose and doing arithmetic.

**And watch what happens to the guardrail downstream.** The floor extracts `invoice_status`
correctly every single time, by regex — and its credit flag still scores only **7 of 8 with 4 false
alarms** (0.875 recall, 0.6364 precision), because it inherits the note-derived cause. That is the
honest lesson of shipping a business-condition guardrail: *it is only ever as good as the field it
reads.*

**The consistency diagnostic caught all 22, with no gold at all.** Run the floor's own output
through `classify()` and its stated cause disagrees with the arithmetic over its own extracted
quantities on exactly the 22 records it got wrong — which is the strongest available evidence that
the no-gold diagnostic is worth computing on unlabelled records.

### The floor's keyword table was checked before anything was paid for

A sibling kit earlier in this series shipped a keyword that fired on a negation inside a calm note
and mis-registered four records for days. So `evals/check_labels.py` asserts, for free and before
any run may spend, that every note template classifies to the register it was authored in — **and,
because this floor is a six-way classifier rather than a binary one, that no template matches two
registers.** That second assertion covers a failure a binary floor cannot have: a template matching
two registers would make the floor's answer depend on the order of its own keyword table rather than
on the note, and nothing in a score would show it.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and
the variance cause is arithmetic, which is the one thing you should never ask a model to adjudicate.
Adding an LLM judge would add cost and a second source of disagreement to a comparison that does not
need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
eleven fields × the whole record is eleven times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the rule, not by the record** — on the worked
example the system prompt and field schema are **1,588 of 1,799 input tokens** and the record itself
is **211**. Most of that floor is the priority order, stated in full rather than left to be
inferred.

The saving is usually invisible, because the sections that get sent would have been sent anyway.
Here there is one you can point at: **`Rating Domain` is mapped by no field at all**, so the union
of the mapped sections leaves it out and it never reaches the provider — 11 of the record's 12
sections are sent.

And note what `SECTION_HINTS` maps `variance_cause` to: the service type and the five quantities —
**and `Duplicate Suspects`, deliberately.** That is not an oversight and it is not a saving. The
suspect figure is the louder of the two duplicate numbers and it is the one this corpus is built to
watch a reader reach for; filtering it out of the prompt would have solved the problem for the model
and measured a kit that had already cheated. It goes in, the rule says which of the two to use, and
44 of 55 records disagree between them. The analyst's note is mapped in too, as a field in its own
right. `SECTION_HINTS` is the map of where the answer actually lives, not a filter that hides the
decoys.

### Spans are searched inside the field's own sections first

`src/extract.py::_locate()` looks for a value in the sections `select.py` maps the field to, and
only falls back to the whole document when it finds it nowhere. On this corpus that scoping is
load-bearing rather than precautionary — five of the eleven fields are quantities in the same unit
sitting in adjacent sections, and the collisions are measured, not feared:

| | |
|---|---|
| records where **two quantity fields share a value** | **22 of 55** |
| records where **two or more quantities are `0`** | **21 of 55** |
| records where `mediated_quantity == invoiced_quantity` | **4 of 55** |
| records where the suspect figure equals the confirmed one | 11 of 55 |

An unscoped document-wide search for `0` would cite `Unrated Usage` for a value read from
`Confirmed Duplicates` on a third of the corpus. The value is right, the section label is wrong, and
nothing scores section labels — a citation that looks checkable and is wrong is worse than none at
all. Scoping costs nothing and closes the whole class.

## Point it at your own reconciliation records

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per line.
`SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need editing for a
different reconciliation-report layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct. `increment()`, `classify()` and `compute()` in
`src/extract.py` are this kit's own invented increment table, variance rule and credit rule, and
should be the first things you replace with your own rating configuration and credit policy.

⚠︎ **And one claim does not travel with you.** Every score here was measured on quantities that were
already aggregated correctly. Point this at your own mediation output and the aggregation becomes
part of the system under test — and nothing measured here transfers to it.

If your records are unlabelled — the normal case — the field grade, the six-way cause grade and the
credit flag's score all go away. What does not go away is the consistency diagnostic, and that is
the one figure you can compute on day one.

## What it does not do

It never raises a credit, reverses a charge, re-rates a suspense bucket or contacts a customer, and
it is not a substitute for a revenue-assurance process. **It reconciles quantity, not money** — a
wrong rate applied to correctly-counted usage, a mid-period tariff switch or a prorated plan change
all produce a charge that is wrong while every quantity on the record is right, and this kit answers
`none`. **Every quantity arrives pre-summed**: a real reconciliation starts from millions of
call-detail records and does the aggregation itself, which is the step most likely to be wrong in
production and the one this kit never touches. The guardrail reads two fields out of the reply — if
the model misreads the mediated total and then classifies that misreading consistently, the line is
routed, or not routed, on a wrong number, and nothing here re-reads the document to catch it. It
reads one line and one period at a time, and never compares a period against its predecessor,
reconciles roaming or interconnect traffic settled in another operator's units, or handles a bundled
allowance where "billable" is not "used". **No red-team run exists** — the corpus plants a
confusable plain register and three misleading numbers, not adversarial text, and whether an
instruction hidden in the analyst's note could move the verdict is unmeasured. No OCR, no auth, no
database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run is
what gets published.
