# docs-summarise — summarise a long document to a fixed brief

**UC003.** A 40–80 page government report goes in. A brief in a **fixed shape** comes
out: six sections, each with a weight, decided before anything ran. One model call
per document, on your key, on your machine.

**And nothing in this kit can tell you whether the brief is any good.** That is not
a gap — it is the reason this kit exists.

```bash
cp ../../.env.example ../../.env    # set PROVIDER, BASE_URL, API_KEY, MODEL once, for every kit
python -m evals.check_rubric        # free. Check what you are about to measure against
python -m src.app                   # the local UI at http://127.0.0.1:8767
python -m evals.run --run-id t000 --stub    # free. Proves the wiring end to end
```

## The thing that is different

| kit | how a score is produced | what it costs |
|---|---|---|
| `docs-qa` (UC001) | an LLM judge scores answers against a labelled set | tokens |
| `docs-extract` (UC002) | string comparison against a gold record — pure code | free |
| **`docs-summarise` (UC003)** | **a person reads the brief against a weighted rubric** | **reviewer-minutes** |

Two correct summaries of one document share almost no words, so there is no gold
string to compare against. Asking a model to score a model's summary would make
the headline figure a measurement of the judge — *no method validates itself*.

So the verdict is a person's, and everything here is built to make that cheap and
honest rather than to hide it:

- `evals/run.py` writes **evidence, not a score.** Six sections of prose per
  document, with what was sent and what was dropped beside them.
- `evals/grade.py` puts a person in front of that evidence one section at a time,
  and **times itself**, because `reviewer-minutes` is the cost unit and a manual
  method priced in tokens reads as $0.00 — which is not cheap, it is *unpriced*.
- `evals/baseline.py` holds the floor: **a grader who scores everything 3 already
  earns 60 of 100.** That is the first row of the board, never a footnote. A real
  score of 62 is barely better than doing nothing, and burying the floor makes 62
  look like a pass.

## The four layers

| layer | files | what it does |
|---|---|---|
| minimal UI | `ui/`, `src/app.py` | one document, one brief, six cards. No framework, no build |
| pipeline | `src/segment.py`, `src/pack.py` | cut the document into sections; order them and fit them to a token budget. **Pure code** |
| AI layer | `src/prompt.py`, `src/summarise.py`, `src/adapters/` | one call, one model, one key |
| eval layer | `evals/` | the rubric, the run record, the human grader, the baselines |

No auth, no database, no integrations. Swapping the model is `.env` and the same
run again — that is what `src/adapters/` is for.

## ⚠︎ The number to read before you read a score

**`pack.py` decides what the model sees.** These reports do not reliably fit in a
context window, so sections are sent in document order until the budget runs out
and the rest are **dropped**. A brief written from a truncated document is not a
measurement of the model, and it looks exactly like a good brief.

So every run record carries `documents_with_dropped_sections`, every document
record names the sections that were dropped, and the UI prints them in amber
above the brief. **A low score read without that number is not a finding.**

Ordering is document order, not a relevance ranking — ranking sections against the
rubric would be a retrieval step wearing this kit's name, and the ranking itself
would be unevaluated.

## The corpus

GAO reports, public domain (17 U.S.C. §105), pulled through GovInfo. **Each
document has had its own human-written brief removed** — GAO ships one, in two
different places depending on the rendition, and leaving it in would mean
measuring a model's ability to copy a summary that was already there. Both strips
are recorded per document in `data/corpus/manifest.json`; a document where neither
matched is not shipped.

The removed text is kept in `data/reference/` as **calibration for a grader**,
never as gold — it is the source's own shape, not this rubric's.

Full detail, including why these are archived reports rather than current ones:
[`data/corpus/SOURCES.md`](data/corpus/SOURCES.md).

## Status

**The corpus is not filled yet and no paid run has happened.** The pipeline is
proved end to end against one built document with `--stub`. `python -m evals.run`
is the step that spends; it prints what it is about to spend and stops for
confirmation first.

MIT, like every kit here.
