"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Three graders, scored separately and never folded together:

1. per-(record, field) exact match, the extraction grade;
2. a confusion matrix on `delivery_complete` against gold's own completeness -- which gold got by
   the same strict comparison, over the same two quantities and the same condition code the record
   states. INCOMPLETE IS THE POSITIVE CLASS: a delivery that did not arrive as booked and gets
   called complete is the failure an operations desk actually pays for, so recall is reported on
   "no". THIS IS THE HEADLINE. Completeness is the whole question the kit asks;
3. a confusion matrix on the pure-code `needs_review` flag against the same flag computed from
   GOLD's own values -- "is this the record a person has to pick up today". It is a business
   condition, so unlike the sibling kit before it in this series it genuinely needs labels, and
   saying so is half of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `delivery_complete` disagreed
with the same comparison re-run over the model's OWN extracted quantities and condition code. That
needs no gold, so it is the one figure here a forker can still compute on records nobody has
labelled -- it is reported, and it is deliberately not called a guardrail, because this kit's
guardrail is the business flag above.
"""
import re

from src.extract import compute as _compute
from src.extract import is_complete as _is_complete


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
    """Every field is stated on every record in this corpus, so a null is always a miss -- there
    is no legitimately-absent value here the way a one-sided limit is absent on a sibling kit's
    certificates. A cell is a `hit`, a `miss` (returned nothing) or `wrong` (returned something
    else)."""
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


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding a null verdict into "true negative"
    would let a model that answers nothing score as a careful one, so an unanswered row is counted
    on its own and never as a correct call.
    """
    tp = fp = tn = fn_ = unanswered = 0
    for r in rows:
        want, got = r["want"], r["got"]
        if got not in ("yes", "no"):
            unanswered += 1
            r["verdict"] = "unanswered"
            continue
        if want == positive and got == positive:
            tp += 1
            r["verdict"] = "true_positive"
        elif want == positive:
            fn_ += 1
            r["verdict"] = "false_negative"
        elif got == positive:
            fp += 1
            r["verdict"] = "false_positive"
        else:
            tn += 1
            r["verdict"] = "true_negative"
    n = len(rows) or 1
    total_positive = sum(1 for r in rows if r["want"] == positive)
    return {
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn_,
        "unanswered": unanswered,
        "not_applicable": 0,
        "accuracy": round((tp + tn) / n, 4),
        "recall": round(tp / total_positive, 4) if total_positive else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
    }


def score_flags(records, flags, golds):
    """The completeness verdict and the review flag, both scored against gold, plus the
    no-gold consistency diagnostic.

    records: {stmt_id: {field: {value,...}}} from the run.
    flags:   {stmt_id: needs_review_or_None} from the run's own pure code.
    golds:   {stmt_id: gold dict}. Gold's completeness is re-derived here by the SAME comparison
             the kit publishes, and gold's needs_review by the SAME rule src/extract.py applies --
             so neither truth this grades against is a separately-typed label that could drift
             from the code.

    Positive class is "no" -- the delivery did not arrive as booked. Recall is therefore "of every
    delivery that really was incomplete, how many did the run call incomplete".
    """
    rows, flag_rows = [], []
    inconsistent = 0
    caught = missed = 0
    for stmt_id, g in sorted(golds.items()):
        want = _is_complete(g.get("delivered_quantity"), g.get("ordered_quantity"),
                            g.get("condition_code"))
        rec = records.get(stmt_id) or {}
        got = (rec.get("delivery_complete") or {}).get("value")
        rows.append({"doc": stmt_id, "want": want, "got": got, "verdict": None,
                     "needs_review": bool(flags.get(stmt_id))})

        # The review flag, computed from gold's own values by the same rule the run applies to
        # its own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"delivery_complete": want,
                              "recipient_signature_present": g.get("recipient_signature_present")})
        got_flag = flags.get(stmt_id)
        flag_rows.append({"doc": stmt_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict survive the same comparison re-run over the
        # reply's own numbers? No gold is used here -- that is the whole point of reporting it.
        self_check = _is_complete((rec.get("delivered_quantity") or {}).get("value"),
                                  (rec.get("ordered_quantity") or {}).get("value"),
                                  (rec.get("condition_code") or {}).get("value"))
        if self_check is not None and got in ("yes", "no") and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    matrix = _matrix(rows, "no")
    flag_matrix = _matrix(flag_rows, "yes")
    return {
        "positive_class": "no (the delivery did not arrive as booked)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "review_flag": dict(flag_matrix, positive_class="yes (incomplete and unsigned)",
                            note="needs_review compares the run's own delivery_complete and "
                                 "recipient_signature_present against the same two-boolean rule "
                                 "run over GOLD's values. It is a business condition, so it needs "
                                 "labels -- unlike the extraction grade, which does too, and "
                                 "unlike the consistency diagnostic below, which does not.",
                            rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_numbers": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the completeness "
                    "comparison over the run's OWN extracted quantities and condition code and "
                    "counts the replies whose stated verdict disagrees with it. It uses no gold, "
                    "so a forker can compute it on unlabelled records -- but it is blind to a "
                    "reply that misreads a quantity and then judges that misreading correctly.",
        },
        "rows": rows,
    }
