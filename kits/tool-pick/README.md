# tool-pick — which tool does this request need, and when should it stop calling them?

You wired a model to your own tools and it works, mostly. What you cannot tell from watching it is
how often it reaches for a tool it did not need — latency and money for nothing — and how often it
stops one step short and hands back half an answer that reads like a whole one.

Nothing in a normal tool loop is deciding whether another call is worth making. **That decision is
the entire cost model.** This kit gives a model four tools and 120 labelled requests, records the
sequence it chose **in order**, and scores it against the sequence that answers the request.

```bash
python3 tools/build_corpus.py     # the corpus, byte-identical every rebuild
python3 -m evals.check_labels     # refuses a label set that cannot be scored honestly
python3 -m evals.baseline         # a WORKING keyword router, 4 settings. 0 calls, $0.00
python3 -m evals.escalate         # router-then-model policies, re-scored from records. 0 calls
```

**No key is needed for any of that, and there is nothing to install** — Python standard library end
to end. A fresh clone gets the whole argument for the kit for $0.00. It cannot re-run the model.

⚠︎ **This kit ships no UI.** Its panel is on the Foundry page and renders the recorded run; the two
screenshots in `docs/shots/` are from there. Everything in this repo is a command line.

## The four tools, and the closed list

| tool | takes | returns |
|---|---|---|
| `shop_sql` | one read-only `SELECT` over `customers` and `orders` | up to 20 rows |
| `doc_search` | a few keywords | the matching policy notes, in full — there are six and they are short |
| `calc` | an arithmetic expression | the number |
| `today` | nothing | the date |

⚑ **The catalogue is closed and the loop enforces it.** A model that names a fifth tool gets a
refusal back, not an exception and not a guess at what it meant — "asked for something that does not
exist" is a distinct failure from "picked the wrong one of the four".

⚑ **All four are read-only, local and pure.** No network, no writes, no auth. That is the line
between a kit and a product, and an agentic kit is the one most likely to be asked to cross it: the
moment a tool can act on the world, the eval stops being about tool *choice* and becomes about blast
radius, which is a different and much larger kit.

⚠︎ **`today()` returns a fixed date, 2026-03-31.** It does not read the clock. A corpus whose answers
change at midnight cannot be diffed, and `evals/check_labels.py` fails if the two copies disagree.

## The corpus, and the traps in it

120 requests at seed `20260813`, each carrying the tool sequence that answers it — or none, or a
declaration that nothing here can. There is no public benchmark of *requests labelled against your
four local tools*, because the tools are the variable; generating both together is the only way the
labels can be true.

| trap | n | why it is hard |
|---|---|---|
| `plain` | 40 | one obvious tool. The control group |
| `two-step` | 24 | **two tools, in order** — the second needs what the first returned |
| `unanswerable` | 16 | nothing available can answer it; the right move is to decline |
| `needs-none` | 16 | no tool needed, and the words point straight at one |
| `wrong-surface` | 12 | the obvious keyword names the wrong tool |
| `ambiguous` | 12 | two rules match; only one is right |

⚠︎ **The labels are true for this catalogue and no other.** A fifth tool makes every sequence a claim
about a different question.

## The free floor, measured — read this before any model number

`src/router.py` is one regex per tool, tried in order, truncated to a call budget. The sort of router
somebody writes in an afternoon — not a straw man, and not tuned against the labels. It is scored by
`src/score.py`, **the same module the model is scored by**.

| call budget | exactly right | wasted calls |
|---|---|---|
| **1** | **46.7%** — 56 of 120 | 28 |
| 2 | 43.3% | 56 |
| 3 | 43.3% | 60 |
| 4 | 43.3% | 60 |

⚑ **Raising the budget makes it worse, and above two nothing moves at all** — no request matches a
third rule, so the router's ceiling is its rules and not its budget.

**By trap, at its best setting:**

| trap | wrong | how |
|---|---|---|
| `plain` | 0/40 | — |
| `wrong-surface` | 0/12 | — |
| `ambiguous` | 12/12 | wrong tool |
| `two-step` | 24/24 | 12 stopped early, 12 wrong tool |
| `unanswerable` | 16/16 | ran a tool on all of them |
| `needs-none` | 12/16 | called a tool it did not need |

⚠︎ **It passes `wrong-surface` on rule ORDER, not on reading.** `evals/baseline.py` ships that
control: swap `doc_search` and `shop_sql` and 0 of 12 wrong becomes **12 of 12**. The floor is one
line away from failing every trap, and its score there is luck. That is stated because a floor whose
strength is accidental would otherwise flatter itself.

## The model, and the number that is not the headline

Recorded run `r015-tool-pick-flash`, one tier, `max_steps` 4, `max_tokens` 512:

| | |
|---|---|
| tool sequence exactly right | **89.4%** — of the **94** requests it answered |
| **returned nothing usable** | **26 of 120 — 21.7%** |
| ran a tool on a request nothing could answer | 6 of 16 |
| tool calls wasted | 9 of 73 |
| per request | ~2.9s, **1.75 model calls**, $0.000178 |

⚠︎ **The 26 are the run's real problem, not its score.** Every one ended unparsed. Those rows average
1,969 reasoning characters against 663 on the answered ones, and 16 of their steps came back
`finish_reason: length` — this model's thinking is billed inside `completion_tokens` and ate the
512-token budget before the answer got any. It is published as a finding rather than smoothed over.
**The fix is a bigger ceiling and a second run that has not been bought.**

### The outcomes

| outcome | n |
|---|---|
| correct | 84 |
| wrong tool | 0 |
| stopped early | 0 |
| kept going | 4 |
| should have declined | 6 |
| **no verdict** | **26** |

## Comparing the two — and the ruler problem

⚑ **The model and the floor are not close, and the gap is in a named place.** The model reaches three
trap kinds the router gets **zero** of at any setting: `two-step` (11 correct), `unanswerable` (9) and
`ambiguous` (8). Those are unreachable by a keyword rule in principle, not by tuning.

⚠︎ **The floor is 46.7% on its own row and 50.0% in the side-by-side, and both are right.** Its own
row scores it under the corpus's rule, where `calc` is required; the side-by-side scores it under the
model's rule, where `calc` is optional. **16 two-step rows move between them, 4 of those to correct.**
The gap survives comfortably and the conclusion is unchanged — but a comparison is only a comparison
if both sides are measured with the same ruler, so the two numbers are kept apart and labelled.
`evals/escalate.py` re-derives it, 0 calls.

## The label that was wrong, and what was done about it

⚠︎ **The method is a list comparison, so the labels were what needed validating — and one was wrong.**
14 requests scored `stopped_early` because the model did the arithmetic itself instead of calling
`calc`. Every one of those answers is correct, verified against the shipped database, and the system
prompt had told the model not to call a tool it did not need.

`evals/rescore.py` applies the corrected rule to the **recorded outputs**, calls nothing, and both
result files are committed side by side: **74.5% → 89.4%, 15 rows moved, the rows themselves
byte-identical.** Re-scoring recorded outputs is not a second run, and shipping the before-file is
what lets you check that.

## Which one you should actually use

| if | pick | avoid |
|---|---|---|
| one request, one obvious tool, vocabulary you control | the keyword router you already have | paying per request for a decision a regex already makes |
| requests that need two tools **in order** | the model | assuming a bigger call budget fixes the router — raising it made things worse |
| requests nothing you have can answer | **neither, yet** | shipping either one unsupervised |
| tools that write, or that are slow or expensive | **not this kit** | reading these numbers as applying to your case |

⚠︎ **6 of 16 times it ran a query for a question nothing available could answer, and returned a
confident empty result** — the failure that looks most like an answer. The router does that on all
16, so the model is far ahead. Far ahead is not safe.

## Where it breaks, and what is not measured here

- **The prompt grows with the transcript.** Every tool result so far is carried verbatim into the next
  call, so a request needing four tools sends the first three results again. Input averaged 808 tokens
  per request across 1.75 calls. A tool returning 20 rows rather than one number pushes that up in
  shape, not in degree — and this corpus deliberately does not contain one.
- **The longest labelled sequence is two.** Nothing here measures a deeper chain, and the step cap of
  4 would start binding.
- **The step cap is 4.** A model that would have answered on its fifth call is recorded as capped, not
  as wrong, and nothing here measures how many those are.
- **All four tools are local, read-only and instant** — exactly when calling one wrongly costs nothing.
- **One model, one run.** A second tier on the identical requests is not measured.
- **The corpus is invented**, so it holds the five failure modes we thought to plant and no others.

## The seams

| seam | file | swap it to change |
|---|---|---|
| the tool catalogue | `src/tools.py` | add or remove a tool; the prompt, the guard and the refusal message all follow from the one list. ⚠︎ every label is relative to it |
| the step cap | `src/loop.py` | `MAX_STEPS`. It is the comparability guard — two runs at different caps were not asked the same question |
| the floor's rules | `src/router.py` | one regex per tool, **and their order**, which is load-bearing |
| the provider | `src/adapters/` | any OpenAI-compatible endpoint, or Anthropic |

## Running the model half

```bash
cd ../.. && cp .env.example .env && chmod 600 .env    # the SHARED connection — every kit reads it
cd kits/tool-pick
python3 -m evals.run --dry-run                        # what it would cost. 0 calls
python3 -m evals.run --run-id r015-tool-pick-flash    # the real thing
```

Set the key **once at the repo root**, not once per kit. Grading calls nothing — two lists are
compared — so the eval's own cost is a measured $0.00, not an unpriced one.

**No API key is ever requested from you by anything in this repo except your own `.env`.**

MIT — see [LICENSE](../../LICENSE). The corpus is ours: `tools/build_corpus.py` writes the seeded
database, the six notes and all 120 requests, so nothing third-party is redistributed. Part of
[adhana-ai/adhana-foundry-kits](https://github.com/adhana-ai/adhana-foundry-kits).
