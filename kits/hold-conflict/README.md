# hold-conflict — check whether a record series past its retention is still frozen by a hold

**UC042.** Point it at a records-disposition review for one record series, get a field table back —
plus a routing decision taken afterwards in pure code, from two of the extracted values: may this
series be *proposed* for destruction, and if something still freezes it, is it already sitting in
the destruction queue?

⚠︎ **This kit proposes; a records officer releases.** "Eligible" means *may be put in front of a
person for approval*, never *destroy it*. Nothing here destroys, deletes, disposes of anything,
releases a hold, amends a retention schedule or notifies anybody — there is no destroy control in
the UI and no write path of any kind. The guardrail runs the *other* way: it asks for a series to be
pulled back **out** of a destruction queue.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                            # free — validates the gold set
python -m evals.run --run-id b000-holds --baseline holds  # free — the over-cautious floor
python -m evals.run --run-id b001-notes --baseline notes   # free — the officer-tone floor
python -m evals.run --run-id t000-stub --stub           # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>               # THIS SPENDS MONEY: one call per review
python -m evals.run --rescore results/eval-r001-<model>.json   # free — re-score, never re-buy
python -m src.app                                        # the local UI on 127.0.0.1:8842
```

**You do not need a key to see this work.** The 55 reviews and every recorded run ship in the repo,
so `python -m src.app` starts, the picker populates, any review renders in full, and Extract returns
a plain sentence saying nothing was called rather than an error. `check_labels` and both free floors
score a complete run with no key at all. A key is only needed to extract a *new* review or to
re-run the eval against your own numbers.

## Eligibility is a derivation. The records officer's note is not evidence about it.

A disposition review puts a retention schedule, two expiry dates, a hold registry and a records
officer's own remark on the same page. Only the first three decide anything, and they are taken in a
priority order — the first condition that fires decides it, as of a fixed review date of **2026-08**:

```
a hold binds it                       -> no
an overlapping series has NOT expired  -> no
its own retention has NOT expired      -> no
otherwise                              -> yes
```

The rule lives in one function, `eligibility()`, and is used in three places — the corpus generator
that wrote gold, the prompt that asks the model, and the scorer that grades it — so the kit cannot
drift about what "eligible" means. `evals/check_labels.py` asserts the review date is the same
constant in all three files before any run may spend.

## The hard part is the first condition, and it is prose

A hold's scope is written the way a hold notice is written — *"all correspondence relating to the
Riverside project, 2019 onward"* — and has to be judged against the series' own category, project
and closed date. **That is three separate tests and all three must pass.** Two of three passing is
the commonest wrong answer, and it is the one that looks most like a match.

Four readings are planted deliberately, each in quantity, because a corpus that plants one instance
of its own sharpest test has an anecdote rather than a measurement:

| | | |
|---|---|---|
| **partial coverage, by category** | 6 | right project, right dates, the hold is about a different records category. **Eligible** |
| **partial coverage, by project** | 5 | right category, right dates, the hold names a different project. **Eligible** |
| **a date range that excludes the record** | 6 | right category, right project, and the series closed outside the scope's span. **Eligible** |
| **a released hold with a live successor** | 6 | the covering hold reads `released`; a second, ACTIVE line's whole scope is *"continues the scope of `<id>`"*. Reading the released line and stopping answers "eligible", and would release a series under a live hold. **Frozen** |
| **the mirror of that** | 5 | a released hold that *would* have covered, with nothing following it — which is what stops "released means look for a successor" from being a working shortcut. **Eligible** |
| **frozen with a perfectly clean registry** | 12 | 6 held by a longer-retention overlapping series that has not expired, 6 whose own retention simply has not elapsed. **Frozen** |

`evals/check_labels.py` refuses to let a run spend if any of those falls below five, if any class
produces the verdict it is not named for, if a successor case is findable without following the
reference, or if a mirror case carries a successor after all.

**Every record, series, custodian office, project, schedule code, hold id and officer note in this
corpus is invented, and no person is named anywhere.** No real agency, published general records
schedule, disposition authority or litigation matter is named or reproduced. What is modelled on
public practice is the *structure* — jurisdictions publish general schedules as (item code, series
description, retention period) — with entirely fabricated contents. See `data/SOURCES.md`.

## The guardrail is a business condition, and it needs labels — which is the honest half

`src/extract.py::compute()` routes a series when it is **not** eligible **and** it is already in the
destruction queue:

> **Is this the series somebody has to pull out of the queue today?**

A frozen series nobody has queued can be left where it is until the next cycle; the same series
already in the queue is one approval away from being destroyed under a live hold. **Note the
direction — this flag never proposes a destruction. It asks for one to be stopped**, which is the
only direction a decision like this should be automated in at all.

⚠︎ **This is the kit's own simplification, not a real records programme's escalation policy.** No
published general records schedule, disposition authority or hold procedure was consulted, and none
is reproduced. A real records office weighs how close the destruction batch is, who issued the hold,
whether counsel has been notified, and whether the series has already been certified for
destruction. Two values is the smallest rule that is genuinely useful and readable off a single
reply, and it should be the first thing a forker replaces.

Because it is a business condition, **it can only be scored where somebody wrote down the right
answer.** The kit reports a no-gold *consistency diagnostic* beside it — does the reply's stated
verdict survive the derivation re-run over the reply's own named hold and own dates? — precisely so
a forker with unlabelled reviews still has one figure to watch. That diagnostic is **not** called
the guardrail, and it is blind to exactly the step this corpus exists to test: it collapses the hold
search to its *result*, so a reply that names the wrong hold and then derives from it perfectly is
completely self-consistent and completely wrong. Only gold grades that.

## What it measures, and the number that matters most

Two models, same 55-review corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-hold-conflict.json`, `eval-r002-hold-conflict.json`).

**Eligibility accuracy against gold is the headline**, and *frozen* is the positive class: a series
under a live hold that gets called eligible is the one that reaches a destruction batch, and it is
the error that is not recoverable.

| | fast tier (r001) | deliberating tier (r002) |
|---|---|---|
| reviews answered | **55 of 55** | **54 of 55** |
| field extraction | 660 of 660 cells | 648 of 648 cells |
| binding hold named | 55 of 55 | 54 of 55, 1 unanswered |
| eligibility verdict | 55 of 55 — 1.00 recall, 1.00 precision on the 28 frozen | 54 of 54 answered |
| review flag | 16 of 16 fired, 0 false alarms | 16 of 16, 0 false alarms |
| spans located | 421 of 421 returned values | 414 of 414 |

Neither tier got a single answer wrong — including all 6 released-with-a-live-successor reviews, all
17 carrying a hold that covers nothing, and all 12 frozen with a clean registry.

**Two tiers clearing a corpus perfectly is a real result and a small one.** It convicts both
shortcuts below and it cannot rank the models: the deliberating tier is separated here by 11.7% more
output tokens, 90% more median latency (7,369 ms against 3,873 ms) and nothing else.

### The one real failure in 110 paid calls, and it was not a model failure

Review `RDS-0018` died on the deliberating tier with `<urlopen error [Errno 60] Operation timed
out>` — a client-side socket timeout at the adapter's 120-second default. The adapter retries only
the HTTP statuses in its `TRANSIENT` set; a socket timeout raises urllib's `URLError`, which carries
no status, so it falls straight through the retry loop and never will be retried. One review of 55
was lost and r002 is published as **54 of 55** rather than patched. It is a one-line fix and it is
deliberately *not* applied here, because the published numbers have to come from the code that
produced them.

At 55 reviews that is a footnote you can see. At ten thousand it is roughly 180 silently missing
series in a queue whose entire purpose is that nothing goes missing — which is why the first thing
in the kit page's `guardrails.add_first` is a completeness reconciliation, not a smarter prompt.

### A perfect score hid a grader defect until somebody disbelieved it

`evals/judge.py`'s binding-hold grader compared the model's named hold against gold's. Gold names
**no** hold on `RDS-0018` — and the missing reply's value was also null — so `None == None`
succeeded and the grader published **55 of 55 over 54 answers**. The confusion matrices beside it
had carried a warning against exactly this in their own docstring since the kit was written; that
grader is not a matrix, so it did not inherit it. No gate caught it. Putting "55 of 55" next to
"records: 54" and refusing to believe it did.

An unanswered review is now its own verdict and is never a correct call. Both paid runs were
re-scored **for free** from their own recorded cells — `python -m evals.run --rescore <file>` —
rather than re-purchased: every result file already carries one row per (review, field) with the
model's own returned value, so the reply set is recoverable exactly. The binding-hold figure moved
from 1.0 to 0.9818 on r002, which is the honest number.

## Two free floors are shipped, and they fail in opposite directions

Sibling kits in this series ship one baseline. This corpus offers two shortcuts a real records desk
actually takes, and the pair is the finding. Both are pure regex, no key, no cost, and both are
perfect on the ten fields that are regex work — **550 of 550 cells each**. Every miss either makes
is on the two fields it *decides* rather than reads.

| floor | what it does | eligibility accuracy | how it fails |
|---|---|---|---|
| `b000-holds` | **the over-cautious clerk** — any hold on file means "not eligible" | **41.82%** | freezes 22 series nothing holds, **and still releases 10 genuinely frozen ones** |
| `b001-notes` | **the tone reader** — decides from how the officer's note reads | **60.00%** | releases 13 frozen series, freezes 9 eligible ones |

The over-cautious floor is not a strawman: freezing everything with a hold anywhere near it is the
real failure mode of a records programme, where nothing is ever destroyed and the retention schedule
stops meaning anything. And it looks *safe* while being unsafe — it is blind to both ways a series is
frozen with no hold on it, so 10 of the 28 frozen series come out the other side marked releasable.
The tone floor fails on exactly the 22 reviews the corpus plants a contradicting note on. **Both
model tiers got every one of those right.**

**And watch what happens to the guardrail downstream.** Both floors extract `queue_status` correctly
every single time, by regex — and the over-cautious floor's review flag still scores 9 of 16 with 11
false alarms (0.5625 recall, 0.45 precision), and the tone floor's 8 of 16 with 4 false alarms (0.50
recall, 0.6667 precision). That is the honest lesson of shipping a business-condition guardrail: *it
is only ever as good as the field it reads.*

⚠︎ It would be trivial to make the over-cautious floor perfect on this corpus, and that is the point
of not doing it. The registry lines here are machine-written in a fixed four-column format, so a
regex could parse the scope prose back into its pieces and re-run the coverage test exactly. It
would score 100% here and tell you nothing, because a real hold registry is prose in a
case-management system with no fixed line format at all.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and the
eligibility verdict is a derivation, which is the one thing you should never ask a model to
adjudicate. Adding an LLM judge would add cost and a second source of disagreement to a rule that
does not need one. What *does* need validating is the **labels**, and `evals/check_labels.py` does
that before any run may spend. It does not validate the graders, and this kit paid for the
difference — see above.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
twelve fields × the whole review is twelve times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the context, not by the question** — on the
worked example the system prompt and field schema are 1,438 of 1,705 input tokens and the review
itself is 267.

The saving is usually invisible, because the sections that get sent would have been sent anyway.
Here there is one you can point at: **`Custodian Office` is mapped by no field at all**, so the union
of the mapped sections leaves it out and it never reaches the provider. And note what
`SECTION_HINTS` maps `disposition_eligible` and `binding_hold_id` to — the category, the project,
the closed date, the two expiry dates and the registry, and **not** the officer's note. That is not
a saving either; the note reaches the model anyway, as a field in its own right. It is the map of
where the answer actually lives.

### `MAX_TOKENS` is a measurement, not a guess

Before either scored run, five reviews were run at a deliberately over-generous ceiling of 8,000
(`results/eval-c000-ceiling.json`). Every reply parsed, and the spread was enormous: **294 to 1,849
output tokens**, and 2,623 to 17,830 ms, against a visible JSON body of about 290 tokens on every one
of them. The captured example (`results/example-RDS-0004.json`) explains it: 576 output tokens
billed, of which **425 are `reasoning_tokens`** that never reach the text. Roughly three quarters of
the output price is thinking nobody reads, and output is 6× the input rate on the card this series
projects onto. `MAX_TOKENS = 6000` is 3.2× that measured maximum, and both scored runs record their
own observed maximum so the number can be re-checked rather than trusted.

### Spans are searched inside the field's own sections first

`src/extract.py::_locate()` looks for a value in the sections `select.py` maps the field to, and only
falls back to the whole document when it finds it nowhere. This corpus needs it: two dates in the
same review are both `YYYY-MM` and can be equal, and a project name appears in the title, in its own
section and again inside a hold's scope prose. An unscoped search would cite the first of those for a
value correctly read from the last. The value is right, the section label is wrong, and nothing
scores section labels — a citation that looks checkable and is wrong is worse than none at all.

## Point it at your own disposition reviews

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold row per review.
`SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need editing for a
different review layout; when it does not match, selection falls back to the whole document —
slower, more expensive, always correct. Then rewrite `eligibility()` and `AS_OF` in
`src/extract.py`: those two *are* the kit, and everything else is plumbing around them. Run
`python -m evals.check_labels` before you spend anything — it refuses a run whose gold disagrees
with its own values.

**Every number on this page stops being true the moment you do.** The rule here is three conditions
this kit invented; yours will have a schedule authority, event-triggered retentions and a hold
procedure negotiated with counsel behind it.

If your reviews are unlabelled — the normal case — the field grade, both confusion matrices and the
review flag's score all go away. What does not go away is the consistency diagnostic, and that is the
one figure you can compute on day one, with its blind spot stated above.

## What it does not do

It never destroys a record, releases a hold, amends a retention schedule, certifies a disposition or
notifies anybody, and it is not a substitute for a records officer signing against an approved
disposition authority.

**The scope prose here is a template.** Every hold scope is one sentence generated from a category
list, a project and a date span. A real hold notice is drafted by counsel, runs to paragraphs, and
describes its reach in language that was negotiated rather than generated. The *shape* of the
judgement this kit measures is right; its full difficulty is not, and no number above should be read
as though it were.

`binding_hold_id` is a **single id** and the rule takes the first active covering line in registry
order — two live holds on one series is ordinary in a real programme and cannot be expressed here,
which means the second hold is invisible the moment the first is released. A scope that references a
hold *not* in the registry resolves to nothing and binds nothing; the reference is followed exactly
one level, because a chain nobody wrote is not a rule. Every date is `YYYY-MM` and every retention is
whole years from the cutoff, so a fiscal-year cutoff, an event-triggered retention ("5 years after
final payment") or a permanent item has no expiry month this rule can read. It reads one review at a
time and never reconciles a series against its own re-appraisal or against a schedule that changed
between cutoff and review.

**No red-team run exists for this kit.** The records officer's note is the one field an outside party
authors, on a page that decides whether a record can be destroyed, which makes it the obvious place
to attack — and whether an instruction hidden in it could move the verdict is **unmeasured**. The
corpus plants confusable *register*, not adversarial text, and those are different tests. It is named
as unmeasured rather than quietly counted as a boundary that holds.

No OCR — a scanned disposition sheet or an image-only hold notice extracts no text. No auth, no
database, no multi-tenancy, no deployment story. It runs once per model, locally, and that run is
what gets published.
