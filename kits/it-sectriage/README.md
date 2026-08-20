# it-sectriage — security alert triage and phishing report handling

One case window — 2 to 4 security alerts a SOC already bundled together because they occurred
close in time and/or share an entity — one model call, a disposition for every alert, a correlated
incident grouping, and a containment recommendation drafted for a named analyst to approve. The
job is not just classification: two alerts can each be individually correct and still get the
window wrong if they are merged into one incident that never happened, or split when they should
have been one.

```bash
python -m src.app                                   # the local UI on http://127.0.0.1:8792

# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python tools/build_corpus.py --verify                 # free. gold re-derived from the corpus, 0 drift.
python -m evals.baseline                              # free. no key, no spend.
python -m evals.run --run-id t000 --stub              # free. proves the wiring end to end.
python -m evals.run --run-id r001-<model>              # THIS SPENDS: 33 calls, one per case window.
```

## What this kit never does

It never locks an account, blocks mail flow, or isolates an endpoint. Every containment
recommendation is drafted text, addressed to the case window's named on-call analyst, and it is
that person who reviews, approves and executes it. If you are looking for the line that enforces
this, there isn't one function to point at — there is no function anywhere in `src/triage.py`,
`src/app.py` or the UI that performs a containment action. Every enrichment cites the specific
indicator that justifies it; `evals/scoring.py`'s `citation_validity` checks that the citation
names an indicator that actually exists on an alert in that case, never a fabricated one.

## The mechanic: classify, then correlate, then recommend — in one call

Every alert carries an id, a type (`phishing_report`, `suspicious_login`, `malware_detection`,
`data_exfil_alert`, `brute_force`), a short raw description, a timestamp, an entity (a user or a
host), and 2-4 named indicators. One call reads the whole window and returns three things:

1. **`alert_dispositions`** — `true_positive` or `false_positive` for every alert, judged on its
   own evidence.
2. **`case_groups`** — which of the true positives are genuinely the SAME incident. A false
   positive never appears in any group; a true positive with no genuine partner is its own case,
   alone.
3. **`recommendations`** — one short containment draft per case, citing the indicator(s) that
   justify it, in `name=value` form so the citation can be checked by exact lookup rather than by
   asking a second model whether it sounds plausible.

`case_groups` in the gold data is **derived, never hand-typed**: every alert is tagged at
generation time with a disposition and a `case_id`, and one function
(`derive_gold()` in `tools/build_corpus.py`) turns those per-alert facts into the aggregate
grouping — the same function used both to write `data/gold.jsonl` and, independently, by
`tools/build_corpus.py --verify` to re-check every row against the corpus actually on disk.

## The two failure modes this kit exists to catch

**Missing a true-positive phishing report.** A real phishing report often reads as a calm "is
this legit?" rather than an alarm. `evals/scoring.py`'s `missed_true_positive` counts every gold
true positive the model called false_positive, reported overall AND, on its own, over the 3
deliberately mundane-worded phishing reports named in `data/SOURCES.md` — a keyword-only reader
has nothing alarming to catch in "wants to know if it's legitimate before clicking anything."

**Correlating unrelated events into a false single case.** Two alerts that share an entity, a
close timestamp, or one coincidental indicator value (most often, in this corpus, the same
building's or VPN concentrator's shared egress IP) are not necessarily one incident.
`evals/scoring.py`'s `false_correlation` counts every PAIR of alerts gold keeps in different cases
(or one case and no case) that the model puts in the same case — scored over pairs rather than
whole groups, because a partial merge inside a larger group is still a false correlation for every
pair it touches, even when the group as a whole isn't wrong. Reported overall AND, on its own, over
the 8 windows in `data/SOURCES.md` built specifically to tempt this mistake.

Neither is adversarial text. Nothing in any alert is written to deceive — a mundane phishing report
is exactly what a real one often reads like, and a shared IP address really is how two unrelated
users behind the same building end up looking connected. That is the whole reason both are worth
measuring rather than assuming a model handles them.

## What was measured

One run, `r001-it-sectriage`, on 2026-08-20 — 33 case windows, 82 alerts, one model call per
window, 0 failures. Scored by `evals/scoring.py`, which is pure code; the free floor below is
scored by the identical function.

| | this run | free floor (`evals/baseline.py`) |
|---|---|---|
| disposition answered | 82 of 82 (100.0%) | 82 of 82 (100.0%) |
| disposition accuracy | **100.0%** | 69.5% |
| missed true positive | **0 of 52 (0.0%)** | 4 of 52 (7.7%) |
| &nbsp;&nbsp;— on the 3 planted mundane-phishing alerts | **0 of 3 (0.0%)** | 2 of 3 (66.7%) |
| false correlation | **0 of 47 pairs (0.0%)** | 19 of 47 (40.4%) |
| &nbsp;&nbsp;— on the 8 planted trap pairs | **0 of 8 (0.0%)** | **8 of 8 (100.0%)** |
| citation validity | **109 of 109 (100.0%)** | n/a — drafts no recommendations |

32,892 input / 54,550 output tokens over the 33 calls. Latency p50 9,758 ms, p95 47,346 ms,
486.2 s wall.

**Read the 100%s with the corpus in mind.** This is one run of one model over a corpus that was
written here and contains exactly the two planted traps and no others. It is not a distribution,
there is no second model to compare against, and no red-team run was fired. What the table does
show is **separability**: the free floor falls into the correlation trap on 8 of 8 pairs, so the
corpus discriminates, and a result of 0 is a real pass rather than a task nothing could fail.

### The `MAX_TOKENS` finding — this run took three attempts, and the first two lied

The published run is the third. The first two produced plausible-looking failure rates that were
**truncation artifacts, not model failures**:

| `MAX_TOKENS` | calls cut off (`finish_reason="length"`) | what the scorer then reported |
|---|---|---|
| 3000 | 7 of 33 | "34.6% missed true positive" — but only 61 of 82 alerts were answered at all |
| 4096 | 5 of 33 | still an inflated missed-true-positive rate, same cause |
| **8192** | **0 of 33** | the real answer: 0.0% |

The tell was in the same file the whole time: at 3000 the disposition **accuracy on what was
answered was already 100%**. The model was never wrong, it was running out of budget mid-reply, and
a scorer that counts an unanswered alert as a miss reports that as a model failure.

**Why this workload needs a ceiling its sibling kits do not.** Reasoning is left at the provider's
default (on) here, and reasoning tokens are billed and bounded as completion tokens. Across the 33
published calls, `reasoning_chars` totals 208,731 — roughly **95.7% of the 54,550 output tokens are
the reasoning pass**, not the JSON answer. Output ran 105–5,442 tokens per call (a 52× spread)
while input stayed essentially flat at 932–1,161. Correlating 2–4 alerts against each other is
simply heavier reasoning than a per-record judgement, which is why a 3000 ceiling that is
comfortable for a sibling kit truncates here. The peak call used 5,442 of the 8,192 available, so
the shipped ceiling has real headroom above the observed maximum rather than sitting just past it.

Only the 3000 attempt was archived while debugging; it was deleted rather than committed, because a
stale contaminated result file next to a good one is a trap for the next reader. The finding lives
here and in `src/prompt.py`'s `MAX_TOKENS` comment.

## What it cannot do, stated up front

- **Indicator coverage varies by which security tools are actually integrated.** An alert from a
  tool this deployment has no feed for arrives with fewer indicators, or none, and this kit cannot
  tell "nothing to cite" apart from "the tool never reported it" — see `data/SOURCES.md`.
- **The case-window boundary is authored, not computed.** Which alerts get bundled into one
  2-4-alert candidate group in the first place is a real, operator-tuned entity/time correlation
  window upstream of this kit. Too loose over-merges before a model ever sees the alerts; too
  tight splits one real incident across two windows that are never compared side by side. Nothing
  here measures that upstream choice.
- **Every window carries at most one of the two named traps**, to keep each failure mode legible
  on its own; a real SOC queue can carry both kinds of trouble in the same bundle at once.

## The gold labels cannot drift from the alert data

Nothing is hand-labelled. Every alert is tagged with a disposition and a `case_id` at construction
time, and `derive_gold()` in `tools/build_corpus.py` computes `alert_dispositions` and
`case_groups` from those per-alert facts by one grouping rule — used both to write
`data/gold.jsonl` at generation time and, independently, by `--verify`, which re-reads
`data/windows.jsonl` and `data/gold.jsonl` from disk and asserts: every alert a window carries is
named in that window's gold facts (no more, no fewer); `derive_gold()` re-run over those facts
matches the written `alert_dispositions` and `case_groups` exactly; no false positive appears in
any case group; and every planted false-correlation `trap_pair` is genuinely gold-separate. See
[`data/SOURCES.md`](data/SOURCES.md) for the full corpus design, the trap windows named
individually, and its limits.

## Layout

```
data/windows.jsonl         33 case windows, 82 alerts total -- everything the model is shown
data/gold.jsonl             33 gold rows: alert_facts, alert_dispositions, case_groups, trap flags
data/SOURCES.md              why the corpus is synthetic, the trap design, and exactly which windows carry which trap
src/prompt.py                 the output schema and the one system prompt, declared ONCE
src/triage.py                  the AI layer: one call, parse the field set
src/app.py                      the local UI (port 8792)
src/config.py, src/budget.py, src/adapters/  shared plumbing, identical across every kit in this repo
evals/scoring.py                pure-code scoring: disposition accuracy, missed_true_positive, false_correlation, citation_validity
evals/baseline.py                the free keyword-and-shared-indicator floor, honestly narrow
evals/run.py                      the real eval harness, plus --stub for a $0.00 wiring check
tools/build_corpus.py              builds windows + alerts, derives gold, --verify re-checks it against disk
```

MIT, like every kit here.
