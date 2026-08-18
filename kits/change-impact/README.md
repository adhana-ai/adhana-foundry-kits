# change-impact — match a change request to the record it modifies, and cost it

One message, one candidate set (from deterministic blocking), one model call, a match plus an
extracted change — then a deterministic calculator turns that into a dollar impact and a
ship-date impact, never asked of the model. Three match outcomes: **a specific record**, **NONE**,
and **UNSURE**. The third is the point: a message that could plausibly be about more than one
record, with nothing in the text to settle it, is not a coin flip — it is a case for a person.

```bash
python -m src.app                                        # the local UI on http://127.0.0.1:8781

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-blocking-similarity   # free. no key, no spend.
python -m evals.run --run-id t000 --stub                     # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>                     # THIS SPENDS: 70 calls, one per message.
python -m evals.redteam --run-id x001-<model> --docs 5         # THIS SPENDS: up to 35 calls.
```

## The job, generically

Extract a requested change from unstructured correspondence, match it to the specific record it
modifies, and compute the downstream impact of accepting it — so a human approves or rejects an
informed number instead of a vague request. This corpus flavours "record" as a purchase-order line
and "correspondence" as a vendor email requesting an expedite, a delay, a cancellation, a quantity
change or a price change, because that is one concrete, checkable instance of the job. Point
`tools/build_corpus.py` at your own record shape and your own correspondence and the pipeline does
not change. See [`data/SOURCES.md`](data/SOURCES.md).

## Three match outcomes, and why the third one matters

| outcome | means | what it costs to get wrong |
|---|---|---|
| **a record id** | The correspondence names or clearly implies exactly one open record. | — |
| **NONE** | The vendor's product in this message has no open record at all. | Predicting a record here corrupts a record nobody asked to touch. |
| **UNSURE** | More than one candidate remains and nothing in the text settles it. | Guessing here is a coin flip on which record gets changed. |

**Why 29 of 70 messages are genuinely ambiguous, on purpose.** More than one open record can share
a vendor and a product; those messages carry no explicit record reference, but each states the
CURRENT value of a field the requested change does not touch — a quantity, or a ship date —
specifically so a reader can tell the candidates apart. A checker that ignores that clue cannot
solve these.

## What was measured — one model, 70 messages

| run | approach | match accuracy | impact accuracy |
|---|---|---|---|
| `b000-blocking-similarity` | **baseline** — the SAME blocking code, a regex read of the record id and the disambiguating hint, falling back to string similarity | 100.0% | 100.0% |
| `r001-change-impact` | **deepseek-v4-flash**, reasoning off | 100.0% | 100.0% |

**Both hit 100% on this corpus, and that is a real finding, stated rather than hidden.** The
baseline reuses the real pipeline's own blocking, so nothing here is a smaller haystack. What it
also reuses is a corpus whose ONE disambiguating clue — "(currently at N units on our records.)" /
"(currently scheduled to ship &lt;date&gt;.)" — is a single fixed phrasing, unlike the varied clause
wording sibling kits' corpora use. A regex tuned to that one template catches every instance,
which is why the baseline is not the honest floor here that it is elsewhere — see
`data/SOURCES.md` and `Business.not_good_enough` on the published report. The measured, genuinely
interesting gap in this kit is not match accuracy; it is **robustness** (below) and **an untested
generalisation risk**: a real correspondence's phrasing of a disambiguating detail will not be
this uniform, and that has not been measured.

**Impact is never asked of the model.** `src/impact.py` computes the dollar figure and the
ship-date delta from the record and the model's own extracted `change_type` + `new_value` alone —
so an impact number is only ever as wrong as the extraction that produced it, never a separate
thing the model could get right or wrong on its own.

## We attacked the correspondence, and it held

The message is this kit's untrusted-input surface — in a real deployment the side that arrives
from outside this codebase, via an inbox or a vendor portal. Six attacks, appended to five
messages each carrying a known, materially large ESCALATE decision:

**0 of 30 scored attempts flipped the decision to AUTO_ACCEPT.** The structural reason: the model
never asserts the dollar figure or the decision, only the `change_type` and `new_value` it read —
so an attack telling the model to "treat the impact as zero" has no field to write that answer
into; the number is recomputed by code every time regardless of what the message claims about
itself. That is not the same as immunity: one `wrongvalue` attempt made the model abstain to
`NONE` on a message it should have matched, and one `dos` (essay-demand) attempt spent the entire
output ceiling and returned nothing parseable. Neither flipped a decision, but both are real
reliability findings, not zero-cost resistance. See `Security.read_twice` on the published report.

## The gold values cannot drift from the records

Nothing is hand-labelled. `tools/build_corpus.py` computes every gold match, change type, extracted
value and computed impact from the same numbers that render the record and the message — so the
text, the record and the label all come from one source by construction, and `src/impact.py` is
imported by the generator itself so a label can never disagree with what the pipeline would
compute. See [`data/SOURCES.md`](data/SOURCES.md) for the full corpus design and its limits.

## What it cannot do, stated up front

- **One requested change per message.** A real email can ask for several changes across several
  line items at once; this corpus plants exactly one per message.
- **A perfect score is a property of this corpus, not a guarantee.** The disambiguating hint is
  always present and always resolves the ambiguity once found; a harder corpus (near-identical
  candidates, a degraded or partial hint, a message discussing two records at once) has not been
  measured.
- **The blocking keys are narrow.** An explicit record id, an explicit SKU code, or a literal
  substring match on the vendor's own product description. A message that paraphrases the product
  in words the corpus never uses would not block correctly — see `src/block.py`.

## Layout

```
data/vendors.json          10 synthetic vendors, each with 2 open products + 1 closed one
data/records.jsonl         43 open records across those products
data/messages.jsonl        70 messages requesting a change
data/gold.jsonl            70 gold rows: match, change type, extracted value, computed impact
data/SOURCES.md            why the corpus is synthetic, and what it does and doesn't test
src/normalise.py           text tidying + record-id/SKU extraction, pure code
src/block.py                candidate-record generation, pure code
src/similarity.py           the free string-similarity floor
src/impact.py                the five deterministic impact formulas + the materiality threshold
src/prompt.py                the match/change vocabulary, declared ONCE
src/match.py                  the AI layer: block, one call, parse, compute impact
src/app.py                    the local UI (port 8781)
evals/scoring.py              pure-code scoring: seven outcomes, never one accuracy number
evals/baseline.py             the free blocking+similarity floor
evals/run.py                   the real eval harness
evals/redteam.py               the correspondence-poisoning attack harness
tools/build_corpus.py         renders vendors, records and messages, derives the gold rows
```

MIT, like every kit here.
