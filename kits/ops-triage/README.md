# ops-triage — it is 03:14, your phone goes off, should it have?

Every team running anything has a pager, a pile of rules that decide when it fires, and nobody left
who remembers why the rules are what they are. The rules are an error count and a keyword. They get
the loud cases right and the quiet ones wrong, in both directions:

- **Woken for nothing.** A health check has been timing out every six seconds for nine days. It puts
  47 errors into a five-minute window and it has never once meant anything. The pager goes off at
  3am anyway — and enough of that is how a rotation learns to stop reading it.
- **Not woken at all.** One WARN line says a certificate expires in 47 hours and the renewal job
  last succeeded 62 days ago. One line. No threshold reacts to one line. In two days every login in
  the estate stops, and the first you hear of it is a customer.

This kit takes **five minutes of a log stream**, decides **PAGE** or **HOLD**, and scores the two
mistakes apart. Every team with an on-call rotation has this problem — the services differ, the
shape does not.

```bash
python3 tools/build_corpus.py      # the corpus, byte-identical every time, MIT
python3 -m evals.check_labels      # re-derives the labels from the stream and checks them
python3 -m evals.baseline          # a WORKING pager, measured. 0 model calls, $0.00
python3 -m src.app                 # the panel — http://127.0.0.1:8012
```

**No key is needed for any of that.** Only `evals/run.py` and the app's *Ask the model* button call
a model.

## The unit of work is a slice of time, and that changes the first station

Every other kit in this repo receives its unit of work already formed — a document arrives, a
question is asked, a pair of rows is handed over. **An event stream has no units in it.** Something
has to decide where one thing being judged stops and the next begins, and here that is
`src/window.py`: fixed five-minute buckets, pure code, before any model is involved.

⚠︎ **That cut is not a neutral step and the kit does not pretend otherwise.** A five-minute bucket
and a fifteen-minute bucket are two different questions about one incident. Widen it and the retry
storm's recovery line lands inside the window, so the correct answer flips from page to hold.
Narrow it and one cascade splits into four windows that each look like a separate outage — which is
how a pager storm is manufactured out of a single root cause. The bucket size is recorded as a
comparability guard on every run, because two runs at different bucket sizes were scored against
different ground truth.

## The free floor, measured — read this before any model number

⚑ **The floor here is not a strawman, and that is the whole argument of the kit.** It is an error
count plus a real SRE keyword regex — what a great many rotations are running right now — scored
through the **same** `src/decide.py` the model's answers go through. `evals/baseline.py` sweeps it
over **49 settings across four floors**. On 123 candidate windows (20 page / 103 hold):

| floor | best setting | missed incidents | false pages | traps handled |
|---|---|---|---|---|
| always-hold | — | **20** | 0 | 3 of 6 — `flapping` `retry-storm` `deploy` |
| always-page | — | 0 | **103** | 3 of 6 — `cascade` `quiet-killer` `silence` |
| count only | 49 | 14 | 0 | 4 of 6 |
| count + keyword | 49+ | 14 | 0 | 4 of 6 |
| count + keyword + absence | 49+ | **8** | **0** | **5 of 6** |

⚑ **Read the first two rows together — they are the shape of the problem.** Doing nothing and doing
everything each handle exactly three traps, and the two sets are disjoint: their union is all six.
Every row below them is an attempt to be in both places at once, and none of them gets there.

⚑ **No setting of any floor handles all six traps.** The one none of them reaches is
`quiet-killer`, and it is not a tuning problem: one WARN line, no count reacts to one line, and the
text is ordinary English about a certificate because nothing is on fire yet.

⚑ **And the knob everybody tunes turns out to be inert.** Deleting the error-count threshold
entirely produces the *identical* result to its best setting — 8 missed, 0 false pages, the same 5
traps. Every other setting of it only adds false pages. `evals/baseline.py` proves that with a
no-count control row rather than asserting it.

⚠︎ **`always-hold` scores 83.7% "accurate" on this corpus while missing every incident in it.**
That is why this kit publishes two numbers and never one, and why you will not find an accuracy
figure anywhere in it.

## The gate, and the pre-filter that nearly deleted the kit's own finding

Nothing sane asks a model about every five-minute slice of a healthy system, so
`src/window.py::candidates` decides which windows are worth a call: **123 of 240**, the other 117
held for free.

⚠︎ **The obvious gate — "any ERROR, FATAL or WARN" — drops every `silence` window.** A service that
has stopped logging produces no line of any level, so the cheapest possible filter silently
discards the hardest trap in the set before anything can look at it, and the scores come out
*better* for it. The gate therefore compares each window against its history and reports a service
that has gone quiet.

⚑ **Gate recall is measured and published beside every score: 1.0 here.** The first version of that
absence check scored **0.85** — it detected the moment silence *started* and went blind the moment
after, because by the second window of an outage the previous window is itself silent. An outage
does not stop being an outage because it is still going on.

## What the model is asked, and what it may answer

`src/prompt.py` is the single source of the vocabulary. **Two verdicts, and the absence of a third
is a design decision:**

| verdict | means |
|---|---|
| `PAGE` | wake somebody now — this is an incident or is about to become one |
| `HOLD` | do not wake anybody — noise, or something that can wait for the morning |

The sibling `data-match` kit offers `UNSURE`, because a pair of twins is genuinely unsettleable and
handing it to a person is a real product behaviour. **A pager has no such state.** At 03:14 the
phone either rings or it does not, and an "unsure" verdict would have to be mapped onto one of those
before anything happened — quietly, to `hold`, which is the tempting direction because it wakes
nobody. That converts every hesitation into a missed incident hidden inside a calm score.

⚑ **The absence is computed by code and handed to the model as a stated fact.** A window in which
`payments` emitted nothing contains, by definition, no line saying so. This is the division of
labour the kit argues for — **code establishes what is true, the model judges what it means** — and
the same fact is given to the `absence` floor above, so nobody can claim the model won on evidence
the rules were never shown.

## The five outcomes, and why none of them collapses

| outcome | what it is |
|---|---|
| `paged_correct` | a real incident, and somebody was told |
| `missed_incident` | **an outage nobody was told about** — the cost is the whole of the downtime |
| `false_page` | somebody woken for nothing — cheap once, corrosive in bulk |
| `held_correct` | noise, correctly left alone |
| `no_verdict` | nothing usable came back |

They reconcile against the window count. ⚠︎ **`no_verdict` never collapses into `held_correct`**,
and on this kit that trap is subtler than on any sibling: a model returning nothing pages nobody, so
a totally broken run reads as a calm night with zero false pages — the best-looking score the kit
can produce.

## Where it breaks

**The bucket size.** Nothing here measures how much of any score is the five-minute cut. It is a
product decision baked into the labels, recorded as a guard, and not swept.

**The corpus is invented,** so it holds the six traps we thought to plant and no others — and its
incidents are politely one per window, which real ones are not. See `data/SOURCES.md` for why real
production logs cannot be published at all.

**Silence detection has a horizon.** `gone_silent` compares against six windows of history, so once
a service has been quiet for more than thirty minutes, silence becomes the new normal and the check
stops firing. That is a real ceiling on how long an outage can go unnoticed here.

**The absence is given to the model, not discovered by it.** This kit measures whether a model
judges silence correctly once told about it. Whether a model can notice something missing from its
input is a different question, and this kit does not ask it.

## The seams

| seam | file | swap it for |
|---|---|---|
| the model | `src/adapters/__init__.py` | any provider; `.env` plus the same run again |
| the cut | `src/window.py` | a different bucket size, or a sessioniser; re-label after |
| the floor | `src/rules.py` | Alertmanager, PagerDuty event rules, an anomaly detector |
| the gate | `src/window.py::candidates` | anything cheaper or broader; **measure gate recall after** |
| the decision | `src/decide.py` | a ticket queue instead of a page |

MIT. Part of [adhana-ai/adhana-foundry-kits](https://github.com/adhana-ai/adhana-foundry-kits).
