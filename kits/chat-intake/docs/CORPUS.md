# The corpus, and the licence line it sits on

## What it is

**Schema-Guided Dialogue (SGD)**, service `Banks_1`, `train` split.
<https://github.com/google-research-datasets/dstc8-schema-guided-dialogue>

**727 dialogues**, measured — not the round number a paper quotes. They live in 9 of the 127 train
shards; `tools/fetch_corpus.py` discovers which 9 rather than hard-coding them.

## Why this corpus and not an insurance one

The kit was first framed around insurance claims. That was overturned by evidence, not preference:
**no real, licensed conversational corpus exists for insurance intake.** Claim calls carry personal
data and are not published. Building one would have meant writing conversations ourselves and then
grading a model against a checklist we also wrote — which measures nothing.

SGD publishes **the required-fact list itself**, in its own `schema.json`:

| intent | required slots |
|---|---|
| `CheckBalance` | `account_type` |
| `TransferMoney` | `account_type`, `amount`, `recipient_account_name` |

Read at the source on 2026-08-09, and parsed by `tools/build_corpus.py` rather than typed. That is
the whole reason this kit's eval is credible: **the definition of "enough" is somebody else's**, and
it was committed to before anyone ran anything.

Every turn also carries `state.slot_values` — what the conversation has established so far. So the
grader is `==` against published ground truth, needs no judge model, and **costs nothing to re-run.**

## ⚠︎ The licence, and why the data is not in this repo

`LICENSE.txt` in the source repo opens **"Attribution-ShareAlike 4.0 International"** — CC BY-SA 4.0.
Read there on 2026-08-09, not recalled. (Note the filename: a fetch for `LICENSE` without the
extension 404s, which is how a licence check comes back "none found" on a repo that has one.)

**This repo is MIT. CC BY-SA is share-alike.** So:

- `tools/fetch_corpus.py` pulls the data at run time. It is never committed.
- `data/_fetched/` and `data/gold.jsonl` are **gitignored**. `gold.jsonl` quotes utterances, which
  makes it a derivative.
- `data/slots.json` **does** ship. It carries slot *names* — the dataset's own schema metadata —
  plus the attribution, the citation and this licence note. No dialogue text.
- Citation, as the project asks: Rastogi et al. 2020, *Towards Scalable Multi-Domain Conversational
  Agents*.

**This is the first kit here whose corpus does not ship, and that is a real cost.** Every sibling
renders its panel and its recorded results on a fresh clone, offline, with no key. This one needs
two commands first. The alternative was relicensing the repo or inventing the data, and inventing it
would have destroyed the only thing that makes the eval worth reading.

## ⚠︎ The split is carved from `train`, because there is no alternative

SGD ships train/dev/test, so the obvious move is to grade on `test`. Measured at the source:

- **`test` contains no Banks service at all.**
- **`dev` carries `Banks_2`** — the same two intents with renamed slots (`transfer_amount`,
  `recipient_name`, plus a `transfer_time` that does not exist in `Banks_1`).
- **`Banks_1` is train-only.**

So held-out is carved out of `train` by `sha256(dialogue_id) < 0.20`: deterministic, identical on
every machine, no seed to remember. **That is a weaker guarantee than a publisher's own split**, and
every number this kit reports says so rather than implying otherwise.

**Banks_2 turns the problem into an asset.** Same task, renamed schema, never seen — a genuine
unseen-schema probe, which is precisely what SGD was built to test and more than a native split
would have given us. Not run yet; it is the obvious second experiment.

## What the case set is, and what was dropped

A case is a conversation **prefix** plus the dialogue state at its end.

**Each dialogue stops at the turn its checklist first fills.** Taking every user turn gave 3,190
cases of which **2,402 — 75% — were already complete**, because these conversations continue well
past the intake into confirming and booking. On that set `always-stop` scored 75% having read
nothing, and the headline would mostly have measured how talkative the corpus is.

Scoped to the intake itself: **1,340 cases, 727 stop / 613 keep-asking**, and **3,567 later user
turns dropped**. The floor fell to **54.4%** on held-out — close to a coin flip, which is what an
eval set should look like.

The floor found that. It ran before any paid call, because it costs nothing to run.
