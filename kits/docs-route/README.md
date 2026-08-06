# docs-route — route an incoming document to the right queue

One document in, one queue out, with a confidence and a floor. If the model is not confident
enough, the document is **escalated to a person** rather than routed — and that third outcome is
measured and published alongside the other two, because a router that is only ever right or wrong
has nowhere to put the documents it should not have guessed at.

Runs on a laptop. Standard library only. One model call per document.

```bash
cp ../../.env.example ../../.env      # one shared connection for every kit; per-kit .env optional
python -m tools.fetch_corpus          # free — pulls from the Federal Register API
python -m tools.build_corpus          # free — builds the corpus and splits the labels out
python -m evals.run --run-id b001 --baseline keyword   # free — the thing a model has to beat
python -m src.app                     # the local UI, http://127.0.0.1:8768
python -m evals.run --run-id r001-<model>               # THIS SPENDS MONEY: one call per document
```

## The question this kit exists to answer

Not "is the model good". **Is the model worth its bill against thirty lines of if-statements?**

`evals/baseline.py` ships a keyword router — a handful of regular expressions over words the
document already contains. It costs nothing and runs in microseconds. Every model run is scored by
the same scorer, on the same 120 documents, and printed on the same board underneath it.

If the keyword router wins, that is the finding and it gets published. This kit is built so that
outcome is possible to discover rather than designed out.

## The three queues

| queue | what routing there commits you to |
|---|---|
| **Rule** | Binding. The comment window has closed; somebody has to read it against what the organisation does today. |
| **Proposed Rule** | Open for comment. Nothing binds yet, and there is a window in which saying something is still possible. |
| **Notice** | For information. Meetings, filings, applications — the queue whose job is to stay boring. |

Plus `unsure`, which is not a fourth queue but a refusal, scored separately.

**The two mistakes do not cost the same.** A proposed rule filed as a notice forfeits the comment
window and nobody finds out. A notice escalated to the legal queue wastes an hour and somebody
complains immediately. `evals/score.py` deliberately does **not** weight them — a weight is a
business input, and inventing one here would publish a guess as the kit's finding. It prints the
off-diagonal cells separately so the expensive direction is visible and you apply your own weight.

## What is measured, and what is not

- **Measured:** accuracy over everything given, accuracy over what it chose to answer, the
  withheld rate, a full confusion matrix, per-class precision/recall/F1, latency, tokens, cost.
- **Not measured:** anything about the real world. The corpus is **balanced by construction**,
  40 per class, and a real inbox is not — the Federal Register runs roughly 7 notices to 2 rules
  to 1 proposed rule. A balanced set answers *can it tell these apart*. It does not answer *what
  happens on Tuesday*, and the precision figures here will flatter a rare class.

## Why this one can be scored by machine when `docs-summarise` cannot

The gold label is the publisher's. The Office of the Federal Register assigns a `type` to every
document it prints, years before this kit existed and with no knowledge of this eval. So there is
a right answer nobody here wrote, and `==` is a legitimate verdict.

`docs-summarise` has no such answer — two correct summaries of one document share almost no words —
so its verdict waits on a person. Both kits are honest about which they are.

## Layout

```
data/corpus/       what the router is allowed to see: title, action, abstract. No agency, no type.
data/gold.jsonl    the labels. Nothing but evals/score.py opens this file.
src/taxonomy.py    the queues and what each one MEANS. Everything downstream reads them from here.
src/prompt.py      the prompt, generated from the taxonomy — never a typed-out class list.
src/route.py       the AI layer and the confidence floor. The guardrail lives with the router,
                   not in the scorer, so the published number comes from the code the app runs.
evals/baseline.py  the null router and the keyword router. Both free, both on the board.
evals/score.py     confusion matrix, per-class rates, two accuracies. The only file that reads gold.
```

## Cost

One call per document, ~500 input tokens and ~40 output. The whole 120-document run is small
change; `src/budget.py` counts calls against a shared daily cap before spending any of them, and
prints what it is about to spend first.

MIT. Part of [adhana-foundry-kits](https://github.com/adhana-ai/adhana-foundry-kits).
