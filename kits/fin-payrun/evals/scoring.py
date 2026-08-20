"""Score a set of predicted invoice traces against gold. Pure code, shared by evals/baseline.py
and evals/run.py so the free floor and the real run are graded by the identical function -- a
baseline and a model scored by two different scorers cannot be compared honestly.

Four things are scored, kept separate, never folded into one accuracy number -- same discipline
fin-close's scoring.py and fin-invval's scoring.py both state for their own scorers:

    current_stage          the core 5-way classification.
    requires_ap_review     its own field, even though it is derived deterministically from
                            current_stage in gold -- the extraction contract scores fields
                            independently, and a model can get the stage right and the boolean
                            wrong (or vice versa) if it does not actually apply the derivation.
    false_paid             THE metric this kit exists to measure -- see below.
    date_accuracy          does the reply's stated date match the one real date the record
                            supports, or correctly state none?

⚑ `false_paid` IS THE EXPENSIVE-DIRECTION ERROR, COUNTED ON ITS OWN AND WEIGHTED LIKE ONE --
same discipline as fin-close's `false_clean` and fin-invval's `false_fully_explained`. Telling a
vendor an invoice is paid when it is actually held in an open match or approval exception is the
one failure this kit was built to catch. The denominator is exactly the corpus's planted trap set
where the trap field is remittance -- see `data/gold.jsonl`'s `trap` / `trap_field` /
`downstream_paid_looking` and `data/SOURCES.md`. A prediction counts as a false paid claim if
EITHER the model's `current_stage` is `remitted` OR its drafted reply text itself claims payment
happened or is imminent -- catching the second case is why this is not simply
`current_stage == "remitted"` compared to gold: a model that gets the field right but still writes
"this has been paid" in the reply has produced exactly the vendor-facing harm the guardrail exists
to prevent.
"""
import re
from collections import Counter

STAGES = ("match_exception", "approval_exception", "awaiting_run_inclusion", "in_scheduled_run",
          "remitted")

# ⚠︎ A SIMPLE KEYWORD SCAN, NOT A JUDGE. This is pure code checking whether the drafted reply
# asserts payment in plain terms -- it is deliberately narrow rather than clever, the same way
# evals/baseline.py's regexes are deliberately narrow. A phrase this does not catch is a gap in
# the scorer worth widening later, not a reason to add an LLM judge to a kit that does not need
# one for this check.
_PAID_CLAIM_RE = re.compile(
    r"\b(has been paid|was paid|has gone out|went out|already paid|payment (?:has|is) (?:gone|"
    r"going) out|successfully remitted|payment (?:has been|was) sent|payment (?:has been|was) "
    r"processed)\b", re.IGNORECASE)


def _reply_claims_paid(reply):
    return bool(reply) and bool(_PAID_CLAIM_RE.search(reply))


def score(records, gold):
    stage_matrix = Counter()                          # (gold_stage, pred_stage) -> count
    per_stage = {s: Counter() for s in STAGES}
    per_stage_gold_total = {s: 0 for s in STAGES}

    scored = 0
    stage_answered = 0
    stage_correct = 0

    review_answered = 0
    review_correct = 0

    trap_total = 0
    false_paid = 0

    date_scoreable = 0
    date_correct = 0

    for rec in records:
        g = gold.get(rec["invoice_id"])
        if not g:
            continue
        scored += 1
        per_stage_gold_total[g["current_stage"]] += 1

        pred_stage = rec.get("current_stage")
        if pred_stage is not None:
            stage_answered += 1
            stage_matrix[(g["current_stage"], pred_stage)] += 1
            per_stage[g["current_stage"]][pred_stage] += 1
            if pred_stage == g["current_stage"]:
                stage_correct += 1
                per_stage[g["current_stage"]]["correct"] += 1

        pred_review = rec.get("requires_ap_review")
        if isinstance(pred_review, bool):
            review_answered += 1
            if pred_review == g["requires_ap_review"]:
                review_correct += 1

        if g.get("trap") and g.get("trap_field") == "remittance":
            trap_total += 1
            claims_paid = pred_stage == "remitted" or _reply_claims_paid(rec.get("reply"))
            if claims_paid:
                false_paid += 1

        expected_date = g["expected_date"]
        pred_date = rec.get("stated_date")
        # Scoreable whenever the model answered SOMETHING for this field -- a stage with no real
        # date (an exception, or awaiting run inclusion) is scored correct when the model
        # correctly states none, same as fin-close treats a correctly-empty citation as an answer
        # rather than a non-answer.
        if "stated_date" in rec:
            date_scoreable += 1
            if pred_date == expected_date:
                date_correct += 1

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    overall = {
        "invoices_scored": scored,
        "stage_answered": stage_answered,
        "stage_answered_pct": pct(stage_answered, scored),
        "stage_accuracy_pct": pct(stage_correct, stage_answered),
        "review_answered": review_answered,
        "review_accuracy_pct": pct(review_correct, review_answered),
        "false_paid": false_paid,
        "false_paid_denominator": trap_total,
        "false_paid_rate_pct": pct(false_paid, trap_total),
        "date_scored": date_scoreable,
        "date_accuracy_pct": pct(date_correct, date_scoreable),
    }

    per_stage_out = {}
    for s in STAGES:
        total = per_stage_gold_total[s]
        correct = per_stage[s].get("correct", 0)
        per_stage_out[s] = {"gold_total": total, "correct": correct,
                            "accuracy_pct": pct(correct, total)}

    return {"overall": overall, "per_stage": per_stage_out,
           "matrix": {"%s->%s" % k: v for k, v in stage_matrix.items()}}
