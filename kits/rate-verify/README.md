# rate-verify — check that a billing account is on the rate class it actually qualifies for

**UC039.** Point it at one utility billing-account record, get a ten-field table back — plus a
routing decision taken afterwards in pure code, from two of the extracted values: is this account
on the wrong rate, and if it is, has the bill already gone out? Nothing here re-rates an account,
issues a credit or contacts a customer; the flag is a routing signal.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the pure-code floor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per record
python -m src.app                                     # the local UI on 127.0.0.1:8775
```

## The rate is a lookup, not an opinion. The billing rep's note is not evidence about it.

A billing-account record puts the customer's service class, the meter type, a month's metered
usage, a peak demand reading, the rate code somebody applied, and a billing rep's own note about
the account on the same page. Only the first five decide anything.

This kit's invented rate ladder is four codes deep:

| code | qualifies when |
|---|---|
| `R-1` | the account is Residential |
| `GS-1` | commercial, and neither rule below fires |
| `GS-2` | commercial, peak demand **at or above 50 kW** |
| `TOU-8` | commercial, **interval-metered AND usage at or above 15,000 kWh** — and it **outranks** `GS-2` |

That last row is the sharpest test in the corpus. An account can read like a textbook `GS-2` case —
demand well over the boundary — and the correct answer is still `TOU-8`, because the meter and the
usage decide it first. A reader applying "demand decides it" alone answers `GS-2` every time.
**Eight of the 55 records are exactly that case**, so it is measured rather than anecdotal.

The comparison lives in one function, `is_rate_correct()` in `src/extract.py`, and is used in three
places — the corpus generator that wrote gold, the prompt that states the ladder to the model in
words, and the scorer that grades it — so the kit cannot drift about what "correct" means.

## The guardrail is a business condition, and it needs labels — which is the honest half

`compute()` in `src/extract.py` runs on whatever the model returned, never on gold, and asks one
question: **is this the record somebody has to fix today?**

```
needs_review  <=>  rate_correct == "no"  AND  bill_status == "sent"
```

A misrated account still in draft can be corrected before it goes out — nothing has reached the
customer. The same mismatch on a bill already sent means a corrected bill or a credit, which is the
case a billing desk actually has to act on. **An `unknown` on either value is not a pass**: the
function returns `None` rather than guessing.

⚠︎ **This is the kit's own simplification, not a real utility's billing-adjustment policy.** No
published tariff, regulatory rule or adjustment procedure was consulted, and none is reproduced. A
real desk weighs the dollar size of the correction, how many cycles it has been wrong, and any
notice requirement. This is two booleans, chosen because it is the smallest rule that is genuinely
useful and readable off one reply.

## What it measures, and the number that matters most

55 records, 10 fields, **550 extraction cells**. Two model tiers, one run each, 110 calls in total.

| | pure-code floor<br>`b000-rules` | fast tier<br>`r001-rate-verify` | deliberating tier<br>`r002-rate-verify` |
|---|---|---|---|
| extraction accuracy | **0.96** | **1.00** | **1.00** |
| values returned with a span | 0 of 262 | **262 of 262** | **262 of 262** |
| hallucinated values | 0 | 0 | 0 |
| rate-correct verdict | **0.60** acc · 0.63 recall · 0.59 precision | **1.00** · 27 TP / 0 FP / 28 TN / 0 FN | **1.00** · 27 TP / 0 FP / 28 TN / 0 FN |
| needs-review flag | **0.75** acc · 8 TP / 8 FP / 6 FN | **14 of 14, no false alarms** | **14 of 14, no false alarms** |
| tokens in / out | — | 66,398 / 13,182 | 66,398 / **14,931** |
| latency p50 / p95 | — | 2,393 ms / 3,083 ms | **3,838 ms / 4,740 ms** |
| wall clock, 55 records | 0.0 s | **134.4 s** | **210.1 s** |
| failed records | 0 | 0 | 0 |

**The floor is the finding.** A pure-code shortcut that never calls a model already gets **96% of
the extraction right** — the fields are mostly there to be read. Where it collapses is the
*judgement*: **60% on the rate-correct verdict**, with 12 false positives and 10 false negatives out
of 55. That gap — 96% on reading, 60% on deciding — is what the model tier is actually buying here,
and it is the number to quote if somebody asks whether this needed a model at all.

**The deliberating tier bought nothing measurable.** It scored identically to the fast tier on every
published grader, while taking **56% more wall clock** and 13% more output tokens. On this corpus,
the cheaper tier is the correct choice, and that is a result of the run rather than a preference.

## ⚠︎ Both tiers scored perfectly, and that is a problem with the evidence, not proof of the kit

550 of 550 cells, 55 of 55 verdicts, 14 of 14 review flags, no false alarms, on 110 calls. **A
corpus that nothing gets wrong has stopped discriminating.** It convicts the pure-code shortcut and
it cannot rank the two model tiers against each other — the one comparison a second paid run exists
to make. Read the perfect scores as "this corpus is not hard enough to separate them", not as "this
is solved".

Specifically unverified:

- Whether either tier still scores 55 of 55 on a **larger or adversarially built** set of
  rate-mismatched records. All 27 mismatched cases here resolved correctly on both tiers, and 27 is
  not enough to rule out a confusion this corpus did not think to plant.
- Whether the `TOU-8`-outranks-`GS-2` precedence holds under cases this generator does not produce.
  **19 of 55 records involve `TOU-8` on one side or the other, and in only 6 of those does the
  precedence actually decide the answer** — the account qualifies for `TOU-8` while its demand alone
  would have said `GS-2`. Six deciding cases is not a stress test of a three-level priority order.
- Whether `needs_review` is a **useful** condition to route on. It scores 14 of 14 against a gold
  built from the same two booleans, which measures the code and not the policy. **No billing or
  revenue-assurance desk has looked at the records it picked.**
- How the flag behaves when the model is wrong — neither tier was wrong, so that path never ran.

## Where it breaks

- **Scanned or photographed statements.** There is no OCR step, and a real utility bill in
  production is very often a rendered PDF or a photo of a paper notice.
- **A record whose sections are not headed.** `segment()` falls back to one whole-document segment,
  so a span names `"document"` and locates nothing useful.
- **Scale.** One call per record, no concurrency, nothing shared between records: 55 records is
  134.4 s on the fast tier. A monthly billing run at a mid-size utility is hours, not minutes,
  before anything is parallelised. There is no batching and no caching.

## Security: three of four boundaries hold on evidence, and the fourth is the one this shape invites

**0 attack trials were run.** The account note is free text an outside party wrote, and it sits in
the same prompt as the ladder the model is asked to apply. **Whether an instruction hidden in
`account_notes` could move `rate_correct` is unmeasured** — no attack run exists. Also unmeasured:
behaviour against a hostile provider response crafted to break the JSON extraction in
`src/prompt.py::parse`.

Half the planted ambiguity in this corpus is tonal rather than adversarial: breezy notes reading
"Rate schedule confirmed correct at last review" are used truthfully on correctly-rated accounts
**and against type on misrated ones**, so a model that trusts the note instead of the ladder is
caught by the grader.

## The four layers

`segment` → `select` → `prompt` → `extract`, each a small module under `src/`, each replaceable on
its own. The model is reached through `src/adapters/`, which speaks raw HTTP to every provider on
purpose: a forker runs this on whichever key they already hold, and giving one vendor its SDK would
bake a preference into the exact file whose job is not having one.

## Where this corpus came from

Generated here, by `tools/build_corpus.py`, from the fixed seed `20260821` — **55 records,
24,660 bytes, byte-identical on every rebuild**, with 55 matching gold rows. There is no
third-party data in this kit. Every account id, division name, rate code and billing-rep note was
invented. **No real utility, filed tariff or published rate schedule is named or reproduced.**
The planted fault mix is stated in the generator: 6 class swaps, 9 demand-boundary swaps, 8 missed
`TOU-8` overrides, 4 wrongly applied `TOU-8`s — 27 misrated records against 28 correct ones.

Full detail, including why an invented corpus rather than a real one, is in
[`data/SOURCES.md`](data/SOURCES.md).

## Point it at your own billing records

Replace `data/corpus/*.txt` with your own records and `data/gold.jsonl` with one row per record
carrying the ten field values. `python -m evals.check_labels` validates the gold set before you
spend anything. If your rate ladder differs — and it will — `correct_rate_code()` and
`is_rate_correct()` in `src/extract.py` are the two functions to change, plus the words describing
the ladder in `src/prompt.py`. Change them together: the whole point of the single-function rule is
that the generator, the prompt and the scorer cannot disagree.

## What it does not do

It does not re-rate an account, issue a corrected bill, raise a credit, write to a billing system,
or contact a customer. It reads one record, returns ten fields with a span for each, applies one
stated rule, and flags the records a person should look at. **The rate a customer is billed on is
the utility's filed tariff and its own billing system's decision — this proposes a verdict with its
reasoning and names what it could not determine.**
