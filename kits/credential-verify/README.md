# credential-verify — reconcile a provider credentialing file and flag it for review

**UC034.** Point it at a provider credentialing file, get a field table back, plus one number
computed afterwards in pure code: whether the file needs credentialing-committee review because
the license is expired, the PSV check is stale, or an adverse action was found — however mildly
worded. The computed flag is never a credentialing or network-participation determination — it is
a routing signal for a person to check.

MIT. Python standard library plus a minimal JS UI. One model, one key, run once per model.

```bash
python -m evals.check_labels                          # free — validates the gold set
python -m evals.run --run-id b000-rules --baseline    # free — the severe-keyword extractor
python -m evals.run --run-id t000-stub --stub         # free — proves the wiring end to end
# provider/key: configure ONCE at the repo root -- ../../.env -- not per kit
python -m evals.run --run-id r001-<model>             # THIS SPENDS MONEY: one call per file
python -m src.app                                      # the local UI on 127.0.0.1:8768
```

## The guardrail: a mild word is still an adverse action

The measurable failure this kit exists to catch is not a missing field — it is an adverse action
getting waved through as clean because it reads gently, often beside reassuring language like
"otherwise active and in good standing" in the very same sentence. `sanction_or_adverse_action_
found` is `yes` whenever the PSV finding names ANY adverse action against the provider — a
reprimand, consent order, letter of concern, restriction, suspension, revocation or exclusion —
however mildly it is worded. Only a finding with no adverse action of any kind is `no`. See
[data/SOURCES.md](data/SOURCES.md) for the planted ambiguity this corpus tests.

Three checks run downstream, in pure code (`src/extract.py::compute`), never authored from intent
and never a judgment call the model makes:

| | rule | not a real accreditation body's published standard |
|---|---|---|
| `license_expired` | the license's own expiration date is before the credentialing effective date | a plain date comparison, no policy involved |
| `psv_stale` | the PSV check happened more than `PSV_LOOKBACK_DAYS = 180` days before the effective date | this kit's own flat window, stated plainly so nobody mistakes it for 42 CFR 438.214's actual requirement |
| `sanction_or_adverse_action_found` | the model's own extracted value, passed through | the one judgment call in the pipeline, and the one this README's guardrail is about |

`needs_review` is `True` if ANY of the three fires. No configuration, no model vote on the routing
decision itself — only on whether an adverse action was found in the first place.

## What it measures, and the number that matters most

Two models, same 55-file corpus, same judge, same guardrail rule — see the committed run records
in `results/` for the exact figures (`eval-r001-deepseek-v4-flash.json`,
`eval-r002-deepseek-v4-pro.json`).

**Recall on the review flag is the figure this kit exists to publish** — of every file that should
route to the credentialing committee (an expired license, a stale PSV check, or any adverse
action, however mild), how many actually got flagged. Both tiers hit 100% extraction accuracy
(550 of 550 cells) and 1.0 recall and precision on the review flag — the cleanest run of this
four-kit series so far, with zero errors of any kind on either tier. That is also a small sample
for a rule this consequential; see `Business.not_good_enough` on the published kit page. This
kit's own tier gap is the smallest measured in the series: the fast tier runs $0.0012911/query
against the deliberating tier's $0.0013347/query, about 5% more output tokens for roughly 70%
higher latency and no measurable accuracy difference.

## The baseline is shipped, including where it wins and where the gap actually is

`--baseline` is a non-LLM extractor: rules and regexes, no key, no cost. It scores well on the
nine structured fields — a fixed file layout is mostly regex work, landing at 96.91% extraction
accuracy. **The gap is entirely in `sanction_or_adverse_action_found`**, where the baseline is a
deliberate severe-keyword floor (`revoked`, `suspended`, `excluded`, `disciplinary hearing` — see
`evals/baseline.py`) that fails the planted ambiguity by construction: it scores 65.71% flag
recall, missing 12 of the 35 files that should have been flagged. Every one of those 12 misses is
a mild-worded adverse action — a "public reprimand," a "consent order," a "letter of concern" —
that never says one of the four severe words the floor checks for, even though the file's own
facet sheet treats it as requiring committee review regardless of severity.

## There is no LLM judge in this kit

The gold is exact and an answer is one value, so `==` (with light normalisation) settles it —
adding an LLM judge would add cost and a second source of disagreement to a comparison that does
not need one.

## The four layers

| layer | where |
|---|---|
| minimal UI | `src/app.py`, `ui/` — one file, one call, on your machine |
| pipeline | `src/segment.py` (addressable sections) → `src/select.py` (which sections per field) |
| AI layer | `src/prompt.py`, `src/extract.py`, `src/adapters/` — one provider, one key |
| eval layer | `evals/run.py`, `evals/judge.py`, `evals/baseline.py`, `evals/check_labels.py` |

`src/select.py` exists for the same reason it exists in every sibling extraction kit here:
sending ten fields × the whole file is ten times the input tokens of sending each field the
section that could possibly state it. **The bill is driven by the context, not by the question.**

## Point it at your own credentialing files

Replace `data/corpus/*.txt`, write your own `data/fields.json`, and provide a gold record per
file. `SECTION_HINTS` in `src/select.py` maps fields to section headings and **will** need
editing for a different file layout; when it does not match, selection falls back to the whole
document — slower, more expensive, always correct. `PSV_LOOKBACK_DAYS` in `src/extract.py` is
this kit's own stated policy, not 42 CFR 438.214's actual Medicaid managed-care requirement or any
other accreditation body's published lookback window — replace it with your own program's actual
standard before trusting the computed flag for anything real.

## What it does not do

Reads one credentialing file at a time and never cross-references a second, corroborating PSV
source — a real credentialing review often checks more than one primary source, and this kit's
review-flag determination comes from the one PSV finding stated on the file alone. It never makes
the credentialing or network-participation determination itself — it reconciles the file and
flags discrepancies for the credentialing committee or specialist to decide. `PSV_LOOKBACK_DAYS`
is this kit's own simplification and does not model how real lookback windows vary by segment and
element. No OCR — scanned or image-only files extract no text. No auth, no database, no
multi-tenancy, no deployment story. It runs once per model, locally, and that run is what gets
published.
