# docs-qa — answer questions over your own documents

A small, complete, runnable RAG pipeline: extract → chunk → retrieve → prompt → answer, with a
labelled test set, an eval harness that classifies every failure by cause, and a UI that shows you
each stage's actual output.

**It runs with no API key.** The corpus, the index and the recorded results ship in this repo, so a
fresh clone renders real output offline. A key unlocks *live* answers; it is not a prerequisite for
seeing the thing work.

## Run it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python3 -m src.app          # → http://127.0.0.1:8765
```

That is the whole setup. **Python 3.9 or newer** — the floor is `pypdf`'s, not ours; everything
else here is standard library.

For live answers, copy `.env.example` to `.env` and fill in three values:

```
PROVIDER=openai-compatible      # or: anthropic
BASE_URL=https://api.openai.com/v1
API_KEY=...                     # yours, on your machine. .env is gitignored.
MODEL=...                       # no default on purpose — a kit that picks a model picks your bill
```

`openai-compatible` covers OpenAI, DeepSeek, Groq, Together, Mistral, xAI, and any local server
(Ollama, LM Studio, vLLM) — `BASE_URL` is what selects between them.

## Everything else you can run

| command | what it does | needs a key |
|---|---|---|
| `python -m src.app` | the UI | no |
| `python -m src.index` | rebuild the index from `data/corpus/` | no |
| `python evals/check_labels.py` | gate the labelled set | no |
| `python evals/run.py --retrieval-only` | score retrieval, classify failures | no |
| `python evals/run.py --run-id <name>` | the full eval, including the model | **yes** |

## The five seams

Every part you might want to swap is one file, and each says so at the top. This is the map; the
files carry the detail.

| seam | file | swap it to change |
|---|---|---|
| 1 | `src/adapters/__init__.py` | the model or provider. Adding one is a function plus an entry in `PROVIDERS` |
| 2 | `src/extract.py` | how text comes out of a file format. Add a format with one entry in `EXTRACTORS` |
| 3 | `src/chunk.py` | how a document becomes retrievable pieces |
| 4 | `src/retrieve.py` | which passages the model sees. Ships keyword *and* embedding behind one call |
| 5 | `src/prompt.py` | what the model actually receives |

**Seam 1 is the teaching point, not the app above it.** It makes one claim checkable that everybody
asserts and nobody demonstrates: *swapping models is a one-line change, and knowing whether you
should is an eval run.*

## Point it at your own documents

1. Drop your files into `data/corpus/`
2. `python -m src.index`
3. Ask again

**What breaks when you do.** A format with no entry in `EXTRACTORS` is skipped and recorded, not
silently dropped. And **the labelled set stops applying the moment the corpus changes** — every
accuracy number in `results/` describes *this* corpus. Re-label before believing a score on yours.

## The eval, and what it will not tell you

Failures are classified rather than counted, because a single accuracy figure tells you the pipeline
is wrong and nothing about where. Each cause has a different fix and a different owner:

| cause | meaning | fix in |
|---|---|---|
| `not_extracted` | the text never survived the file | `src/extract.py` |
| `dropped_in_chunking` | extracted, but no chunk kept it whole | `src/chunk.py` |
| `bad_ranking` | a chunk had it; retrieval ranked it out | `src/retrieve.py` |
| `answered_wrong` | it was in the prompt; the answer is not | `src/prompt.py`, or the model |

**Two things this eval cannot currently measure, both printed on every run:**

- **`not_extracted` cannot fire.** `check_labels.py` verifies every answer fragment against the
  *extracted* text, and the taxonomy inspects that same text — so a label describing content that
  extraction lost cannot exist. The gate and the analysis are reading the same thing. Fixing it
  means labelling against the source document, which is a change to how labels are authored.
- **The grader is an exact substring match, so it measures quotation as much as correctness.** It
  scored 80% where the expected fragment was 1–2 words and 33% where it was 7+, on the same
  answers — so `check_labels.py` now caps fragment length. It still rewards a verbose answer over a
  correct terse one: *"Yes."* is marked wrong. Read `results/` before quoting any accuracy figure.

`results/` ships with runs already recorded, each stating what it could not verify.

## What this deliberately is not

A kit is the smallest thing that demonstrates a pattern well enough to learn from and fork. Every
layer added is a layer you have to understand before you can change the part you came for.

No auth, no users, no database, no multi-tenancy, no deployment story, no integrations, no
framework, no build step. One dependency, and it earns its place: `pypdf`, for PDF text.

If a kit starts needing any of that, the idea is too big for a kit.

## Licence and the corpus

MIT — see [LICENSE](../../LICENSE). The sample corpus is SQLite's documentation, public domain;
its provenance, the licence text and all 40 source URLs are in
[`data/corpus/SOURCES.md`](data/corpus/SOURCES.md).

**No API key is ever requested from you by anything in this repo except your own `.env`.**
