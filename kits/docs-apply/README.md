# docs-apply — it made the change. What else did it change, and should it have refused?

Letting a model edit a document is the first thing anyone tries and the last thing anyone measures.
The question that gets asked is *did it make the change*. The two questions that decide whether you
can ship it are **what else moved** and **did it write when it should have stopped and asked**.

This kit puts a change request against a policy document, applies it two ways — a free rules editor
and a model — and scores three populations that it never averages into one number: the intended
edit, every other line that moved, and the requests where the right answer was to refuse.

```bash
python3 tools/build_corpus.py --verify   # rebuild from seed and prove the tree matches, byte for byte
python3 evals/baseline.py                # a WORKING editor, measured. 0 model calls, $0.00
python3 evals/combine.py                 # rules + model veto, re-scored from records. 0 calls, $0.00
python3 -m src.app                       # the panel — http://127.0.0.1:8773
```

**No key is needed for any of that, and there is nothing to install** — this kit is Python standard
library end to end. Only `evals/run.py` and the panel's model button call out.

## The corpus, and why it had to be written rather than found

60 policy documents, one change request each, generated from seed `20260815`. `--verify` rebuilds all
121 files and diffs them, so nothing here is a claim about a corpus you cannot reproduce.

This kit's output is an **edited artifact**, so scoring needs the exact bytes the document should end
up as — not a label. Every request therefore carries an authored *after* state, including the 24
where the correct after state is *the file, untouched*.

| family | n | the right answer |
|---|---|---|
| `apply` | 36 | make the change |
| `ambiguous` | 8 | **refuse** — the number named appears in two clauses |
| `missing` | 8 | **refuse** — the thing to change is not in the document |
| `contradiction` | 8 | **refuse** — the change breaks a cross-reference elsewhere in the file |

Those eights are the denominators of every family rate below. One row moves a family by 12.5 points.

## Both methods, measured

`evals/baseline.py` is an anchored find-and-replace that parses clause numbers and headings, and
**refuses when the anchor is not unique**. A floor built to lose proves nothing, so this one was
built to win where a regex genuinely should.

| | rules editor (`b000`) | the model (`r001`) | rules + model veto (`c001`) |
|---|---|---|---|
| edits applied | **100%** of 36 | **100%** of 36 | **100%** of 36 |
| other lines moved | **0** | **0** | **0** |
| refused correctly | **66.7%** of 24 | **13.0%** of 23 | **70.8%** of 24 |
| unsafe writes | 8 | **14** | 7 |

⚑ **They do not separate on the edit. They separate entirely on refusal, and the free one wins.**
The model carried out changes that should have been refused more than twice as often as a regex did.

**Note the denominator moves: 24, then 23.** One reply came back with the right document and the
wrong envelope — `p040` returned `DECISION: APPLY` and the complete file but omitted the closing
`---END DOCUMENT---` sentinel, so the strict parser rejected it. It is counted as a broken reply
contract, not folded into the refusal rate. A rate whose denominator quietly changes is not a rate.

### By family

| family | rules editor | the model | combined |
|---|---|---|---|
| `apply` | 36/36 | 36/36 | 36/36 |
| `ambiguous` | 8/8 | 2/8 | 8/8 |
| `missing` | 8/8 | 0/7 | 8/8 |
| `contradiction` | **0/8** | 1/8 | 1/8 |

**Contradiction is where both of them fail**, and it is the family that matters most: the change is
valid on its own line and breaks a clause somewhere else in the file. The combination catches one
extra — one veto used — and that is the whole of what the model bought.

## The three things the model did with a request it should have refused

Among its 23 scored refusal rows:

| outcome | n | what it means |
|---|---|---|
| declined | 3 | said no |
| **unsafe write** | **14** | changed the bytes when it should not have |
| harmless rewrite | 6 | acted, but returned the file unchanged |

The last row is deliberately not counted as a refusal. It did not decline; it happened not to do
damage. Scoring it as caution would turn luck into a safety figure.

## Where it breaks, and what is not measured here

- **The model returns the whole document on every call**, so output tokens scale with document size
  rather than with the size of the change. A one-word edit to a fifty-page contract costs a
  fifty-page reply. That is the argument for a patch format, and **this kit does not have one.**
- **Zero collateral damage was measured, which was not the expected result.** It may be a property
  of short, highly structured documents rather than of the model. Long prose is not in this corpus.
- **One model tier was run.** Nothing here argues a larger model would not refuse better — it was
  not tried, and on this evidence it is the obvious next question.
- **The contradiction family is a single planted pattern** — a numeric cross-reference to the clause
  being deleted. A document whose internal dependencies are subtler is not represented.
- Changes that cannot be localised to a line (a renumbering, a clause moved between sections, a
  table restructured) are outside the corpus. English only.

## Which one you should actually use

| if | pick | avoid |
|---|---|---|
| your edits are mechanical and precisely specified | the free rules editor | paying a model to do find-and-replace |
| your documents hold cross-references a change could break | rules for the edit, model as veto — and a person after both | the model on its own |
| you need it to know when **not** to act | neither, unsupervised | reading the 100% applied rate as readiness |

⚠︎ **The best of the three still writes 7 changes that should have been refused.** Every system here
needs a human between it and the file.

## The seams

| seam | file | swap it to change |
|---|---|---|
| the refusal families | `src/corpus.py` | which kinds of request are traps, and how many of each |
| the free floor | `evals/baseline.py` | what the model is being compared against |
| the prompt | `src/prompt.py` | what the model is told would make a change unsafe |
| the combination rule | `evals/combine.py` | how the two arbitrate — currently, either may veto |
| the provider | `src/adapters/` | any OpenAI-compatible endpoint, or Anthropic |

## Point it at your own documents

Put them in `data/corpus/`, their expected results in `data/gold/`, and one line per request in
`data/requests.jsonl` with `should_write` set. Both methods run unchanged and the diff scorer needs
no new labels — the *after* state **is** the label.

⚠︎ **Every number above describes this corpus.** They stop applying the moment you change it.

## Running the model half

```bash
cd ../.. && cp .env.example .env && chmod 600 .env    # the SHARED connection — every kit reads it
cd kits/docs-apply
python3 evals/run.py --probe 3 --no-thinking   # 3 calls, proves the shape before the money
python3 evals/run.py --no-thinking             # 60 calls
```

Set the key **once at the repo root**, not once per kit. A `kits/docs-apply/.env` is an override,
merged key by key, and it is only for pointing this one kit at a different model.

The recorded run is `r001-docs-apply-flash`: one call per request, ~439 input and ~194 output tokens,
p50 2.6s, and **$0.000116 per request**. Grading is free — a diff, in pure code, with no model in the
scoring loop, so re-scoring the committed records costs a measured $0.00.

**No API key is ever requested from you by anything in this repo except your own `.env`.**

MIT — see [LICENSE](../../LICENSE). The corpus is ours: we wrote every byte from the seed in
`tools/build_corpus.py`, so there is no upstream grant to honour and nothing third-party is
redistributed. Part of [adhana-ai/adhana-foundry-kits](https://github.com/adhana-ai/adhana-foundry-kits).
