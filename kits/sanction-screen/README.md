# sanction-screen — is the alert and the watchlist entry the same party?

**UC052.** Point it at a screening alert review sheet — one customer record beside the watchlist
entry a screening engine matched it to — and get a field table back, plus an adjudication taken
afterwards in pure code: are these the same party, are they different parties, or does the file
simply not decide? Every answer names the identifier that produced it.

> **⚠︎ This kit clears nothing, blocks nothing and files nothing.** No alert is closed, no party is
> designated or de-designated, no account is frozen or released, no payment is stopped or let
> through, and no report of any kind is made to anybody. It proposes an adjudication with the
> deciding identifier attached, names what it could not determine, and **a human makes the call.**
>
> **The rulebook shipped with this kit (`data/rulebook.json`) is illustrative and is not an
> authority** — it was written for this kit and reproduces no sanctions programme, designation
> list, supervisor's guidance, industry matching standard or screening-vendor tuning. **Every name,
> list, programme, country, place and identifier in the corpus is invented**, and no real list,
> authority, programme, jurisdiction or person is named anywhere in it. Replace the rulebook with
> your own before you decide anything real by it. See `data/SOURCES.md`.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                                  # free — validates the gold set
python -m evals.run --run-id b000-sanction-screen-tone --baseline   # free — the tone floor
python -m evals.run --run-id t000-sanction-screen-stub --stub       # free — proves the wiring
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-sanction-screen --yes       # THIS SPENDS MONEY: one call per alert
python -m src.app                                             # the local UI on 127.0.0.1:8052
```

## The decision: an identifier comparison with a stopping order

Five checks, in order, stopping at the first that fires. The order is the whole difficulty.

```
adjudicate(customer_id_type, customer_id_value, listed_id_type, listed_id_value,
           customer_dob, listed_dob, customer_pob, listed_pob):
    a strong identifier of the SAME TYPE on both, values equal   -> same_party
    a strong identifier of the SAME TYPE on both, values differ  -> not_a_match
    any comparable moderate identifier that DISAGREES            -> not_a_match
    at least 2 comparable moderate identifiers that AGREE         -> same_party
    otherwise                                                     -> insufficient_information
```

**`insufficient_information` is a first-class answer, not a failure to produce one.** Two records
that do not carry enough to be separated or joined are exactly the case a screening desk has to
escalate rather than close, and the kit says so — with a named reason and with what one extra fact
would settle it — rather than inventing a verdict. **A kit that never says "I cannot tell" is worse
than one that does**, because on a screening queue the guess that costs is a confident
`not_a_match`: the alert is closed and nobody looks again.

**The rulebook is sent with every call.** "Which identifier outranks which" is a policy, and a
model cannot apply a policy it has never been shown. `src/prompt.py::rulebook_block()` renders
`data/rulebook.json` into the prompt rather than restating it in prose, so the model's instructions
and the gold labels cannot drift apart about the same policy. On the worked example it is 973 of
3,105 input tokens.

## The three decoys, and where they live

Three things are on every alert, decide nothing, and are on the sheet precisely because a person
reading it would weigh them:

| decoy | what it is | why it is there |
|---|---|---|
| `analyst_note` | one person's free-text impression at triage | written after seeing two names and a similarity score, **before anybody compared identifiers**. On **35 of 50 alerts (70%)** its register contradicts the rulebook's verdict |
| the nationality pair | the nationality on each record | a watchlist record's nationality is routinely stale or secondary, so two records for one party disagree about it all the time |
| **the engine's match score** | the screening engine's own fuzzy-name confidence | ⚑ **it never reaches the model at all.** It lives in the `Screening List` section, which `SECTION_HINTS` maps to nothing, so the union of the mapped sections leaves it out. It is the number a human anchors to first and it decides nothing |

The first two still reach the model — each is a field in its own right. `SECTION_HINTS` maps
`verdict` and `deciding_identifier` to the **two records and nothing else**; that is not a filter,
it is the map of where the answer actually lives.

## The five hard cases, each measured rather than asserted

`evals/check_labels.py` asserts a floor on every one of these before any run may spend, and fails
the run if a floor is not met.

| case | why a careless reader gets it wrong | alerts |
|---|---|---|
| **one strong identifier against several weak mismatches** | the names are transliteration variants, the nationalities disagree, **the places of birth disagree** and the engine scored the pair low — and both records carry the same passport number. Same party. Asserted directly: hide the identifier and the same sheet reads `not_a_match` | 6 |
| **a conflicting identifier beats everything that agrees** | identical names, identical full dates of birth, identical places of birth, identical nationalities, engine score 0.9+ — and two different passport numbers. Not a match. Asserted: hide the identifier and the sheet reads `same_party` | 8 |
| **two identifiers of DIFFERENT types corroborate nothing** | a passport number on one record and a national identity number on the other. It looks like two records that both carry a strong identifier; it is two facts about two different registries, and the rule falls through as though neither existed | 8 |
| **a partial date of birth is a stated fact and still not comparable** | `1978` against `1978-04-12` neither agrees nor disagrees. With the place of birth agreeing that leaves **one** agreement against a threshold of two. Asserted: complete the date and the sheet reads `same_party` | 7 |
| **a common name and nothing else** | three invented names recur across these alerts, with no comparable identifier and no comparable date. Nothing on the file decides it, and saying so **is** the answer | 8 |

## What it measures

One scored run over 50 alerts (`results/eval-r001-sanction-screen.json`), one tier, 12 concurrent
workers, 20.9 seconds of wall clock.

**850 of 850 extracted cells, 50 of 50 three-way verdicts, 50 of 50 deciding identifiers, 0 false
confidences, 0 false clearances, 17 of 17 escalation flags with no false alarms.** Perfect on every
published figure.

**That is a reason to distrust the corpus, not to trust the model.** A 50-alert single-seed set
that nothing gets wrong has stopped discriminating: it cannot rank two models, cannot tell you which
of this kit's own prompt rules is earning its place, and cannot tell you what happens on an alert
shaped in a way this corpus did not think to plant. See `Business.not_good_enough` on the published
kit page, which says so at length rather than leading with the score.

### The headline number is a honesty number

The three-way verdict is collapsed twice. **`false_clearance`** is an alert the rulebook would have
left open that the run closed — the expensive direction, because a closed alert is never looked at
again. **`false_confidence`** is the one this kit exists to publish: *of the alerts the file cannot
decide, how many did the run answer with a decision anyway?* It was **0 of 15**. Its opposite,
**`false_caution`** — hiding behind "I cannot tell" on an alert the file does decide — is published
beside it at **0 of 35**, because publishing only one direction would flatter the kit.

## The deciding identifier is scored separately, and that is deliberate

A run can reach the right verdict for the wrong reason. On an adjudication a person has to sign,
the reason is half the answer — "same party, because the passport numbers match" is a thing a
reviewer can check in five seconds, and "same party" alone is not. `deciding_identifier` is a
seventeenth field with its own grader and its own `right_verdict_wrong_reason` count. The run scored
**50 of 50 with 0 right-verdict-wrong-reason**; the free floor scored **24 of 50 with 3**.

## The baseline is shipped, including what it can and cannot say

`--baseline` is a non-LLM extractor: it regexes every structured field out of the sheet and decides
the verdict from the register of the analyst's note. Unlike most floors in this series **it can
reach all three answers** — a hedging phrase gives `insufficient_information` — so its
false-confidence count is a real measurement rather than an artefact of a two-value vocabulary.

It is **perfect on all fifteen structured fields — 750 of 750 cells** — and it scores **30.0% on the
three-way verdict (15 of 50)**, which is *below chance*. It **closes 11 of the 35 alerts that must
stay open**, and on the 15 alerts the file cannot decide it **asserts a decision on 11 of them**.

Below chance is not a fluke and it is not rigged. The note's register on this corpus follows the
screening **engine's name score**, and name similarity is decorrelated from identity here for the
same reason screening false positives exist: the alerts whose names look most alike are frequently
the ones the identifiers separate, and the alerts whose names look least alike are frequently one
party behind a transliteration. **A tone read does not merely lose accuracy on this shape of
decision — it points the wrong way.**

## There is no LLM judge in this kit

Gold is exact and an answer is one value, so `==` with light normalisation settles it — and the
verdict is an identifier comparison, which is the one thing you should never ask a model to
adjudicate.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine; serves the rulebook beside the answer |
| the rulebook | `data/rulebook.json` → `src/rulebook.py` — data, not code, so you can open it and disagree |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

## Point it at your own alerts

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and supply a gold record per alert.
**Replace `data/rulebook.json` first** — it is this kit's own construction, your institution's
policy about identifier strength is not this one, and everything downstream reads the file:
`src/rulebook.py` loads it, `src/prompt.py` renders it into every call, and `tools/build_corpus.py`
writes gold with it. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will**
need editing for a different sheet layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct.

If your alerts are unlabelled — the normal case — the field grade and every confusion matrix go
away, and the **consistency diagnostic** does not: `evals/judge.py` re-runs the rulebook over each
reply's own extracted values and counts the replies whose stated verdict disagrees with it. No gold
needed. On the free floor it caught **all 35** of its verdict errors with zero false alarms and no
labels at all. It is blind to a reply that misreads an identifier and then reasons correctly from
the misreading, and it is reported as a diagnostic rather than as this kit's guardrail.

## What it does not do

**It watches nothing and it acts on nothing.** It reads one alert review sheet that somebody else
assembled and proposes an adjudication. It does not screen, does not run a matching engine, does not
poll or subscribe to any list, does not close, escalate or file a case, does not freeze or release
an account, does not stop or release a payment, and does not notify anybody.

It reads natural persons only — a legal entity's alert carries a completely different identifier
set and this kit has no field for one. It cannot see anything the sheet does not state: a second
passport, a name change, a family relationship, an address history, a corporate ownership chain, or
the reason the entry was published at all. It treats an identifier as exact — a transposed digit is
a different identifier here, not a near miss. It does no OCR, and it does not resolve a name across
scripts beyond copying what is written. No auth, no database, no multi-tenancy, no deployment story.
It runs once per model, locally, and that run is what gets published.
