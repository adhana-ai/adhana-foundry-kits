"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Three graders, scored separately and never folded together:

1. per-(record, field) exact match, the extraction grade;
2. `variance_cause` against gold's own arithmetic. THIS IS THE HEADLINE, and it is reported in TWO
   shapes because a six-way classification has two different failures inside it:
     - SIX-WAY EXACT ACCURACY: did the run name the right cause. A run that says
       `duplicate_records` where the truth is `late_records` has spotted the variance and blamed
       the wrong block, which is a different day's work from missing it entirely;
     - AN ACTIONABLE/NOT-ACTIONABLE CONFUSION MATRIX collapsed onto the same rows, where the
       positive class is "this line has a variance somebody has to act on" -- anything that is not
       `none` and not `rounding`. A real variance called clean is the failure a revenue-assurance
       desk actually pays for, so recall is reported on that class;
3. a confusion matrix on the pure-code `needs_credit` flag against the same flag computed from
   GOLD's own values -- "is this the line a customer is owed money on today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `variance_cause` disagrees
with the same classification re-run over the model's OWN extracted values. That needs no gold, so
it is the one figure here a forker can still compute on records nobody has labelled -- it is
reported, and it is deliberately not called a guardrail, because this kit's guardrail is the
business flag above.
"""
import re

from src.extract import CAUSES
from src.extract import classify as _classify
from src.extract import compute as _compute

# The causes that mean somebody has to do something about this line. `rounding` is an EXPLAINED
# difference and `none` is no difference at all; both are "leave it alone".
ACTIONABLE = ("unrated_usage", "duplicate_records", "late_records", "unexplained")


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
    """A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned
    something else).

    ⚠︎ NOTHING IN THIS CORPUS IS LEGITIMATELY NULL, AND THAT IS A DELIBERATE DIFFERENCE FROM THE
    SIBLING KITS. Every quantity is stated on every record, INCLUDING the ones that are zero: a
    line with no unrated usage says "0 KB" rather than leaving the section out. So a null here is
    always a miss, and a model that returns null for a stated 0 is wrong in a way the page should
    show -- `null` and `0` are different answers to "how much failed rating", and only one of them
    is a measurement.
    """
    by_field, cells = {}, []
    for line_ref, rec in sorted(records.items()):
        g = golds.get(line_ref) or {}
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
            cells.append({"doc": line_ref, "field": name, "verdict": v, "got": got, "want": want,
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
    """The variance-cause verdict and the credit flag, both scored against gold, plus the no-gold
    consistency diagnostic.

    records: {line_ref: {field: {value,...}}} from the run.
    flags:   {line_ref: needs_credit_or_None} from the run's own pure code.
    golds:   {line_ref: gold dict}. Gold's cause is re-derived here by the SAME arithmetic the kit
             publishes, and gold's needs_credit by the SAME rule src/extract.py applies -- so
             neither truth this grades against is a separately-typed label that could drift from
             the code.
    """
    rows, flag_rows, act_rows = [], [], []
    confusion = {}                      # {(want, got): count} -- the six-way picture
    per_cause = {c: {"want": 0, "got_right": 0} for c in CAUSES}
    inconsistent = 0
    caught = missed = 0
    exact = 0

    for line_ref, g in sorted(golds.items()):
        want = _classify(g.get("service_type"), g.get("mediated_quantity"),
                         g.get("invoiced_quantity"), g.get("unrated_quantity"),
                         g.get("prior_period_quantity"), g.get("confirmed_duplicate_quantity"))
        rec = records.get(line_ref) or {}
        got = (rec.get("variance_cause") or {}).get("value")
        got = got if got in CAUSES else None

        rows.append({"doc": line_ref, "want": want, "got": got,
                     "verdict": ("exact" if got == want else
                                 ("unanswered" if got is None else "wrong_cause")),
                     "needs_credit": bool(flags.get(line_ref))})
        confusion["%s->%s" % (want, got)] = confusion.get("%s->%s" % (want, got), 0) + 1
        if want in per_cause:
            per_cause[want]["want"] += 1
            if got == want:
                per_cause[want]["got_right"] += 1
        if got == want:
            exact += 1

        # The same rows collapsed onto the only binary a desk actually queues on.
        act_rows.append({"doc": line_ref,
                         "want": "yes" if want in ACTIONABLE else "no",
                         "got": (None if got is None else ("yes" if got in ACTIONABLE else "no")),
                         "verdict": None})

        # The credit flag, computed from gold's own values by the same rule the run applies to its
        # own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"variance_cause": want, "invoice_status": g.get("invoice_status")})
        got_flag = flags.get(line_ref)
        flag_rows.append({"doc": line_ref,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own cause survive the same arithmetic re-run over the
        # reply's own numbers? No gold is used here -- that is the whole point of reporting it.
        self_check = _classify((rec.get("service_type") or {}).get("value"),
                               (rec.get("mediated_quantity") or {}).get("value"),
                               (rec.get("invoiced_quantity") or {}).get("value"),
                               (rec.get("unrated_quantity") or {}).get("value"),
                               (rec.get("prior_period_quantity") or {}).get("value"),
                               (rec.get("confirmed_duplicate_quantity") or {}).get("value"))
        if self_check is not None and got is not None and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    n = len(rows) or 1
    act_matrix = _matrix(act_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    return {
        "positive_class": "an actionable variance (any cause other than none or rounding)",
        "cause_accuracy": round(exact / n, 4),
        "cause_exact": exact,
        "cause_rows": n,
        "confusion": dict(sorted(confusion.items())),
        "per_cause": per_cause,
        "true_positive": act_matrix["true_positive"], "false_positive": act_matrix["false_positive"],
        "true_negative": act_matrix["true_negative"], "false_negative": act_matrix["false_negative"],
        "unanswered": act_matrix["unanswered"], "not_applicable": 0,
        "accuracy": act_matrix["accuracy"], "recall": act_matrix["recall"],
        "precision": act_matrix["precision"],
        "actionable_note": "The six-way accuracy above and this matrix are two readings of the "
                           "same 55 rows and must not be averaged. A reply can be inside this "
                           "matrix's true_positive cell and still be counted wrong by "
                           "cause_accuracy -- it saw the variance and blamed the wrong block.",
        "credit_flag": dict(flag_matrix, positive_class="yes (over-billed and already issued)",
                            note="needs_credit compares the run's own variance_cause and "
                                 "invoice_status against the same rule run over GOLD's values. It "
                                 "is a business condition, so it needs labels -- unlike the "
                                 "consistency diagnostic below, which does not.",
                            rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_numbers": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the variance arithmetic "
                    "over the run's OWN extracted quantities and counts the replies whose stated "
                    "cause disagrees with it. It uses no gold, so a forker can compute it on "
                    "unlabelled records -- but it is blind to a reply that misreads a quantity "
                    "and then classifies that misreading correctly.",
        },
        "rows": rows,
    }
