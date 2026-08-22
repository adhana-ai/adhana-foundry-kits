"""Score a disposition run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(record, field) exact match, the extraction grade;
2. a confusion matrix on `disposition_eligible` against gold's own derivation. FROZEN IS THE
   POSITIVE CLASS: a series under a live hold that gets called eligible is the failure a records
   office actually pays for -- it is the one that reaches a destruction batch -- so recall is
   reported on "no". THIS IS THE HEADLINE. Whether a series may be proposed for destruction is
   the whole question the kit asks;
3. `binding_hold_id` -- did the run name the same hold gold names, INCLUDING naming none when
   none binds? It is inside grader 1 as one of twelve cells, and it is broken out because it is
   the reasoning step: the prose scope judgement that decides grader 2;
4. a confusion matrix on the pure-code `needs_review` flag against the same flag computed from
   GOLD's own values -- "is this the record somebody has to pull out of the queue today". It is a
   business condition, so unlike a self-consistency check it genuinely needs labels, and saying so
   is half of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `disposition_eligible`
disagrees with the same derivation re-run over the model's OWN named hold and OWN extracted dates.
That needs no gold, so it is the one figure here a forker can still compute on records nobody has
labelled.

⚠︎ AND ITS BLIND SPOT, STATED RATHER THAN LEFT TO BE FOUND. The derivation collapses the hold
search to its RESULT, so a reply that names the wrong hold -- or misses a live successor and
answers null -- and then derives eligibility correctly from that wrong hold is perfectly
self-consistent and completely wrong. The diagnostic is blind to exactly the step this corpus is
built to test. Grader 3 is what measures it, and grader 3 needs gold.
"""
import re

from src.extract import compute as _compute
from src.extract import eligibility as _elig


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(field, got, want):
    g, w = norm(got), norm(want)
    return g == w


def score(fields, records, golds):
    """`overlapping_expires` and `binding_hold_id` are legitimately null on many records and
    stated on the rest -- both are a `hit` when the model matches gold, never a `miss` by default
    the way a corpus with no nullable fields would treat any null. A cell is a `hit`, a `miss`
    (returned nothing where gold has a value) or `wrong` (returned something else)."""
    by_field, cells = {}, []
    for case_id, rec in sorted(records.items()):
        g = golds.get(case_id) or {}
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
            cells.append({"doc": case_id, "field": name, "verdict": v, "got": got, "want": want,
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
    """The eligibility verdict, the binding-hold identification and the review flag, all scored
    against gold, plus the no-gold consistency diagnostic.

    records: {case_id: {field: {value,...}}} from the run.
    flags:   {case_id: needs_review_or_None} from the run's own pure code.
    golds:   {case_id: gold dict}. Gold's verdict is re-derived here by the SAME rule the kit
             publishes, and gold's needs_review by the SAME rule src/extract.py applies -- so
             neither truth this grades against is a separately-typed label that could drift from
             the code.

    Positive class is "no" -- this series may NOT be proposed for destruction. Recall is therefore
    "of every series that really is frozen, how many did the run refuse to release".
    """
    rows, flag_rows, hold_rows = [], [], []
    by_class = {}
    inconsistent = 0
    caught = missed = 0
    for case_id, g in sorted(golds.items()):
        want = _elig(g.get("binding_hold_id"), g.get("overlapping_expires"),
                     g.get("retention_expires"))
        rec = records.get(case_id) or {}
        got = (rec.get("disposition_eligible") or {}).get("value")
        rows.append({"doc": case_id, "want": want, "got": got, "verdict": None,
                     "klass": g.get("_class"),
                     "needs_review": bool(flags.get(case_id))})

        # ⚑ THE REASONING STEP, GRADED ON ITS OWN. Naming no hold when gold names none is a hit;
        # naming the wrong hold and naming none where one binds are different errors and are
        # counted apart, because they fail in opposite directions.
        #
        # ⚠︎ AN UNANSWERED RECORD IS NOT A CORRECT "NOTHING BINDS", and this grader said it was
        # until it was checked. Run r002 lost one record to a client-side socket timeout; that
        # record's gold names no binding hold, so `None == None` scored it CORRECT and the grader
        # published 55 of 55 over 54 replies. `_matrix` below has carried the same warning in
        # words since the sibling kits, and this grader is not a matrix, so it did not inherit it.
        # Found by disbelieving a perfect score, not by a gate.
        answered = case_id in records
        want_hold = g.get("binding_hold_id")
        got_hold = (rec.get("binding_hold_id") or {}).get("value")
        if not answered:
            hold_verdict = "unanswered"
        elif norm(got_hold) == norm(want_hold):
            hold_verdict = "correct"
        elif want_hold is not None and got_hold is None:
            hold_verdict = "missed_a_binding_hold"
        elif want_hold is None and got_hold is not None:
            hold_verdict = "invented_a_binding_hold"
        else:
            hold_verdict = "named_the_wrong_hold"
        hold_rows.append({"doc": case_id, "want": want_hold, "got": got_hold,
                          "verdict": hold_verdict, "klass": g.get("_class")})

        # Per-class accuracy on the headline verdict. The class labels are the corpus's own claim
        # about WHY each record is what it is, so this is the table that says which of the four
        # hard cases a model actually fails -- an overall percentage cannot.
        klass = g.get("_class") or "unclassified"
        d = by_class.setdefault(klass, {"n": 0, "verdict_correct": 0, "hold_correct": 0})
        d["n"] += 1
        if got == want:
            d["verdict_correct"] += 1
        if hold_verdict == "correct":
            d["hold_correct"] += 1

        # The review flag, computed from gold's own values by the same rule the run applies to its
        # own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"disposition_eligible": want, "queue_status": g.get("queue_status")})
        got_flag = flags.get(case_id)
        flag_rows.append({"doc": case_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict survive the same derivation re-run over the
        # reply's own values? No gold is used here -- that is the whole point of reporting it.
        self_check = _elig((rec.get("binding_hold_id") or {}).get("value"),
                           (rec.get("overlapping_expires") or {}).get("value"),
                           (rec.get("retention_expires") or {}).get("value"))
        if self_check is not None and got in ("yes", "no") and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    matrix = _matrix(rows, "no")
    flag_matrix = _matrix(flag_rows, "yes")
    hold_correct = sum(1 for r in hold_rows if r["verdict"] == "correct")
    hold_counts = {}
    for r in hold_rows:
        hold_counts[r["verdict"]] = hold_counts.get(r["verdict"], 0) + 1

    return {
        "positive_class": "no (this series may NOT be proposed for destruction)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "binding_hold": {
            "correct": hold_correct,
            "of": len(hold_rows),
            "accuracy": round(hold_correct / len(hold_rows), 4) if hold_rows else None,
            "counts": hold_counts,
            "unanswered": hold_counts.get("unanswered", 0),
            "note": "Did the run name the hold gold names, including naming none when none "
                    "binds? This is the prose scope judgement the eligibility verdict rests on. "
                    "It is one of the twelve extraction cells as well; it is broken out because "
                    "an average over twelve fields hides the only one that required reasoning. "
                    "The denominator is every gold record, not every reply -- a record that "
                    "produced no reply is `unanswered` and is never a correct call.",
            "rows": hold_rows,
        },
        "by_class": by_class,
        "review_flag": dict(flag_matrix,
                            positive_class="yes (frozen and already in the destruction queue)",
                            note="needs_review compares the run's own disposition_eligible and "
                                 "queue_status against the same two-value rule run over GOLD's "
                                 "values. It is a business condition, so it needs labels -- "
                                 "unlike the extraction grade, which does too, and unlike the "
                                 "consistency diagnostic below, which does not. It asks for a "
                                 "series to be pulled OUT of a destruction queue; it never "
                                 "proposes putting one in.",
                            rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the eligibility "
                    "derivation over the run's OWN named binding hold and OWN extracted dates "
                    "and counts the replies whose stated verdict disagrees with it. It uses no "
                    "gold, so a forker can compute it on unlabelled records -- but it collapses "
                    "the hold search to its result, so it is blind to a reply that names the "
                    "wrong hold, or misses a live successor, and then derives correctly from "
                    "that. That is precisely the step this corpus is built to test.",
        },
        "rows": rows,
    }
