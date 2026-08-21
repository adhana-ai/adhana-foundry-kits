# pod-conformance — check a proof-of-delivery record against what was actually booked

**UC038.** Point it at a proof-of-delivery record for one shipment, get a field table back — plus a
routing decision taken afterwards in pure code, from two of the extracted values: did this delivery
arrive as booked, and if it did not, did anybody sign for it? Nothing here files a claim, issues a
credit or contacts a carrier; the flag is a routing signal.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the driver-tone floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per record
python -m src.app                                      # the local UI on 127.0.0.1:8774
```

## Completeness is a comparison. The driver's note is not evidence about it.

A proof-of-delivery record puts two counts, a condition code and a driver's own account of the stop
on the same page. Only the first three decide anything:

```
complete  <=>  delivered_quantity == ordered_quantity  AND  condition_code == "undamaged"
```

Three things about that rule are stated to the model in full, because each is a reading a model
falls into on its own:

| | |
|---|---|
| **equality is exact in both directions** | "at least the ordered quantity arrived" is the natural reading and the wrong one. A surplus is still not the order that was booked — **3 of these 55 records deliver more units than were ordered**, so the reading is measured rather than assumed away |
| **the condition code is part of the test** | counts that match with a `damaged` code is not a complete delivery |
| **`unknown` is not a pass** | a condition nobody assessed at the drop is not an undamaged one. Only the literal code `undamaged` passes |

The rule lives in one function, `is_complete()`, and is used in three places — the corpus generator
that wrote gold, the prompt that asks the model, and the scorer that grades it — so the kit cannot
drift about what "complete" means.

## The guardrail is a business condition, and it needs labels — which is the honest half

The sibling kit immediately before this one in the series ships a **self-consistency** check: does
the reply contradict itself? That shape needs no labels at all, and it answers a question about the
*model*. This kit's guardrail is the other shape, and it answers the question an operations desk
actually has:

> **Is this the record somebody has to pick up today?**

`src/extract.py::compute()` routes a record when the delivery did not arrive as booked **and** no
recipient signature is on file. A shortfall or a damaged pallet that *is* signed for is already
documented and acknowledged — somebody at the receiving end saw the delivery and put their name to
it, and the claim or credit follows an ordinary paper trail. The same problem with no signature is
the one that turns into a dispute: nothing on file shows the recipient was ever told, and the only
surviving account of the stop is the driver's own.

⚠︎ **This is the kit's own simplification, not a real carrier's claims-intake policy.** No published
SLA, tariff or carrier liability rule was consulted, and none is reproduced. A real desk weighs
shipment value, commodity, the consignee's own receiving standard and the terms on the bill of
lading. Two booleans is the smallest rule that is genuinely useful and readable off a single reply,
and it should be the first thing a forker replaces.

Because it is a business condition, **it can only be scored where somebody wrote down the right
answer** — unlike a self-consistency check, which computes on anything. The kit is explicit about
that, and it reports a no-gold *consistency diagnostic* beside it (does the reply's own verdict
survive the comparison re-run over the reply's own numbers?) precisely so a forker with unlabelled
records still has one figure to watch. That diagnostic is **not** called the guardrail, and it is
blind to the same case the guardrail is: a reply that misreads a count and then judges its own
misreading correctly.

## What it measures, and the number that matters most

Two models, same 55-record corpus, same judge, same guardrail — see the committed run records in
`results/` (`eval-r001-pod-conformance.json`, `eval-r002-pod-conformance.json`).

**Completeness accuracy against gold is the headline**, because completeness is the whole question,
and *incomplete* is the positive class: a delivery that did not arrive as booked and gets called
complete is the error that costs money. **Both tiers scored 55 of 55, with 1.00 recall and 1.00
precision on the 27 incomplete deliveries** — including all 3 over-deliveries and all 4 records
whose only fault is an unassessed condition code. On field extraction both tiers were exact: 550 of
550 cells each, 1,100 of 1,100 across the two runs. The review flag fired on 10 of 10 records with
no false alarms on both tiers, and no reply on either tier ever disagreed with its own numbers.

**Two tiers clearing a corpus perfectly is a real result and a small one.** It convicts the
shortcut and it cannot rank the models — the fast and deliberating tiers are separated here by 17%
more output tokens and 53% more latency and by nothing else. See `Business.not_good_enough` on the
published kit page.

## The baseline is shipped, including where it wins and exactly where it does not

`--baseline` is a non-LLM extractor: seven worried-sounding words in the driver's note, no key, no
cost. It is very good at the parts that are regex work — **all nine structured fields, 495 of 495
cells, perfect** — and it is a deliberate *tone floor* on the tenth: it reads the driver's prose and
never compares the counts, which is precisely the shortcut the prompt forbids.

It scores **60.0% completeness accuracy — 22 of 55 records wrong**, with 10 incomplete deliveries
called complete and 12 complete ones called failures. Those 22 are exactly the 22 the corpus plants
a contradicting note on. Both model tiers got all 22 right.

**And watch what happens to the guardrail downstream.** The floor extracts
`recipient_signature_present` correctly every single time, by regex — and its review flag still
scores only 6 of 10 with 4 false alarms, because it inherits the tone-derived completeness verdict.
That is the honest lesson of shipping a business-condition guardrail: *it is only ever as good as
the field it reads.*

### A defect in the floor itself, found before anything was paid for

The floor's first keyword list contained `"flagging"`, which fires on a breezy note reading
*"nothing worth flagging"* — a negation. Four records were mis-registered, and **two of them were
records the corpus had deliberately made ambiguous**, so the bug flipped them back to the *right
answer for the wrong reason*: the floor's error count read 24 where the design plants 22.

Nothing would have caught that. Both numbers are plausible, and a floor scoring slightly worse than
designed looks like a floor working. The fix was the keyword list rather than the corpus, and the
property is now **asserted for free** in `evals/check_labels.py` before any run may spend: every
note template must classify to the register it was authored in.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it — and
the completeness verdict is a comparison, which is the one thing you should never ask a model to
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
ten fields × the whole record is ten times the input tokens of sending each field the section that
could possibly state it. **The bill is driven by the context, not by the question** — on the worked
example, the system prompt and field schema are 944 of 1,130 input tokens and the record itself is
186.

The saving is usually invisible, because the sections that get sent would have been sent anyway.
Here there is one you can point at: **`Receiving Site` is mapped by no field at all**, so the union
of the mapped sections leaves it out and it never reaches the provider. And note what
`SECTION_HINTS` maps `delivery_complete` to — the two quantity sections and the condition code, and
**not** the exception note. That is not a saving either; the note reaches the model anyway, as a
field in its own right. It is the map of where the answer actually lives.

### Spans are searched inside the field's own sections first

`src/extract.py::_locate()` looks for a value in the sections `select.py` maps the field to, and
only falls back to the whole document when it finds it nowhere. That is a change from the sibling
kits, and this corpus is why: **on a complete delivery the ordered and delivered quantities are the
same number**, so a document-wide search for `72` finds the *Ordered Quantity* line first and cites
it for both fields. The value is right, the section label is wrong, and nothing scores section
labels — a citation that looks checkable and is wrong is worse than none at all. Scoping costs
nothing and closes the whole class.

## Point it at your own delivery records

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per
delivery. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different POD layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct. Replace `compute()` before you route anything
real by it: the rule this kit ships is invented.

If your records are unlabelled — the normal case — the field grade, the confusion matrix and the
review flag's score all go away. What does not go away is the consistency diagnostic, and that is
the one figure you can compute on day one.

## What it does not do

It never files a claim, issues a credit, contacts a carrier or disposes of a shipment in any way,
and it is not a substitute for a receiving process. The guardrail reads two fields out of the
reply: if the model misreads the delivered quantity and then judges that misreading consistently,
the record is routed — or not routed — on a wrong number, and nothing here re-reads the document to
catch it. It reads one record at a time and never sums two stops against a single order, compares a
delivery against its own re-attempt, or reconciles a quantity stated in one unit against a limit
stated in another. No OCR — a photographed delivery note or a captured signature image extracts no
text, which is how a great many real PODs arrive. No auth, no database, no multi-tenancy, no
deployment story. It runs once per model, locally, and that run is what gets published.
