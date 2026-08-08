# Reasoning is OFF in this kit, and that is a measurement, not a preference

Every scored run here — `r001` on `deepseek-v4-flash`, `r003` on `deepseek-v4-pro` — sends
`thinking: {"type": "disabled"}`. This file records why, because "we turned the model's reasoning
off and then reported that it reasons poorly about conditional rules" is a fair objection and it
deserves a measured answer rather than a footnote.

## The objection

`r001`'s headline is that a free string match beats the model. Its most interesting failure is that
of 36 missed breaches, 27 were called `never addressed` — the model saw something was wrong and
misclassified *which kind* of wrong. All 7 `Why Study Stopped` breaches went that way: it never
connected *status = TERMINATED* to *therefore this element is required, so its absence is a breach*.

That is a conditional-reasoning failure, and the run had reasoning disabled. So the obvious next
experiment is to turn it on.

## What was actually run

**`p002-docs-comply-thinking-probe` — 2 documents, provider default (reasoning ON), 2026-08-08.**

Nothing else changed: same corpus, same rulebook edition, same prompt, same `MAX_TOKENS = 6000`.

| document | finish_reason | output_tokens | reply |
|---|---|---|---|
| `NCT00005110` | `length` | **6000 of 6000** | **empty** |
| `NCT00008775` | `length` | **6000 of 6000** | **empty** |

Both calls spent the **entire output ceiling on hidden reasoning and returned no text at all.**
0 of 82 rule-checks answered. This is not a worse score; it is **no score** — the model never
emitted a verdict.

## Why the ceiling did not save it

6000 is the largest `MAX_TOKENS` in this estate, and it was chosen deliberately: 41 rules must come
back in one reply, so this kit already asks for far more output than its siblings. The expectation
recorded before the probe was that it might therefore *survive* reasoning on where `docs-redact`
had not. It did not. `docs-redact`'s r001 failed the same way at a ceiling of 800
(`token_details: {"reasoning_tokens": 800}`), and raising the ceiling by 7.5× did not change the
outcome — the reasoning pass expands to fill whatever it is given, because it is reasoning about
41 rules rather than one.

## What this does and does not license

- **It does license** disabling reasoning on this task with this provider. At the ceiling this kit
  can afford, reasoning-on returns nothing, and nothing is not a comparison.
- **It does NOT license** "LLMs cannot do compliance checking", and it does not close the
  conditional-reasoning question. The honest statement is that **this kit has not measured a
  reasoning-on model**, and that is what `Eval.could_not_verify` says.
- Closing it properly needs a ceiling large enough to hold a full reasoning pass *plus* 41
  verdicts, which is a different cost question and a different run — **not** a re-try of this one.

## The probe is not in the run history, on purpose

Extracting it wrote `false_met: 0, false_alarm: 0, breached_recall_pct: 0.0` into a run record —
a run that answered **nothing** recorded as perfect on the expensive error. `build/measured/runlog.py`
now refuses any run that answered 0%, and re-adding the probe to its registry makes `--rebuild`
fail deliberately. A zero you earned and a zero you got because nothing came back are different
facts and must not share a cell.

## The field that should have said all this read null

`src/comply.py` recorded `reasoning_tokens` by reading `res["reasoning_tokens"]` — a key the
adapter has never returned. It reports the provider's `completion_tokens_details` dict under
`token_details`. So the field was null on every record this kit ever wrote, and null looks like a
plausible answer to "how much reasoning happened" on a run that disabled reasoning. It went
unnoticed until the one run where the answer mattered. Fixed 2026-08-08.

⚠︎ **`r003` does not demonstrate the fix and cannot.** It disabled reasoning, so the provider
returns no `completion_tokens_details` at all and the field is legitimately **absent** — which is
the third state this kit keeps distinct from a zero, not evidence of anything. The fix is proved
instead against a fake provider that returns the dict, which is free and does not need a run:

```python
# reasoning_tokens -> 777, read from token_details rather than a key that never existed
```

The provider value will first appear in a real record on whatever run next leaves reasoning on —
and per the section above, that run needs a bigger ceiling than this one has.
