"""Score a CAM pre-check run. PURE CODE -- gold is exact and every answer is one value, so `==`
(with light normalisation, and a stated dollar tolerance on the one computed money field) settles
it. No model grades this kit, and none should: the truth here is arithmetic, and arithmetic is the
last thing to ask a language model to adjudicate.

Three graders, scored separately and never folded together:

1. per-(line, field) exact match, the extraction grade. `permitted_amount_usd` is in it and is the
   only field graded to a TOLERANCE rather than to equality -- 1.00 US dollar, the same bar
   `line_ok` itself uses, stated once in src/rule.py;
2. a confusion matrix on `line_ok` against gold's own comparison -- which gold got by running the
   same four-stage rule over the same values the line states. NOT-BILLABLE-AS-CHARGED IS THE
   POSITIVE CLASS: a line billed wrong that gets called right is the failure a tenant's auditor
   finds two years later with interest, so recall is reported on "no". THIS IS THE HEADLINE;
3. a confusion matrix on the pure-code `needs_review` flag against the same flag computed from
   GOLD's own values -- "is this the line somebody has to fix today". It is a business condition,
   so unlike a self-consistency check it genuinely needs labels, and saying so is half of what
   makes the number believable.

And three figures that are NOT grades:

  * ARITHMETIC ACCURACY. How often the model's own `permitted_amount_usd` lands within a dollar of
    what the four stages actually produce. It is the same cells as one column of grader 1, reported
    on its own because it is the thing this kit is really asking a model to do and because it is
    the number that moves when a stage is skipped rather than misread.
  * THE TRAP TABLE. Accuracy on `line_ok` broken out by which of the eight planted faults or eight
    correct shapes the line carries. A headline accuracy over 55 records cannot tell you the model
    is fine on caps and blind on amortized capital; this can, and a five-record cell says so with
    its own denominator printed beside it.
  * SELF-CONSISTENCY. How often the model's stated `line_ok` disagrees with re-running the
    comparison over the model's OWN two numbers. That needs no gold, so it is the one figure here
    a forker can still compute on lines nobody has checked -- reported, and deliberately not called
    a guardrail, because this kit's guardrail is the business flag above.
"""
import re

from src.extract import compute as _compute
from src.rule import TOLERANCE_USD, line_is_ok as _ok, permitted_amount as _permitted


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _num(v):
    """⚠︎ `str(v or "")` WOULD BE A BUG HERE AND WAS ONE. A permitted amount of 0.00 is the CORRECT
    answer on every correctly-excluded line, and `0.0 or ""` is `""` -- so the falsy-default
    spelling scored seven right answers as unparseable and printed an arithmetic accuracy of 0 for
    a floor that had them all. Second instance of the same class in this kit in one afternoon (see
    evals/check_labels.py); a zero is a value, not an absence, and this corpus is full of zeroes
    because "the lease permits nothing" is a real answer here."""
    if v is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(v).replace(",", ""))
    return float(m.group(0)) if m else None


def equal(field, got, want):
    """Exact after light normalisation, EXCEPT the one computed money field.

    ⚠︎ THE TOLERANCE IS NOT LENIENCE, IT IS THE UNIT. `permitted_amount_usd` is the model's own
    arithmetic over a chain of divisions and an exponent; grading it to the cent would score a
    correct four-stage computation as wrong for a rounding step nobody in a property-accounting
    office would notice. A dollar is the same bar `line_ok` is defined at, so a reply cannot be
    graded right on the verdict and wrong on the number the verdict came from, or the other way
    round. Every other number is still exact to half a cent.
    """
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    if g == w:
        return True
    if field.get("type") in ("number", "integer"):
        gn, wn = _num(g), _num(w)
        if gn is None or wn is None:
            return False
        tol = TOLERANCE_USD if field.get("computed") else 0.005
        return abs(gn - wn) <= tol
    return False


def score(fields, records, golds):
    """Six of these twenty fields are legitimately null on some lines and stated on others -- an
    amortization term only on an amortizable capital item, an expansion only where there was one,
    three cap fields only where the lease caps something. Both are a `hit` when the model matches
    gold, never a `miss` by default. A cell is a `hit`, a `miss` (returned nothing where gold has a
    value) or `wrong` (returned something else)."""
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
    non_spannable = sorted({f["name"] for f in fields
                            if f.get("type") == "enum" or f.get("computed")})

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
            "non_spannable_fields": non_spannable,
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


def _gold_permitted(g):
    return _permitted(g.get("expense_class"), g.get("pool_gross_usd"),
                      g.get("amortization_years"), g.get("occupancy_sensitive"),
                      g.get("building_occupancy_pct"), g.get("building_area_sf"),
                      g.get("tenant_area_sf"), g.get("expansion_area_sf"),
                      g.get("expansion_month"), g.get("cap_type"), g.get("cap_pct"),
                      g.get("cap_basis_usd"), g.get("cap_years"))


def score_flags(records, flags, golds):
    """The billability verdict and the review flag, both scored against gold, plus the arithmetic
    figure, the trap table and the no-gold consistency diagnostic.

    records: {line_ref: {field: {value,...}}} from the run.
    flags:   {line_ref: needs_review_or_None} from the run's own pure code.
    golds:   {line_ref: gold dict}. Gold's permitted amount is RE-DERIVED here by the same four
             stages the kit publishes, and gold's needs_review by the SAME rule src/extract.py
             applies -- so neither truth this grades against is a separately-typed label that could
             drift from the code.

    Positive class on the verdict is "no" -- the amount billed is not what the lease permits.
    Recall is therefore "of every line that really is billed wrong, how many did the run catch".
    """
    rows, flag_rows = [], []
    inconsistent = caught = missed = 0
    arith_hit = arith_n = 0
    arith_errors = []
    traps = {}

    for line_ref, g in sorted(golds.items()):
        want_amount = _gold_permitted(g)
        want = _ok(g.get("billed_to_tenant_usd"), want_amount)
        rec = records.get(line_ref) or {}
        got = (rec.get("line_ok") or {}).get("value")
        got_amount = (rec.get("permitted_amount_usd") or {}).get("value")
        rows.append({"doc": line_ref, "want": want, "got": got, "verdict": None,
                     "needs_review": bool(flags.get(line_ref)),
                     "want_permitted_usd": want_amount, "got_permitted_usd": got_amount})

        # ---- the arithmetic figure, on the same dollar bar the verdict is defined at
        gn = _num(got_amount)
        if want_amount is not None:
            arith_n += 1
            if gn is not None and abs(gn - want_amount) <= TOLERANCE_USD:
                arith_hit += 1
            else:
                arith_errors.append({"doc": line_ref, "want": want_amount, "got": got_amount,
                                     "off_by": (None if gn is None
                                                else round(gn - want_amount, 2)),
                                     "shape": g.get("_fault") or g.get("_shape")})

        # ---- the trap table: which planted shape was this line, and was the verdict right
        key = g.get("_fault") or ("ok:" + str(g.get("_shape")))
        t = traps.setdefault(key, {"n": 0, "verdict_right": 0, "arithmetic_right": 0,
                                   "wrong_lines": []})
        t["n"] += 1
        if got == want:
            t["verdict_right"] += 1
        else:
            t["wrong_lines"].append(line_ref)
        if gn is not None and want_amount is not None and abs(gn - want_amount) <= TOLERANCE_USD:
            t["arithmetic_right"] += 1

        # ---- the review flag, computed from gold's own values by the same rule the run applies
        want_flag = _compute({"line_ok": want, "statement_status": g.get("statement_status"),
                              "billed_to_tenant_usd": g.get("billed_to_tenant_usd"),
                              "permitted_amount_usd": want_amount})
        got_flag = flags.get(line_ref)
        flag_rows.append({"doc": line_ref,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # ---- the diagnostic: does the reply's own verdict survive re-running the comparison over
        # the reply's own two numbers? No gold is used here -- that is the whole point of it.
        self_check = _ok((rec.get("billed_to_tenant_usd") or {}).get("value"), got_amount)
        if self_check is not None and got in ("yes", "no") and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    matrix = _matrix(rows, "no")
    flag_matrix = _matrix(flag_rows, "yes")
    return {
        "positive_class": "no (the amount billed is not what the lease permits)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "arithmetic": {
            "cells": arith_n,
            "hits": arith_hit,
            "accuracy": round(arith_hit / arith_n, 4) if arith_n else None,
            "tolerance_usd": TOLERANCE_USD,
            "errors": arith_errors,
            "note": "The model's own permitted_amount_usd against the four stages run over the "
                    "same values the line states, on the same 1.00 USD bar line_ok is defined at. "
                    "It is one column of the extraction grade, reported separately because it is "
                    "what this kit actually asks a model to do -- and because a stage SKIPPED and "
                    "a value MISREAD look identical in an accuracy figure and different here.",
        },
        "traps": traps,
        "review_flag": dict(flag_matrix,
                            positive_class="yes (overbilled and already issued to the tenant)",
                            note="needs_review compares the run's own line_ok, statement_status, "
                                 "billed and permitted amounts against the same three-condition "
                                 "rule run over GOLD's values. It is a business condition, so it "
                                 "needs labels -- unlike the consistency diagnostic below, which "
                                 "does not. It also reads a COMPUTED field, so it inherits every "
                                 "arithmetic error above.",
                            rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_numbers": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the billed-versus-permitted "
                    "comparison over the run's OWN two numbers and counts the replies whose stated "
                    "verdict disagrees with it. It uses no gold, so a forker can compute it on "
                    "unlabelled lines -- but it is blind to a reply that gets the arithmetic wrong "
                    "and then judges its own wrong number consistently, which on this corpus is "
                    "the commonest failure there is.",
        },
        "rows": rows,
    }
