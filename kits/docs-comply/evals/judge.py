"""Score a run against the gold verdicts. PURE CODE — there is no LLM judge in this kit.

⚠︎ AND THAT IS A DELIBERATE CHOICE, NOT AN OMISSION. UC001 and UC003 grade with a model because
their outputs are free text and no exact rule can say whether an answer is right. This kit's output
is one of three enum values per rule, against a gold verdict derived mechanically from the source
record. A model asked to grade that would add cost, latency and its own error rate to a comparison
that `==` already decides correctly. The kit standard wants the evaluation method to be pluggable;
pluggable includes choosing the cheap deterministic one when it is the right one.

⚠︎ THERE IS NO SINGLE ACCURACY HEADLINE, AND THAT IS THE POINT OF THIS FILE. On this corpus `met`
is 74.2% of applicable rules, so a checker that answers "met" to everything scores 74.2% and has
found nothing. Any figure that can be reached by refusing to think is not a measurement of
thinking. `baseline.py` computes that number on every run so it is always printed beside the
model's, and the two are meant to be read together.

WHAT IS ACTUALLY MEASURED:

  the 3x3 matrix      which verdict gets confused for which. This is the finding.
  breached recall     THE metric for this kit, and the hardest. Breach is 3.6% of applicable rules
                      because the registry enforces most elements at submission — so a model can
                      miss every breach and still look excellent on accuracy.
  never-addressed
    recall            the second metric. Silence is usually the finding in compliance: a required
                      disclosure never made. A checker that collapses it into `met` hides it.
  FALSE MET           the expensive error, named separately because accuracy buries it: a rule the
                      document breaches or never addresses, reported as satisfied. This ships a
                      breach with a tick on it, and nobody re-checks a rule the checker passed.
  quote fidelity      of the verdicts that cited a line, how many cited one the document really
                      contains. Pure code, free, and it catches a model inventing its evidence.
  answered            how many rules got any verdict at all. A model that returns nothing for a
                      third of the rulebook has not scored 100% on the two thirds it managed.

⚑ RULES THE REGULATION DOES NOT BIND ARE DROPPED BEFORE SCORING. The gold set carries a fourth
state, `not_applicable`, for rules whose own condition excludes a document — `Why Study Stopped` on
a trial that was never stopped, `Study Phase` on a trial that is not FDA-regulated. 162 of this
corpus's 1,230 rule-verdicts are in that state. Scoring them would hand out 13% of the marks for
rules nobody is obliged to satisfy.
"""
LABELS = ("met", "breached", "never_addressed")
NOT_APPLICABLE = "not_applicable"


def _pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def score(records, gold):
    """`records` is [{doc, rules:[{rule, verdict, quote_in_doc}]}]; `gold` maps doc -> gold row."""
    matrix = {t: {p: 0 for p in LABELS} for t in LABELS}
    unanswered = {t: 0 for t in LABELS}
    total = answered = correct = 0
    quoted = quoted_real = 0
    skipped_na = 0

    for rec in records:
        grow = gold.get(rec["doc"]) or {}
        truth_of = {v["rule"]: v["verdict"] for v in (grow.get("verdicts") or [])}
        for row in rec["rules"]:
            truth = truth_of.get(row["rule"])
            if truth == NOT_APPLICABLE:
                skipped_na += 1
                continue
            if truth not in LABELS:
                continue
            total += 1
            got = row.get("verdict")
            if got is None:
                # NEVER counted as a wrong prediction of some class — it is not a prediction.
                # Folding it into the matrix would blame a class the model never named.
                unanswered[truth] += 1
                continue
            answered += 1
            matrix[truth][got] += 1
            if truth == got:
                correct += 1
            if row.get("quote_in_doc") is not None:
                quoted += 1
                quoted_real += 1 if row["quote_in_doc"] else 0

    per_class = {}
    for c in LABELS:
        tp = matrix[c][c]
        gold_n = sum(matrix[c].values()) + unanswered[c]
        pred_n = sum(matrix[t][c] for t in LABELS)
        per_class[c] = {
            "gold": gold_n,
            "predicted": pred_n,
            "correct": tp,
            # Recall is over ALL gold rows including unanswered ones. A rule the model never
            # returned a verdict for is a rule it did not check, whatever the reason.
            "recall_pct": _pct(tp, gold_n),
            "precision_pct": _pct(tp, pred_n),
        }

    # THE EXPENSIVE ERROR, named separately because "accuracy" buries it: the document does not
    # satisfy this rule, and the model said it did.
    false_met = matrix["breached"]["met"] + matrix["never_addressed"]["met"]
    unmet_gold = (sum(matrix["breached"].values()) + unanswered["breached"]
                  + sum(matrix["never_addressed"].values()) + unanswered["never_addressed"])

    # The other direction, cheaper but not free: a rule the document DOES satisfy, reported as a
    # problem. This is what a reviewer experiences as a false alarm, and two of them are enough to
    # make someone stop reading the report.
    false_alarm = matrix["met"]["breached"] + matrix["met"]["never_addressed"]

    return {
        "overall": {
            "rules_scored": total,
            "skipped_not_applicable": skipped_na,
            "answered": answered,
            "unanswered": total - answered,
            "answered_pct": _pct(answered, total),
            # Accuracy is over ANSWERED rules and says so in its name, with coverage beside it.
            # One number that silently mixes "got it wrong" and "never replied" is the number that
            # lets a half-broken run look respectable.
            "accuracy_answered_pct": _pct(correct, answered),
            "accuracy_all_pct": _pct(correct, total),
            "false_met": false_met,
            "false_met_rate_pct": _pct(false_met, unmet_gold),
            "false_alarm": false_alarm,
            "false_alarm_rate_pct": _pct(false_alarm,
                                         sum(matrix["met"].values()) + unanswered["met"]),
            "quotes_offered": quoted,
            "quotes_found_in_doc": quoted_real,
            "quote_fidelity_pct": _pct(quoted_real, quoted),
        },
        "per_class": per_class,
        "matrix": matrix,
        "unanswered_by_class": unanswered,
    }
