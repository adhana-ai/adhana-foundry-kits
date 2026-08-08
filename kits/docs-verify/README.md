# docs-verify — check each claim against its cited source

**UC007.** A document of claims in, a verdict per claim out. Each claim names the source it is
based on; the kit resolves that citation, sends the source and the claims in a single model call,
and returns one of three verdicts per claim **with the sentence it relied on**.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once.

```bash
python -m tools.fetch_corpus                      # free, network — raw CTG pulls (never shipped)
python -m tools.build_corpus                      # free — the 20 documents + 174 labelled claims
python -m evals.baseline --run-id b000-lexical    # free — what word-matching alone scores
python -m evals.run --run-id t000 --stub          # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r00N-<model> --no-thinking   # THIS SPENDS MONEY: one call per document
python -m src.app                                 # the local UI on 127.0.0.1:8770
```

## Three verdicts, and why the third one is the whole kit

| verdict | means | why it is separate |
|---|---|---|
| **supported** | the source states this, or plainly entails it | — |
| **contradicted** | the source states something incompatible | the easy case: two values disagree |
| **not stated** | the source neither asserts nor denies it | **the case that matters** |

A claim the source is simply silent about is what a hallucination looks like from the outside:
plausible, on-topic, and unbacked. Most checkers collapse it into "not supported" and lose the
distinction — but a model that **invented** a fact and a model that **caught a real error** need
opposite responses from you. So `not_stated` is a first-class verdict here, and `not_stated`
recall is the metric to read first. A checker that never says it looks respectable on accuracy
(the class is 23% of the set) and is useless for the job it was bought for.

## What it cannot do, stated up front

**The citation is given, never retrieved.** There is no index and no top-k — a claim names its
source and the kit checks it against that source. That is the real production question ("the model
cited X; does X actually say this?"), and it is what keeps this kit from being
[docs-qa](../docs-qa) with a different prompt.

The cost is real and is not hidden: **this kit cannot catch a claim that cites the wrong document
entirely.** It measures fidelity to the cited source, not choice of source.

## What was measured

20 public-domain ClinicalTrials.gov records, 174 claims (88 supported / 46 contradicted /
40 not stated). One call per document — the claims for a document are batched into its single
call, which is why 174 claims cost 20 calls rather than 174.

| run | what | accuracy | not-stated recall | false support |
|---|---|---|---|---|
| `b000-lexical` | free word-matching, no model | 37.4% | 100% (precision 27%) | 1 |
| `r002-docs-verify-flash` | the fast tier, thinking off | 98.3% | 100% | 1 |
| `r003-docs-verify-pro` | the reasoning tier, thinking off | 100% | 100% | 0 |

The baseline is the interesting row. Word overlap alone gets **100% recall on `not_stated`** —
a claim about peer review shares almost no vocabulary with a study record — and then collapses
where reading is actually required, at 21.6% recall on `supported`, because `supported` and
`contradicted` differ by one value in an otherwise identical sentence. That is a precise
statement of what the model is buying you.

## Three defects this kit found by running rather than by reasoning

Recorded because they are the point of running at all, and each is commented at the site it
happened.

1. **`r001` recorded 0 input and 0 output tokens for all 20 calls.** `verify()` read
   `res["usage"]["input_tokens"]`, a dict `adapters.complete()` has never returned. Zero is a
   plausible-looking number, so nothing failed — it was found by *reading the run record*. `r002`
   is the corrected run every cost figure comes from.
2. **`r001` had one document return nothing, with `finish_reason="stop"`** — not truncation. The
   run record had thrown the raw reply away, keeping only the first *successful* one, so the
   interesting question was unanswerable. Failed calls now keep their raw text.
3. **`/api/verify` crashed on every request**, returning a key the pipeline stopped producing.
   Found by clicking the live UI, which is the only thing that exercises that path — the eval
   harness never touches it. Same class of defect as UC006's, found the same way.

## The labels cannot drift from the documents

`data/claims.jsonl` is not hand-typed. Every claim is derived from the same structured field the
document text is rendered from, so text and label come from one source by construction, and the
build *refuses to ship* a claim it cannot stand behind — a supported claim's value must appear in
its document, and a contradicted claim needs the true value present **and** its asserted value
absent. See [`data/corpus/SOURCES.md`](data/corpus/SOURCES.md) for the licence, the method, and
the two real defects that check caught on its first run.

## Layout

```
data/corpus/      20 CTG records as plain text  (public domain — see SOURCES.md)
data/claims.jsonl 174 claims, labelled by construction
src/prompt.py     the one prompt, and the parser that never invents
src/verify.py     the whole AI layer: resolve citation -> one call -> check the quotes
src/app.py        the local UI server
evals/judge.py    pure-code scoring: the 3x3 matrix, per-class recall, quote fidelity
evals/baseline.py the free lexical baseline
evals/run.py      the runner. Prints the call count and stops for confirmation.
```
