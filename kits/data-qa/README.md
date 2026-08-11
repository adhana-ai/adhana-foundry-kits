# data-qa — ask your own database a question

**Natural language query. Text-to-SQL. NL2SQL.** You ask in English, a model writes one SQL
statement, a read-only guard checks it, and the pipeline runs it against a SQLite database and
shows you the rows *and the query that produced them*.

This is UC010 in [AI Foundry](https://foundry.adhana.ai)'s use-case kit series. Like every kit it
is four layers and nothing more — a minimal UI, the pipeline, the AI layer, the eval layer. No
auth, no server, no deployment story.

```bash
git clone https://github.com/adhana-ai/adhana-foundry-kits
cd adhana-foundry-kits/kits/data-qa
python3 tools/build_db.py        # builds data/shop.db from a fixed seed. No network.
python3 -m src.app               # http://127.0.0.1:8010
```

No `pip install`. There are no dependencies — sqlite3, urllib and http.server are all standard
library. **You do not need an API key to see it work**: the database and the recorded run ship in
the repo, so the app renders real output immediately. A key is needed only to ask a *new* question.

## What it actually does

```
schema card ──▶ prompt ──▶ one model ──▶ GUARD ──▶ execute ──▶ rows + the SQL
                                          │
                                          └─ not a single read-only SELECT? nothing runs.
```

**The model never sees a row of your data.** It is shown the schema — table names, column names,
types, foreign keys — and nothing else. If you later decide to include sample values to improve
accuracy, that is a real decision with a privacy consequence; make it deliberately.

## The guard, which is the point

The model is asked a question and returns a *statement*, and a statement can delete the table it
was asked about. Every other failure in this kit produces a wrong number you can throw away. This
one produces a database you cannot get back.

Two independent layers, and neither is decoration:

1. `src/guard.py` — an **allowlist**: one statement, and it must be a `SELECT` (or a `WITH` that
   resolves to one). Comments and string literals are stripped before the decision, so
   `SELECT 1; -- \n DROP TABLE x` is counted as the two statements it is. Anything not positively
   recognised as a read is refused.
2. `src/execute.py` — the connection is opened `file:...?mode=ro`, SQLite's own read-only flag. A
   parser can be fooled; a read-only file descriptor cannot.

Verified in both directions: ten attack shapes refused, five harmless ones allowed (including
`WHERE name LIKE '%delete%'` and a semicolon inside a string literal), and with the guard bypassed
entirely the read-only connection still blocks the write.

## How it is scored

**Execution match.** There is no single correct query — `>= '2024-01-01'` and
`strftime('%Y', d) = '2024'` are the same answer written twice — so comparing SQL strings would
mark correct answers wrong. The generated query is *run*, and its result set is compared against
the result set of the gold query. Two queries agree if the data agrees.

```bash
python3 evals/check_labels.py    # free, no key: proves the ruler itself is sound
python3 evals/run.py --dry-run   # prints exactly what a run would spend, calls nothing
python3 evals/run.py --run-id my-first-run
```

**Where that ruler is blunt, stated rather than hidden:** on a database this size two different
queries can return the same rows by coincidence. Execution match cannot tell that from
understanding. The claim is *"the answer was right"*, never *"the model understood the schema"*.

**This kit has no free scoring half.** Other kits in this repo score part of their pipeline offline
because that part is pure code. Here every score needs a generated query and that needs the model.
`--dry-run` exists so you can see the bill before you pay it.

## The sample database

`customers` and `orders` — the worked example from Foundry's own Query Construction page, joined on
`customer_id`. 400 customers, 5,000 orders, generated from a fixed seed so **every clone rebuilds
the byte-identical database** and the gold answers stay true for everyone.

MIT, same as the repo. Nothing scraped, nothing redistributed, no licence argument to have.

Three properties are planted on purpose, because a corpus that cannot express the failure cannot
demonstrate that the eval layer earns its keep:

| planted | why it matters |
|---|---|
| **112 customers with no 2024 orders** | an inner `JOIN` silently drops them — the classic wrong answer to "average revenue per customer" |
| **135 orders with a NULL amount** | `AVG` skips NULLs without saying so |
| **one shared display name** | `GROUP BY name` merges two different customers; `GROUP BY customer_id` does not |

Each is a mistake a competent person makes, and each is invisible in the result.

## The failure taxonomy

A single accuracy figure tells you the pipeline is wrong and nothing about where. Each cause has a
different owner:

| cause | means | fix |
|---|---|---|
| `refused_by_guard` | the model wrote a statement that writes | `src/prompt.py` — SYSTEM |
| `invalid_sql` | it ran and SQLite rejected it | `src/prompt.py`, or the model |
| `wrong_result` | it ran and the rows disagree with gold | the model, or the schema card |
| `false_refusal` | said CANNOT ANSWER to an answerable question | `src/prompt.py` — SYSTEM |
| `missed_refusal` | invented schema for an unanswerable question | `src/prompt.py`, or the model |
| `timed_out` | the query never finished | `src/execute.py` bounds |

`missed_refusal` is the one to watch: confident SQL against columns that do not exist, which is the
database equivalent of a fabricated citation. Two of the twenty labelled questions have no gold
answer at all, purely to catch it.

## Where it stops working

The **whole schema goes into the prompt**. There is no retrieval step and no schema linking. That
is honest and simple for two tables, and it stops working when the schema no longer fits the
context window — a few hundred tables, or a few dozen very wide ones. At that point the answer is
"you now need schema linking", not a bigger prompt.

Also out of scope, deliberately: it is **single-turn** (no "now filter that to 2023"), **read-only**,
and points at **one database**.

## Point it at your own data

Replace `data/shop.db` with your own SQLite file — `src/schema.py` reads the schema out of the
database rather than from anything written down, so the schema card follows automatically. Then
write your own `data/labelled.jsonl` with gold SQL, and run `evals/check_labels.py` until it is
clean. The gold set is the part that takes real work, and it is also the part that makes any number
you publish mean something.

MIT. No API key is ever requested from a reader, on any surface.
