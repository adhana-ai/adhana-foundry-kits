# AI Foundry — Use-Case Kits

**Kit #1 runs.** [`kits/docs-qa`](kits/docs-qa) — *answer questions over your own documents* — is a
complete pipeline with a UI, a labelled test set, an eval harness that classifies every failure by
cause, and results recorded from a real run. **It works with no API key**: the corpus, the index and
the recorded results all ship in the repo.

```bash
cd kits/docs-qa
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python3 -m src.app          # → http://127.0.0.1:8765
```

Still outstanding on kit #1: `spec.json`, the cross-links back to Foundry, and the walkthrough
video. Everything described above is runnable today — nothing in this repo is a mockup.

## What a kit is

[AI Foundry](https://foundry.adhana.ai) **explains** how modern AI works. A Use-Case Kit makes it
**demonstrate** — for one real job, a small runnable project you can execute, change and re-measure.

Every kit has the same seven parts, in dependency order:

| # | Part | What it is |
|---|---|---|
| 1 | `spec.json` | the use case declared as data — job, tools, guides it routes to, dataset id, metrics, provenance |
| 2 | Sample dataset | ~50 labelled examples, checked in, small enough to read |
| 3 | **AI adapter layer** | one interface, several providers behind it |
| 4 | The app | the smallest thing that does the job end to end |
| 5 | Eval harness | runs the dataset through the app, scores it, emits JSON with `as_of` / `verified_by` |
| 6 | Error analysis | the failure taxonomy |
| 7 | Cross-links | back to the guides, terms and deep-dives that explain each part |

### Part 3 is the teaching point, not part 4

The adapter layer is the reason to build this rather than link to somebody's demo. It makes one
claim checkable that everybody asserts and nobody demonstrates:

> **Swapping models is a one-line change. Knowing whether you should is an eval run.**

Flip the adapter from a frontier model to a cheap one, re-run the dataset, and watch accuracy and
cost move on the same dashboard.

## Why the shape is fixed

The whole idea stands or falls on every kit having the same shape. **Seven lenses, each with a
typed contract**: what a kit must report about its UI, its business case, its architecture, its
data, its prompt, its evaluation and its cost. The shape is held as data by the tooling that
authors and checks a kit, and read from there rather than restated here, so there is no second
copy to drift.

The tooling itself is not part of this repo. **What is here is the kit** — the pipeline, the
labelled set, the graders, the harness — which is the part you would fork, read and change.

## Stack

Python core, minimal vanilla-JS UI. No framework — closest to how Foundry itself is built, and the
eval harness is naturally Python.

## Licence

MIT. See [LICENSE](LICENSE).
