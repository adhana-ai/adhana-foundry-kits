"""Score a run against the labelled claim set. PURE CODE — there is no LLM judge in this kit.

⚠︎ AND THAT IS A DELIBERATE CHOICE, NOT AN OMISSION. UC001 and UC003 grade with a model because
their outputs are free text and no exact rule can say whether an answer is right. This kit's
output is one of three enum values per claim, against a label that was derived mechanically from
the source record. A model asked to grade that would add cost, latency and its own error rate to a
comparison that `==` already decides correctly. The kit standard wants the evaluation method to be
pluggable; pluggable includes choosing the cheap deterministic one when it is the right one.

WHAT IS ACTUALLY MEASURED, and why accuracy alone would be a bad headline:

  accuracy          all three classes, one number. Useful, and hides everything below.
  the 3x3 matrix    which class gets confused for which. This is the finding.
  not_stated recall THE metric for this kit. A model that never says not_stated looks fine on
                    accuracy (the class is 23% of the set) and is useless in production, because
                    every hallucination it was bought to catch comes back marked contradicted or
                    supported.
  false support     a claim the document does NOT support, called supported. The costly error:
                    it is the one that lets a wrong claim through with a confident tick.
  quote fidelity    of the verdicts that cited a sentence, how many cited one the document really
                    contains. Pure code, free, and it catches a model inventing its own evidence.
  answered          how many claims got any verdict at all. A model that returns nothing for half
                    the set has not scored 100% on the half it managed.
"""
LABELS = ("supported", "contradicted", "not_stated")


def _pct(n, d):
    return round(100.0 * n / d, 2) if d else None


def score(records, labelled):
    """`records` is [{doc, claims:[{id, verdict, quote_in_doc}]}]; `labelled` maps doc -> claims."""
    matrix = {t: {p: 0 for p in LABELS} for t in LABELS}
    unanswered = {t: 0 for t in LABELS}
    total = answered = correct = 0
    quoted = quoted_real = 0

    for rec in records:
        gold = {c["id"]: c["label"] for c in labelled.get(rec["doc"], [])}
        for row in rec["claims"]:
            truth = gold.get(row["id"])
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
            # Recall is over ALL gold rows including unanswered ones. A claim the model never
            # returned a verdict for is a claim it did not catch, whatever the reason.
            "recall_pct": _pct(tp, gold_n),
            "precision_pct": _pct(tp, pred_n),
        }

    # The costly error, named separately because "accuracy" buries it: the document does not
    # support this claim, and the model said it did.
    false_support = matrix["contradicted"]["supported"] + matrix["not_stated"]["supported"]
    unsupported_gold = (sum(matrix["contradicted"].values()) + unanswered["contradicted"]
                        + sum(matrix["not_stated"].values()) + unanswered["not_stated"])

    return {
        "overall": {
            "claims": total,
            "answered": answered,
            "unanswered": total - answered,
            "answered_pct": _pct(answered, total),
            # Accuracy is over ANSWERED claims and says so in its name, with coverage beside it.
            # One number that silently mixes "got it wrong" and "never replied" is the number that
            # lets a half-broken run look respectable.
            "accuracy_answered_pct": _pct(correct, answered),
            "accuracy_all_pct": _pct(correct, total),
            "false_support": false_support,
            "false_support_rate_pct": _pct(false_support, unsupported_gold),
            "quotes_offered": quoted,
            "quotes_found_in_doc": quoted_real,
            "quote_fidelity_pct": _pct(quoted_real, quoted),
        },
        "per_class": per_class,
        "matrix": matrix,
        "unanswered_by_class": unanswered,
    }
