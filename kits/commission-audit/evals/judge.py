"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Three graders, scored separately and never folded together:

1. per-(record, field) exact match, the extraction grade;
2. a confusion matrix on `claim_valid` against gold's own computation -- which gold got by running
   the same five-branch rule over the folio values the record states. AN UNOWED CLAIM IS THE
   POSITIVE CLASS: a commission line that is not owed as claimed and gets waved through is the
   failure a hotel finance desk actually pays for, so recall is reported on "no". THIS IS THE
   HEADLINE. Whether the claim is owed is the whole question the kit asks;
3. a confusion matrix on the pure-code `needs_recovery` flag against the same flag computed from
   GOLD's own values -- "is this the line somebody has to chase today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `claim_valid` disagreed with
the same computation re-run over the model's OWN extracted values. That needs no gold, so it is
the one figure here a forker can still compute on records nobody has labelled -- it is reported,
and it is deliberately not called a guardrail, because this kit's guardrail is the business flag
above.
"""
import re

from src.extract import compute as _compute
from src.extract import is_claim_valid as _icv


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _num(v):
    m = re.search(r"-?\d+(\.\d+)?", str(v or "").replace(",", ""))
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
    """Both nullable fields are legitimately null on part of the corpus and stated on the rest --
    `room_revenue_refunded_usd` is null exactly on a cancellation or no-show, and
    `penalty_charged_usd` is null exactly on a stay -- so a null there is a `hit` when the model
    matches gold, never a `miss` by default the way a corpus with no nullable fields would treat
    any null. A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong`
    (returned something else)."""
    by_field, cells = {}, []
    for claim_ref, rec in sorted(records.items()):
        g = golds.get(claim_ref) or {}
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
            cells.append({"doc": claim_ref, "field": name, "verdict": v, "got": got, "want": want,
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


def _gold_valid(g):
    """Gold's own verdict, re-derived here by the SAME computation the kit publishes -- so the
    truth this matrix grades against can never be a separately-typed label that drifted."""
    return _icv(g.get("claimed_commission_usd"), g.get("folio_status"), g.get("booking_source"),
                g.get("already_commissioned"), g.get("room_revenue_usd"),
                g.get("room_revenue_refunded_usd"), g.get("penalty_charged_usd"),
                g.get("contract_rate_pct"))


def score_flags(records, flags, golds):
    """The claim-validity verdict and the recovery flag, both scored against gold, plus the
    no-gold consistency diagnostic.

    records: {claim_ref: {field: {value,...}}} from the run.
    flags:   {claim_ref: needs_recovery_or_None} from the run's own pure code.
    golds:   {claim_ref: gold dict}. Gold's validity is re-derived here by the SAME computation
             the kit publishes, and gold's needs_recovery by the SAME rule src/extract.py applies
             -- so neither truth this grades against is a separately-typed label that could drift
             from the code.

    Positive class is "no" -- the commission claimed is not what is actually owed. Recall is
    therefore "of every claim that really is wrong, how many did the run call wrong".
    """
    rows, flag_rows = [], []
    inconsistent = 0
    caught = missed = 0
    by_fault = {}
    for claim_ref, g in sorted(golds.items()):
        want = _gold_valid(g)
        rec = records.get(claim_ref) or {}
        got = (rec.get("claim_valid") or {}).get("value")
        rows.append({"doc": claim_ref, "want": want, "got": got, "verdict": None,
                     "fault": g.get("_fault"), "shape": g.get("_shape"),
                     "needs_recovery": bool(flags.get(claim_ref))})

        # ⚑ PER-SHAPE, NOT JUST OVERALL. A headline verdict figure hides which of the five hard
        # cases actually carried it -- a run can be perfect on plain stays and blind on the
        # penalty-window cancellations, and one number cannot say so.
        key = g.get("_fault") or g.get("_shape") or "unclassified"
        d = by_fault.setdefault(key, {"n": 0, "correct": 0})
        d["n"] += 1
        if got == want:
            d["correct"] += 1

        # The recovery flag, computed from gold's own values by the same rule the run applies to
        # its own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"claim_valid": want, "invoice_status": g.get("invoice_status")})
        got_flag = flags.get(claim_ref)
        flag_rows.append({"doc": claim_ref,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict survive the same computation re-run over
        # the reply's own values? No gold is used here -- that is the whole point of reporting it.
        v = lambda n: (rec.get(n) or {}).get("value")            # noqa: E731
        self_check = _icv(v("claimed_commission_usd"), v("folio_status"), v("booking_source"),
                          v("already_commissioned"), v("room_revenue_usd"),
                          v("room_revenue_refunded_usd"), v("penalty_charged_usd"),
                          v("contract_rate_pct"))
        if self_check is not None and got in ("yes", "no") and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    matrix = _matrix(rows, "no")
    flag_matrix = _matrix(flag_rows, "yes")
    for d in by_fault.values():
        d["accuracy"] = round(d["correct"] / d["n"], 4) if d["n"] else None
    return {
        "positive_class": "no (the commission claimed is not what is actually owed)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "by_case": {k: by_fault[k] for k in sorted(by_fault)},
        "recovery_flag": dict(flag_matrix,
                              positive_class="yes (not owed as claimed, invoice already paid)",
                              note="needs_recovery compares the run's own claim_valid and "
                                   "invoice_status against the same two-boolean rule run over "
                                   "GOLD's values. It is a business condition, so it needs "
                                   "labels -- unlike the extraction grade, which does too, and "
                                   "unlike the consistency diagnostic below, which does not.",
                              rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_numbers": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the commission "
                    "computation over the run's OWN extracted values and counts the replies whose "
                    "stated verdict disagrees with it. It uses no gold, so a forker can compute "
                    "it on unlabelled records -- but it is blind to a reply that misreads a value "
                    "and then judges that misreading correctly.",
        },
        "rows": rows,
    }
