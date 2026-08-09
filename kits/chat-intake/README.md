# chat-intake — collect a required set of facts across a conversation, and know when you have enough

**UC009.** Claims, loan applications, onboarding and support triage are the same job: there is a set
of facts you must end up with, and the work is getting them out of a conversation without asking
twice and without stopping early.

**The checklist is not ours.** It is published by the corpus, so *"did it collect enough"* is a
comparison against ground truth somebody else committed to in advance. That is what makes the
number worth reading — and it makes the eval **free**, because there is no judge model.

## Run it

```bash
cd kits/chat-intake
python3 -m tools.fetch_corpus       # ~25 MB, 9 shards. CC BY-SA 4.0 — fetched, never committed.
python3 -m tools.build_corpus       # -> data/slots.json (ships) + data/gold.jsonl (gitignored)
python3 -m evals.baseline held-out  # the floor. Free. Run it before anything else.
python3 -m src.app                  # -> http://127.0.0.1:8769
```

No API key needed for any of that. The page steps through real conversations and shows the checklist
filling — labelled **replay**, because those values are the dataset's own dialogue state and not a
prediction. Set `API_KEY` in `.env` and a model reads the same turns and answers beside it.

```bash
python3 -m evals.run --n 40 --run-id r001-<model>    # ⚠︎ one call per case. Costs money.
```

`--n` has no default on purpose.

## How it works — three steps, and only the middle one is a model

| step | what | where |
|---|---|---|
| carry state | the turns so far, and what the checklist still owes | `src/slots.py`, pure code |
| extract | which required facts the conversation has established | `src/prompt.py` + one call |
| decide | ask again, or stop | `src/slots.missing()`, a set difference |

**The model is asked to extract, not to decide.** Asking it *"do you have enough?"* would hand the
one deterministic step to the component that cannot be held to it. The checklist is known in
advance and set arithmetic is not a judgement call, so a model cannot claim a completeness its own
extraction does not support. That split is also what makes the eval cost nothing.

## What it measures

Three states per fact, and none may be folded into another:

- **collected** — stated, and the value is one gold accepts.
- **still missing** — named explicitly, never a blank cell. Costs one more question.
- **wrong against gold** — a value was captured and gold says it is not that. **The expensive one**,
  because the checklist reads as full and nothing downstream will ask again.

And, reported separately, **the turn decision**: ask again, or stop. It is not a fourth state — it
is what the kit is *for*. **Stopping early** gets its own number and is never averaged into a
decision accuracy: asking one question too many annoys somebody, stopping one too soon hands a
downstream process a record it believes is complete.

## The floor, measured before any model ran

298 held-out cases:

| floor | correct | wrong | missed | open | decision | stopped early |
|---|---|---|---|---|---|---|
| always-stop | 346 | 226 | 0 | 0 | **54.4%** | 136 |
| always-ask | 184 | 0 | 162 | 226 | 45.6% | 0 |
| copy-nothing | 0 | 0 | 346 | 226 | 45.6% | 0 |

**A model that does not clear 54.4% has not read anything.** `always-stop` is given gold's own
values on purpose, so it is the hardest constant to beat rather than a straw man — and note its
`stopped early` column: it is wrong in the direction that costs the most, on every case where the
conversation was not finished.

Running the floor is what caught the corpus defect described in [docs/CORPUS.md](docs/CORPUS.md):
the first case set was 75% already-complete, and `always-stop` scored 75% reading nothing.

## What this kit is not

**No results are recorded yet.** The one real run is the operator's to fire — it spends money on
their key, and "run once" is a published claim. `results/` is empty until then, and nothing in this
README quotes a model number, because there is not one.

Nothing persists between calls. Conversation state rides in the request: no session, no store, no id
that outlives it. If that changes, the kit has outgrown being a kit.

The next question is templated, not generated. Phrasing it well is a real product problem and it is
**not** the one measured here — grading it would need a judge, which is exactly what this kit
avoids, and a second call would double the bill for something no number covers.

## Licence

Code: MIT, like the rest of this repo. **The corpus is CC BY-SA 4.0 and is not redistributed here** —
see [docs/CORPUS.md](docs/CORPUS.md) for the boundary and why `data/` is mostly gitignored.
