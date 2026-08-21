"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Two graders, scored separately and never folded together:

1. per-(record, field) exact match, the extraction grade;
2. a confusion matrix on `conforms_to_spec` against gold's own conformance -- which gold got by
   the same arithmetic, from the same numbers the certificate states. NON-CONFORMING IS THE
   POSITIVE CLASS: a batch that is out of specification and gets called conforming is the failure
   a quality team actually cares about, so recall is reported on "no".

And one diagnostic that is not a grade at all: how often the run's own pure-code `needs_review`
fired -- the model's stated verdict disagreeing with its own extracted numbers -- and how many of
the verdict errors that self-consistency check would have caught WITHOUT any gold. That last figure
is the one this kit exists to publish, because it is the only one a forker can still compute on
documents nobody has labelled.
"""
import re

from src.extract import recompute_conformance as _recompute


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _num(v):
    m = re.search(r"-?\d+(\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else None


def equal(field, got, want):
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    if g == w:
        return True
    if field.get("type") in ("number", "integer"):
        gn, wn = _num(g), _num(w)
        return gn is not None and wn is not None and abs(gn - wn) < 0.005
    return False


def score(fields, records, golds):
    """⚠︎ A NULL IS A REAL ANSWER IN THIS CORPUS, not an abstention. A one-sided specification
    states no limit on one side, and gold records None there; a model that returns null is CORRECT
    and a model that invents a bound is wrong. So a cell is judged against gold first and only
    counted a `miss` when gold has a value the model did not return -- unlike the sibling kits,
    where every field is always stated and a null is always a miss."""
    by_field, cells = {}, []
    for stmt_id, rec in sorted(records.items()):
        g = golds.get(stmt_id) or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            want = g.get(name)
            if equal(f, got, want):
                v = "hit"
            elif norm(got) is None:
                v = "miss"
            else:
                v = "wrong"
            cells.append({"doc": stmt_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": want is not None,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    # A correctly-returned null has nothing to locate, so it is not counted against the span rate.
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": 0,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields if f.get("type") == "enum"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def score_flags(records, flags, golds):
    """The conformance verdict, scored against gold, plus the self-consistency diagnostic.

    records: {stmt_id: {field: {value,...}}} from the run.
    flags:   {stmt_id: needs_review_or_None} from the run's own pure code.
    golds:   {stmt_id: gold dict}. Gold's conformance is re-derived here by the SAME arithmetic
             the kit publishes, so the truth this grades against is never a separately-typed label
             that could drift from the rule.

    Positive class is "no" -- out of specification. Recall is therefore "of every batch that really
    is out of specification, how many did the run call out of specification".
    """
    tp = fp = tn = fn_ = unanswered = 0
    rows = []
    inconsistent = 0
    caught = missed = 0
    for stmt_id, g in sorted(golds.items()):
        want = _recompute(g.get("measured_value"), g.get("spec_lower_limit"),
                          g.get("spec_upper_limit"))
        rec = records.get(stmt_id) or {}
        got = (rec.get("conforms_to_spec") or {}).get("value")
        flagged = bool(flags.get(stmt_id))
        if flagged:
            inconsistent += 1
        correct = (got == want)
        if not correct:
            if flagged:
                caught += 1
            else:
                missed += 1
        # ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding a null verdict into "true
        # negative" would let a model that answers nothing score as a careful one.
        if got not in ("yes", "no"):
            unanswered += 1
            v = "unanswered"
        elif want == "no" and got == "no":
            tp += 1
            v = "true_positive"
        elif want == "no":
            fn_ += 1
            v = "false_negative"
        elif got == "no":
            fp += 1
            v = "false_positive"
        else:
            tn += 1
            v = "true_negative"
        rows.append({"doc": stmt_id, "want": want, "got": got, "verdict": v,
                     "needs_review": flagged})
    total_positive = sum(1 for r in rows if r["want"] == "no")
    n = len(golds) or 1
    return {
        "positive_class": "no (out of specification)",
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn_,
        "unanswered": unanswered,
        "not_applicable": 0,
        "accuracy": round((tp + tn) / n, 4),
        "recall": round(tp / total_positive, 4) if total_positive else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "self_consistency": {
            "needs_review_fired": inconsistent,
            "verdict_errors": caught + missed,
            "errors_caught_by_needs_review": caught,
            "errors_missed_by_needs_review": missed,
            "note": "needs_review compares the run's own conforms_to_spec against the same "
                    "arithmetic re-run over the run's OWN extracted numbers. It uses no gold, so "
                    "a forker can compute it on unlabelled certificates.",
        },
        "rows": rows,
    }

