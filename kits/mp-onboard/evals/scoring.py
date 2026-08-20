"""Score a set of predicted applications against gold. Pure code, shared by evals/baseline.py and
evals/run.py so the free floor and the real run are graded by the identical function -- a baseline
and a model scored by two different scorers cannot be compared honestly.

Three things are scored, kept separate, never folded into one accuracy number -- same discipline
every sibling kit's scoring.py states for its own scorer:

    per_field                 all seven field pairs, 3-way (match/mismatch/mismatch_explained),
                              scored independently, every application, every field.
    missed_banking_mismatch   THE metric this kit exists to measure -- see below.
    over_explained            the opposite-direction error, its own named metric, distinct from
                              missed_banking_mismatch.

⚑ `missed_banking_mismatch` IS THE EXPENSIVE-DIRECTION ERROR -- same discipline as fin-payrun's
`false_paid` and fin-invval's `false_fully_explained`. The denominator is exactly the corpus's
planted trap set (see data/SOURCES.md): applications where `bank_routing_number` is gold
`mismatch` and all six other fields are gold `match` -- an application that looks completely
clean apart from the one banking detail. A prediction counts as a miss if the model's own
`bank_routing_number` flag is anything other than `mismatch`: calling it `match` under-weighs the
one field that actually disagreed on an otherwise spotless application; calling it
`mismatch_explained` is the over-explaining error counted separately below, and it is ALSO a miss
here, because either way the model failed to raise an unexplained banking discrepancy for the
analyst.

⚑ `over_explained` IS THE OTHER DIRECTION, COUNTED ACROSS ALL SEVEN FIELDS, NOT ONLY BANKING. Its
denominator is every (application, field) cell where gold is `mismatch` -- a real, unexplained
discrepancy the applicant's own submission_note does not cover. A prediction counts as
over-explaining that cell if the model calls it `mismatch_explained` -- reading an absent or
unrelated note as covering a discrepancy it never mentions. This is the natural failure mode of a
reader that treats "a note is present" as "the note explains whatever looks off", rather than
checking the note actually names the field in question.

`could_not_verify`-worthy gaps -- a document too degraded to read, a field neither side states --
are left for the capture step; this corpus's every field is always populated by construction (see
data/SOURCES.md), so nothing here needs a fourth flag yet.
"""
from collections import Counter

FIELDS = ("business_name", "business_address", "tax_id", "bank_account_name",
         "bank_routing_number", "owner_name", "owner_address")
FLAGS = ("match", "mismatch", "mismatch_explained")


def score(records, gold):
    per_field = {f: Counter() for f in FIELDS}
    per_field_gold_total = {f: 0 for f in FIELDS}

    scored = 0
    field_answered = 0
    field_correct = 0

    trap_total = 0
    missed_banking = 0

    unexplained_total = 0
    over_explained = 0

    for rec in records:
        g = gold.get(rec["application_id"])
        if not g:
            continue
        scored += 1

        for f in FIELDS:
            gold_flag = g[f]
            per_field_gold_total[f] += 1
            pred_flag = rec.get(f)
            if pred_flag is not None:
                field_answered += 1
                if pred_flag == gold_flag:
                    field_correct += 1
                    per_field[f]["correct"] += 1

            if gold_flag == "mismatch":
                unexplained_total += 1
                if pred_flag == "mismatch_explained":
                    over_explained += 1

        if g.get("trap"):
            trap_total += 1
            if rec.get("bank_routing_number") != "mismatch":
                missed_banking += 1

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    overall = {
        "applications_scored": scored,
        "field_cells_total": scored * len(FIELDS),
        "field_answered": field_answered,
        "field_answered_pct": pct(field_answered, scored * len(FIELDS)),
        "field_accuracy_pct": pct(field_correct, field_answered),
        "missed_banking_mismatch": missed_banking,
        "missed_banking_mismatch_denominator": trap_total,
        "missed_banking_mismatch_rate_pct": pct(missed_banking, trap_total),
        "over_explained": over_explained,
        "over_explained_denominator": unexplained_total,
        "over_explained_rate_pct": pct(over_explained, unexplained_total),
    }

    per_field_out = {}
    for f in FIELDS:
        total = per_field_gold_total[f]
        correct = per_field[f].get("correct", 0)
        per_field_out[f] = {"gold_total": total, "correct": correct,
                            "accuracy_pct": pct(correct, total)}

    return {"overall": overall, "per_field": per_field_out}
