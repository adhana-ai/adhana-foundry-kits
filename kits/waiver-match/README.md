# waiver-match — assemble the lien-waiver coverage picture behind a progress payment

**UC045.** Point it at a construction progress-payment package, get a field table back — plus a
routing decision taken afterwards in pure code: how many parties on this package are **not**
covered by a lien waiver, which is the first, and why — and if any are, is this application
scheduled to go out this cycle?

**It assembles evidence and names the gaps. A person releases the payment.** Nothing here
determines anybody's lien rights, nothing here releases or withholds money, and the coverage rule
it applies is this kit's own invention — **no jurisdiction's statute or statutory waiver form is
reproduced**. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set and the rule
python -m evals.run --run-id b000-rules --baseline    # free — the coordinator-note floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per package
python -m src.app                                     # the local UI on 127.0.0.1:8807
```

## The question, and why it is not just arithmetic

Before a general contractor releases a progress payment, somebody has to decide whether the lien
waivers on file actually cover the amounts about to be paid — for the subcontractor and for every
lower tier beneath them. That is matching, plus arithmetic, plus **type reasoning**: is this the
right *kind* of waiver, does its amount reach, does its through-date reach, and does it reach a
claim that was asserted after it was signed?

The kit applies one rule to each party in document order and stops at the first condition that is
true:

```
1. no_waiver_on_file   no waiver on file for this party
2. notice_after_waiver the party's preliminary notice is dated AFTER the waiver was signed --
                       the waiver predates the claim it would have to reach
3. period_short        a PROGRESS waiver whose through-date is earlier than the package's
                       Period Through date.  A FINAL waiver has no through-date and can
                       never be period_short
4. amount_short        the waiver amount is less than that party's amount due
5. conditional_stale   the waiver is CONDITIONAL and something has already cleared against
                       it: Prior Payment Cleared is yes, OR that party is on a joint check,
                       which clears on issue
otherwise              covered
```

**The order is the hard part, and each of the four traps below is measured on this corpus:**

| trap | why it is hard |
|---|---|
| a notice dated after the waiver | the waiver can be unconditional, for the full amount, covering the whole period — and still not reach the claim. Every check a fast reader runs says covered |
| a final waiver's missing through-date | it reaches all work through completion, so the line reads `n/a`. A reader mechanically comparing dates finds no date and calls it a gap |
| period outranks amount | a waiver for twice the amount due whose through-date stops inside the period is `period_short`, not `amount_short` and not covered |
| a joint check clears on issue | both payees negotiate it, so a conditional waiver on a joint-check party is stale **even when the package says the prior payment has not cleared**. It is the one case where the package-level answer is not the answer |

The rule is stated once, in `coverage_status()`, and read in three places — the corpus generator
that wrote gold, the prompt that asks the model, and `evals/check_labels.py`, which asserts all
four traps directly before any run may spend.

## The guardrail is a business condition, not a check on the model

`src/extract.py::compute()` fires `needs_hold` when `parties_uncovered > 0` **and**
`release_status == "scheduled"`. A package with a gap that is already on hold is not news —
somebody has stopped it. The same gap on one scheduled to go out is the package that has to be
pulled back today, before the money moves.

It is two values and an AND, run in pure code over whatever the model returned, never over gold.
A reply missing either value returns `None` rather than `False`: an unknown is not a pass.

⚠︎ **It routes, it does not authorise.** A package with no gap is not thereby cleared for release
— it is a package this kit found nothing to say about. And the rule itself is invented: no
jurisdiction's statute, no filed subcontract and no real payment procedure was consulted.

Beside it, and deliberately **not** called the guardrail, is a **no-gold self-check**
(`src/extract.py::self_check`): is a party named exactly when the count is non-zero, is the reason
`none` exactly when the count is zero, and does the package actually list the party named. That
one needs no labels, so a forker can compute it on packages nobody has scored — but it is blind
to a reply that applies the coverage rule wrongly and then reports that wrong answer consistently,
which is why the confusion matrices are the graded figures.

## What it measures

Four graders, scored separately and never folded together — see the committed run records in
`results/`:

1. **Per-field exact match** over 11 fields × 55 packages. The reference standard for field values.
2. **Coverage-gap confusion matrix.** Is there *any* uncovered party on this package? A gap is the
   positive class: a package with an uncovered party that gets called complete is the failure a
   payment desk actually pays for.
3. **Gap attribution**, scored *only* on the packages that really have a gap: did the run name the
   right party **and** the right reason? A package-level yes/no hides the difference between
   "found the gap" and "found a gap", and on a package with four parties and five possible
   reasons that difference is the entire value of the thing.
4. **Hold-flag confusion matrix.** Does the pure-code routing decision land where the same rule
   run over gold's own values lands?

## The baseline is shipped, including exactly where it fails

`--baseline` is a non-LLM extractor: nine fixed worried-sounding phrases in the coordinator's
note, no key, no cost. It is perfect on the eight structured fields it regexes and it is a
deliberate **tone floor** on the three that matter — it reads the coordinator's prose and never
opens a party block, which is precisely the shortcut the prompt forbids.

It scores **60.0% on the coverage-gap verdict — 22 of 55 packages wrong**, and those 22 are
exactly the 22 this corpus plants a contradicting note on. On attribution it manages **1 of 31**.

Making it perfect would take a few dozen lines: the party blocks are as regexable as everything
else in this layout. Not doing so is the design — the floor is the *shortcut*, and the gap it
opens is the gap between reading prose and running the rule.

Its keyword list was checked against both note registers **before** the floor was first run. Two
obvious candidates, "complete" and "looked", appear in *both* registers here ("it looked complete"
is settled; "Not confident the waiver coverage is complete" is not), so both were rejected. A
sibling kit in this series shipped a keyword that fired on a negation inside a settled note and
mis-registered four records for days; `evals/check_labels.py` asserts the property here from the
start.

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and the
coverage verdict is a comparison over dates and amounts, which is the one thing you should never
ask a model to adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
eleven fields × the whole package is eleven times the input tokens of sending each field the
section that could possibly state it. **Two sections are mapped by nothing and are therefore never
sent** — the prime contractor and the subcontract reference. They are the part of the saving a
reader can point at.

Note what `SECTION_HINTS` maps the three coverage fields to: the party blocks, the period-through
date and the prior-payment answer — and **not** the coordinator's note. That is not a filter; the
note reaches the model anyway, as a field in its own right. It is the map of where the answer
actually lives.

## Point it at your own packages

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
package. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different pay-application layout; when it does not match, selection falls back to
the whole document — slower, more expensive, always correct.

`coverage_status()` and `compute()` in `src/extract.py` are this kit's own invented coverage rule
and routing policy. **Replace both** with your own counsel's requirements before trusting anything
this computes. Changing *who gets routed* is a policy change; changing *what covered means* is a
definition change; they are two separate functions on purpose so they cannot be the same edit.

If your packages are unlabelled — the normal case — the field grade, both confusion matrices and
the attribution grade all go away, and the no-gold self-check does not. That is the one figure in
this kit you can still compute on day one, and it is a weak one; the honest answer is that this
kit's real graders need labels.

## What it does not do

It never releases a payment, withholds one, issues or requests a waiver, files or responds to a
preliminary notice, or contacts any party. It is **not legal advice** and it does not determine
anybody's lien rights — those depend on a jurisdiction's statute, the subcontract, and facts this
kit never sees. It reads one pay application in isolation and never compares it against the prior
application on the same job, the subcontract's own retainage terms, a payment bond, or a waiver
filed after the package was assembled. It does no OCR — scanned waivers and photographed paper
extract no text. It does no name matching: a party that appears under two spellings across two
documents is two parties to this kit. No auth, no database, no multi-tenancy, no deployment story.
It runs once per model, locally, and that run is what gets published.
