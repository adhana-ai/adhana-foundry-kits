# AI Foundry — Use-Case Kits

**Nothing is built yet.** This repo exists so kit #1 has somewhere to live. It is private until
that first kit is complete: a public repo holding one half-finished kit is a worse first impression
than a private one that opens complete.

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

The whole idea stands or falls on every kit having the same shape. The standard lives in the
Foundry repo as pure data — `mcp/standards/use_case.py`, seven lenses with a typed per-lens
contract — and is read by the scaffolding and validation tools rather than restated here. There is
no second copy to drift.

## Stack

Python core, minimal vanilla-JS UI. No framework — closest to how Foundry itself is built, and the
eval harness is naturally Python.

## Licence

MIT. See [LICENSE](LICENSE).
