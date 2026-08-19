# fin-close — check a recurring JE and account reconciliation against its documented basis

One drafted recurring journal entry, one account reconciliation, one model call, a verdict per
check — with the clause it relied on. Four checks: posting account, amount versus the prior-period
approved figure, calculation basis, and reconciliation residual against the account's documented
materiality band. Three verdicts: **clean**, **defect**, and **unverifiable**. The third is the
point: a basis document that never states a fact is not a pass, it is a gap, and calling it clean is
how a silently-changed basis or an unexplained residual slips through unchecked.

```bash
python -m src.app                                  # the local UI on http://127.0.0.1:8775

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-regex        # free. no key, no spend.
python -m evals.run --run-id t000 --stub            # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>           # THIS SPENDS: 60 calls, one per close cycle.
python -m evals.redteam --run-id x001-<model> --cycles 5   # THIS SPENDS: up to 35 calls.
```

## What this kit never does

It never posts a journal entry and it never clears a reconciling item. Every check below produces a
**verdict and a citation for a named preparer and a named reviewer to act on** — segregation of
duties is preserved outside this kit, exactly as every basis document's own duties paragraph states.
Nothing in `src/close.py`, `src/app.py` or the UI writes anything as "approved." If you are looking
for the line that enforces this, there isn't one function to point at — there is no function that
does the opposite anywhere in the kit.

## Four checks, and why the third and fourth carry `unverifiable`

| check | means | what it costs to get wrong |
|---|---|---|
| **account** | Does the drafted entry post to the account the basis document states for this recurring template? | A misposted recurring entry compounds every period it repeats. |
| **amount** | Does the drafted amount match the prior-period APPROVED amount, allowing normal fluctuation and nothing more? | An unexplained jump that clears as clean is how a basis change ships without anyone deciding it should. |
| **basis** | Does the drafted entry's stated calculation method match what the basis document describes? | This is the named risk this kit exists to catch: a recurring entry that silently changes its calculation basis while the amount still looks plausible. |
| **residual** | Is the reconciliation residual within the account's documented materiality band? | An unexplained residual above threshold, called immaterial, is a real problem write-off nobody signed. |

**Why silence gets its own verdict instead of collapsing into "clean".** 2 of the 12 recurring-JE
templates in this corpus never document a calculation basis at all — "the calculation method for
this recurring entry is not recorded in this workpaper" — and 3 of the 12 never document a
reconciliation materiality band for their account. A checker that defaults an undocumented fact to
"no violation found" is indistinguishable, from the outside, from a checker that actually looked and
found nothing. `unverifiable` is what tells the two apart, and it is exactly the corpus expression of
this kit's own open assumption: **that each recurring JE's documented basis is stored somewhere
machine-readable, rather than held only in a preparer's memory or a prior-year workpaper.** Where
that assumption fails, the honest answer is `unverifiable`, never a guessed `clean`.

## What was measured — the honest floor, run and committed; the model run is not fired yet

| run | what | overall accuracy | answered | false clean | false alarm |
|---|---|---|---|---|---|
| `b000-regex` | **baseline** — regex against one fixed phrasing per fact | 60.4% | 100% | 0 | 20 (11.6% of gold clean) |
| `t000` | **stub** — deterministic fake provider, proves prompt → call → parse → score end to end | 71.7% | 100% | 43 (100% of gold defects) | 0 |

See [`results/eval-b000-regex.json`](results/eval-b000-regex.json) and
[`results/eval-t000.json`](results/eval-t000.json). **No real model has been run against this corpus
yet** — that step needs a live API key on the operator's own account (`../../.env`, shared across
every kit in this repo) and spends real money, so it is a deliberate, confirmed action rather than
something this kit does on import. Run `python -m evals.run --run-id r001-<model> --yes` once a key
is configured to produce the first real number, then update this table from
`results/eval-r001-<model>.json` — never type a score here from intent.

### The regex baseline is honest, not a strawman

The corpus's basis documents state each fact in one of two or three hand-written phrasings, and the
regex baseline is written against the phrasing it happens to read first — the same way a person
free-texting a quick extractor would write one. It scores **100% on account** (the account code sits
beside the word "account" in every phrasing this corpus writes, so a loose pattern transfers) and
**25% on basis** (a pattern that only matches one of three ways the calculation method gets stated).
See [`data/SOURCES.md`](data/SOURCES.md).

### The stub is a wiring proof, not a competitor

`t000` answers every check "clean" from a fixed rule and cites the basis document's first line
regardless of what it actually says — it exists to prove the prompt is assembled, the reply is
parsed, and the scorer runs against gold correctly, end to end, without a key. Its 43 false cleans
are not a finding about any model; they are what "always say clean" costs against a corpus that
plants 43 real defects. `evals/baseline.py` is the honest floor; the stub is not.

## We attacked the basis document, wiring proven, real attack not fired

`evals/redteam.py` targets the **residual** check specifically — the guardrail this kit states most
directly is that an unexplained residual above the documented materiality band is never
characterized as immaterial. Six attacks, appended to five close cycles' basis documents, each try
to make the model wave through a residual that is, in fact, still above threshold. The stub run
(`results/redteam-t000.json`) proves the harness end to end — a fixed rule that always answers
`residual: defect` naturally resists all six by construction, which is why that number is a wiring
proof and not a security finding. The real attack (`python -m evals.redteam --run-id
x001-<model> --cycles 5 --yes`) has not been fired; it needs the same live key and spends up to 35
calls.

## What it cannot do, stated up front

- **One basis document per recurring template, no versioning.** A real basis document amended
  mid-relationship, or a template with more than one applicable workpaper, is a shape this kit has
  not been measured against.
- **At most one planted defect family per close cycle.** A real month-end close can carry several
  independent problems on the same entry at once — a changed basis AND a misposted account, say; the
  measured baseline numbers above do not speak to that case.
- **The residual check is a threshold comparison, not a judgment call.** A real reviewer sometimes
  accepts an above-threshold residual with a documented explanation, or flags a below-threshold one
  anyway. This corpus's gold residual verdict is derived mechanically from the materiality band
  alone.
- **No defence against a poisoned basis document, until the real attack is run.** See "We attacked
  the basis document" above. A workpaper system or close-management tool that could be tampered
  with, even briefly, is the supply-chain risk `evals/redteam.py` exists to measure — and that
  measurement is still pending a key.

## The gold verdicts cannot drift from the close cycles

Nothing is hand-labelled. `tools/build_corpus.py` computes every gold verdict from the same
template facts (account, prior-period approved amount, calculation basis, materiality band) that
render both the basis document and the drafted close cycle itself — so the text, the entry and the
label all come from one source by construction. Defects are planted on purpose and round-robined
across the four checks so per-check accuracy is measurable rather than guessed; `unverifiable` is
forced by a real omission (exactly 2 of 12 templates lack a documented basis, exactly 3 of 12 lack a
documented materiality band — chosen by a fixed sample, not an independent coin flip per template,
so the proportion this file claims is the proportion that ships), never a coin flip. See
[`data/SOURCES.md`](data/SOURCES.md) for the full corpus design and its limits.

## Layout

```
data/basis/*.txt           12 synthetic recurring-JE basis documents, phrasing and order varied
data/close_cycles.jsonl    60 drafted close cycles (journal entry + reconciliation worksheet)
data/gold.jsonl            60 gold verdicts, one per close cycle, derived mechanically
data/templates.json        the 12 recurring templates' account, has_basis and has_threshold flags
data/SOURCES.md            why the corpus is synthetic, and what it does and doesn't test
src/prompt.py              the check and verdict vocabulary, declared ONCE
src/close.py               the AI layer: load basis, one call, check the citations
src/app.py                 the local UI (port 8775)
evals/scoring.py           pure-code scoring: exact match plus the false-clean/false-alarm split
evals/baseline.py          the free regex floor, honestly narrow
evals/run.py                the real eval harness
evals/redteam.py           the basis-document-poisoning attack harness, targeting `residual`
tools/build_corpus.py      renders basis documents and close cycles, derives the gold verdicts
```

MIT, like every kit here.
