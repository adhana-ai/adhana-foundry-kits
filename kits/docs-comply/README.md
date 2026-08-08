# docs-comply — check a document against a rulebook

Check one document against a **fixed rulebook**, rule by rule, and get back a verdict per rule with
the line it relied on. The rulebook here is real: **42 CFR Part 11 §11.28(a)(2)**, the data elements
a responsible party must submit to register a clinical trial, transcribed from the eCFR by code.

```bash
pip install -r requirements.txt        # nothing but the standard library is actually required
python -m src.app                      # the local UI on http://127.0.0.1:8771

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.baseline --run-id b000-label     # free. no key, no spend.
python -m evals.run --run-id t000 --stub         # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>        # THIS SPENDS: 30 calls, one per document.
```

## Three verdicts, and why the third one is the whole kit

| verdict | means | what it costs to get wrong |
|---|---|---|
| **met** | The document satisfies the rule, and a line says so. | A **false met** ships a breach with a tick on it. The expensive error, counted separately from accuracy. |
| **breached** | The document **addresses** the rule and fails it. | A compliant document sent back for rework, and a reviewer who stops trusting the checker after the second false alarm. |
| **never addressed** | The document is **silent**. No line can be quoted, so the quote is empty. | Called met, a mandatory disclosure that was never made disappears entirely — nobody re-checks a rule the checker passed. |

**Why silence gets its own verdict instead of collapsing into "breached".** In `docs-verify`, the
sibling kit, silence is *neutral*: nobody is at fault when a source does not speak to a claim. Here
silence is usually **the finding itself** — a required disclosure never made. And the two have
different remedies: a breach is a wrong statement someone must correct, a never-addressed rule is a
missing statement someone must write. A checker that merges them hands the reader the wrong job.

## What it cannot do, stated up front

- **It is not a compliance audit and must not be read as one.** It checks whether a rendered
  registration record *states* the elements Part 11 lists. A real audit works from the sponsor's
  full submission, accounts for the waivers and deadlines in §§11.44 and 11.54, and is done by
  someone qualified to do it.
- **Some rules can never be satisfied here.** `Human Subjects Protection Review Board Status` and
  `IND or IDE Number` are not exposed by the public API at all, so they read as never-addressed on
  every document. That is a fact about the API, not a finding about the trial.
- **No retrieval, and no rule selection.** The whole document is checked against every rule, every
  time. Cost therefore scales with document length **and** rule count together — this kit gets more
  expensive on long documents rather than smarter about them.
- **One call per document.** All 41 rules are batched into a single call. That is what makes 30
  documents cost 30 calls instead of 1,230.

## What was measured

One paid run, 30 calls, 2026-08-08. Scored over the **1,068 applicable** rule-verdicts (162 of the
1,230 are rules the regulation does not bind, dropped before scoring).

| run | what it is | accuracy | breached recall | false met |
|---|---|---|---|---|
| `b000-label` | **baseline** — pure code, no model. "Is the element's label in the document?" | **95.97%** | **0.0** (0/38) | 7 (2.54%) |
| `r001` | **deepseek-v4-flash**, reasoning **off**, 41 rules per call | **93.45%** | **5.26%** (2/38) | **15 (5.43%)** |
| `t000-stub` | stub provider, answers `met` to everything | 74.16% | 0.0 | 276 (100%) |

### The model lost to the free baseline, and that is the result

Not a hedge — the numbers go the wrong way on both headline measures. The model scored **2.5 points
lower on accuracy** and made **twice as many false METs** (15 vs 7), which is the expensive error:
a breach shipped with a tick on it. Its only win was finding **2 of 38 breaches** where the baseline
found none — and it paid for those two with **22 false breach alarms** (precision 8.33%).

Where the 36 missed breaches went: **27 were called `never addressed`** and 9 were called `met`. The
model reliably noticed something was wrong and then misclassified *which kind* of wrong — which is
the one distinction the kit exists to draw. All 7 `Why Study Stopped` breaches were missed this way:
the model saw no such line and said "never addressed", never connecting *status = TERMINATED* to
*therefore this is required, so its absence is a breach*. That conditional is the reasoning the
rulebook demands.

Clean on the mechanical measures: **100% answered** (1,068/1,068), **100% quote fidelity** — every
line it cited genuinely exists in the document — and 0 unparseable replies.

### What this run does and does not license you to say

- **It does not show that "LLMs cannot do compliance checking."** It is one model, at one tier, on
  one corpus, in **one configuration** — and that configuration matters: `--no-thinking` was passed,
  so the model's reasoning was **disabled**. For a task whose hard cases are conditional
  (*this rule binds only if the trial was stopped*), that is a real handicap, and the honest reading
  is that this run has not yet tested the mode most likely to help. Reasoning was disabled because
  UC006 lost a whole run to a provider that reasons by default and burned its output ceiling; this
  kit's ceiling is the largest in the estate for exactly that reason, so it may well survive it.
- **It does show something worth knowing anyway**: that on this task a trivial string match is a
  genuinely hard baseline, that accuracy is the wrong headline, and that a checker can look 93%
  correct while finding 5% of what you bought it for.

`--no-thinking` is recorded as a guard on the run record, so this run forms its own series and
nothing may be differenced against a reasoning-on run.

## The gold verdicts cannot drift from the documents

Nothing is hand-labelled. Every verdict is computed from the **structured record** — the same record
the document text is rendered from — so the text and the label come from one source by construction.
`tools/build_corpus.py::_verify()` then fails the build if:

- a `met` or `breached` verdict quotes a line that is not in its document, or
- a `never_addressed` verdict quotes anything at all, or its element *does* have a line.

A **breach by omission** still points at the document — it quotes the line that creates the
obligation (`Overall Recruitment Status: TERMINATED`), because a finding a reader cannot locate is
not a finding.

## Where `breached` comes from — the regulation's own words, never a house rule

| rule | the sentence it rests on |
|---|---|
| Why Study Stopped | §11.10(b): *"for a clinical trial that is suspended or terminated or withdrawn prior to its planned completion"* — so on a terminated record, absence is a breach; on a completed one the rule does not apply at all. |
| Enrollment | §11.10(b): *"Once the trial has reached the primary completion date, the responsible party must update the Enrollment data element to reflect the actual number"* — an estimated count past that date is a breach. |
| Responsible Party | §11.28(a)(2)(iii)(B) names the element *"Responsible Party, **by Official Title**"* — an individual investigator named with no official title has addressed the element and failed its form. |
| Facility Information | §11.10(b): *"(i) Facility Name… (ii) Facility Location…"* — a site listed by city with no organisation name fails part (i). |

A fifth candidate — "primary outcome stated without a time frame" — was **dropped**, because the
time frame is required by the ClinicalTrials.gov data dictionary and not by Part 11. A kit that
quietly promotes a house rule to a federal one is lying about what it checks.

## The corpus is this kit's own, and that was a correction

Reusing `docs-verify`'s 20 documents was proposed, approved, and then measured: 6 candidate rules
were satisfied by all 20 and 7 by none, and only 2 discriminated. The cause was that kit's
`overallStatus=COMPLETED` filter, which turns `Why Study Stopped` into a constant. This kit pulls
across six statuses instead. The full measurement is in [`docs/CORPUS.md`](docs/CORPUS.md).

## Layout

```
data/rulebook.json     41 rules, parsed from the eCFR — never typed
data/corpus/*.txt      30 registration records, public domain (see corpus/SOURCES.md)
data/gold.jsonl        1,230 gold verdicts, derived mechanically
src/prompt.py          the verdict vocabulary, declared ONCE, read by everything
src/comply.py          the AI layer: load rules, one call, check the quotes
src/app.py             the local UI (port 8771)
evals/judge.py         pure-code scoring. No LLM judge, and no single accuracy headline
evals/baseline.py      the free baseline that scores 96% and finds nothing
tools/build_rulebook.py  transcribes the regulation
tools/build_corpus.py    renders the documents and derives the gold verdicts
```

MIT, like every kit here.
