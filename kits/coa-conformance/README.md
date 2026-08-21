# coa-conformance — check a certificate of analysis against its own specification limits

**UC037.** Point it at a certificate of analysis for one manufactured batch, get a field table
back — plus a check run afterwards in pure code, on the model's own answer: re-run the comparison
over the numbers the model itself extracted, and see whether it lands on the verdict the model
itself gave. Nothing here releases or rejects a batch; the flag is a routing signal.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the analyst-tone floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per certificate
python -m src.app                                      # the local UI on 127.0.0.1:8773
```

## The guardrail: the model's own numbers have to support the model's own verdict

Every sibling kit in this series flags a **business condition** — a break aged past a threshold, an
income figure under a floor. To know whether such a flag was right, you need a labelled answer. This
kit's guardrail is a different shape, and the difference is the reason it is worth showing:

> **Does the model's stated conclusion match what its own extracted numbers actually say?**

`src/extract.py::compute()` takes the `measured_value`, `spec_lower_limit` and `spec_upper_limit`
that came back in the *same reply*, re-runs the published comparison over them, and raises
`needs_review` when the result differs from the `conforms_to_spec` in that same reply.

| | rule | what it needs |
|---|---|---|
| `needs_review` | the recomputation over the model's own numbers disagrees with the model's own `conforms_to_spec` | nothing but the reply — **no gold, no second call, no labelled set** |

That property is the point. A business-condition flag can only be scored where somebody has already
written down the right answer; this one computes identically on a certificate nobody has ever
scored, which is every certificate a forker actually has. It detects exactly the failure this kit is
built around — a model talked out of the arithmetic by the analyst's prose, returning a verdict its
own numbers contradict. It is **not** a check on whether the extracted numbers are right: if the
model misreads the measured value *and* judges consistently against its own misreading, the reply is
self-consistent and this flag stays quiet. Two different jobs; see *What it does not do*.

The comparison itself is stated once, in `recompute_conformance()`, and used in three places —
the corpus generator that wrote gold, the prompt that asks the model, and the guardrail that
re-checks it — so the kit cannot drift about what "conforms" means:

```
conforming  <=>  (lower is None or measured >= lower) and (upper is None or measured <= upper)
```

Both limits inclusive; a limit the certificate does not state constrains nothing on that side,
because a one-sided specification ("not more than 1000 CFU/g") is ordinary practice and **31 of
this corpus's 55 records carry one**. A model that invents the missing bound gets the field wrong.

## What it measures, and the number that matters most

Two models, same 55-record corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-coa-conformance.json`, `eval-r002-coa-conformance.json`).

**Conformance accuracy against gold is the headline**, because conformance is the whole question:
gold's own verdict is the arithmetic run over the numbers the certificate states, and out of
specification is the positive class — a failing batch called conforming is the error a quality team
loses sleep over. **Both tiers scored 55 of 55, with 1.00 recall and 1.00 precision on the 26
out-of-specification records.** On field extraction the deliberating tier was perfect (550 of 550
cells); the fast tier missed one — a product name read as "Halcotte" for "Halvette" on COA-0038, a
field the comparison never touches. Neither tier's `needs_review` ever fired: every one of the 110
replies agreed with its own numbers.

Both tiers clearing a corpus is a real result and also a small one. See `Business.not_good_enough`
on the published kit page for what 55 records cannot tell you.

## The baseline is shipped, including where it wins and exactly where it does not

`--baseline` is a non-LLM extractor: seven fixed worried-sounding words in the disposition note, no
key, no cost. It is very good at the parts that are regex work — **all nine structured fields, 495
of 495 cells, perfect** — and it is a deliberate *tone floor* on the tenth: it reads the analyst's
prose and never does the comparison, which is precisely the shortcut the prompt forbids.

It scores **56.4% conformance accuracy — 24 of 55 records wrong**, with 10 out-of-specification
batches called conforming and 14 conforming batches called failures. Every one of those 24 is a
register mismatch this corpus planted on purpose. Both model tiers got all 24 right.

Making the baseline perfect would take four lines: it already regexes all three numbers out of the
document. Not doing so is the design — the floor is the *shortcut*, and the gap it opens is the gap
between reading prose and doing arithmetic.

**And the guardrail caught all 24 of them, with no gold at all.** Run the tone floor's own output
through `compute()` and `needs_review` fires on exactly the 24 records it got wrong, 0 false alarms
— which is the strongest available evidence that a self-consistency check is worth computing on
unlabelled documents.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and
the conformance verdict is arithmetic, which is the one thing you should never ask a model to
adjudicate. Adding an LLM judge would add cost and a second source of disagreement to a comparison
that does not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here: sending
ten fields × the whole certificate is ten times the input tokens of sending each field the section
that could possibly state it. **The bill is driven by the context, not by the question** — on the
worked example, the system prompt and field schema are 789 of 965 input tokens and the certificate
itself is 176.

Note what `SECTION_HINTS` maps `conforms_to_spec` to: the measured result and the two limits, and
**not** the disposition note. That is not a saving — the note reaches the model anyway, as a field
in its own right. It is the map of where the answer actually lives.

## Point it at your own certificates

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
certificate. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different certificate layout; when it does not match, selection falls back to the
whole document — slower, more expensive, always correct. The specification limits in
`tools/build_corpus.py` are invented for this corpus and resemble no real standard; replace them
with your own approved specification before trusting anything this computes.

If your certificates are unlabelled — the normal case — the field grade and the confusion matrix
both go away, and `needs_review` does not. That is the one figure in this kit you can still compute
on day one.

## What it does not do

It never releases, rejects or dispositions a batch, and it is not a substitute for a qualified
person signing against an approved specification. The guardrail checks the model against **itself**,
not against the certificate: a reply that misreads the measured value and then judges that misreading
correctly is self-consistent, and this flag stays quiet — nothing here re-reads the document to
confirm the numbers. It reads one certificate at a time and never compares a batch against its own
re-test, its neighbours on the same production run, or a specification that changed between test and
review. It does no unit conversion: a result reported in one unit against a limit stated in another
is out of scope, and unmeasured. No OCR — scanned or image-only certificates extract no text. No
auth, no database, no multi-tenancy, no deployment story. It runs once per model, locally, and that
run is what gets published.
