"""Score a screening-alert adjudication run. PURE CODE -- gold is exact and the answer is one value
per cell, so `==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(alert, field) exact match, the extraction grade;

2. the VERDICT, scored three ways at once. Three-way exact accuracy across same_party /
   not_a_match / insufficient_information; a binary confusion matrix on the distinction that
   decides whether a human ever sees the alert again -- IS THIS ALERT STILL OPEN, i.e. is it
   anything other than `not_a_match`; and, named on its own,

   ⚑ THE FALSE-CONFIDENCE COUNT: of the alerts the rulebook says the FILE CANNOT DECIDE, how many
   did the run answer with a decision anyway? This is the number this kit exists to publish. An
   adjudicator that never says "I cannot tell" is not decisive, it is guessing, and on a screening
   queue the guess that costs is a confident `not_a_match` -- the alert is closed and nobody looks
   again. It is counted and named separately as `false_confidence`, never averaged into an accuracy
   figure where it disappears, and the expensive direction of the binary is named separately too,
   as `false_clearance`;

3. the DECIDING IDENTIFIER. Which identifier produced the verdict, scored on its own -- because a
   run can reach the right verdict for the wrong reason, and on an adjudication that a person has
   to sign, the reason is half the answer. `right_verdict_wrong_reason` counts exactly that;

4. a confusion matrix on the pure-code `needs_escalation` flag against the same rule computed from
   GOLD's own values -- "is this the alert somebody has to reach today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `verdict` disagrees with the
rulebook re-run over the model's OWN extracted values. That needs no gold, so it is the one figure
here a forker can still compute on alerts nobody has labelled -- it is reported, and it is
deliberately not called a guardrail, because this kit's guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. The rulebook is illustrative and is not an authority; a run that scores
100 pct here has agreed with `data/rulebook.json`, which is a different and much smaller claim
than being right about a real alert.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import correct_deciding_identifier as _deciding_of
from src.extract import correct_verdict as _verdict_of


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(field, got, want):
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    return g == w


# ⚠︎ SIX LEGITIMATELY-NULL FIELDS, AND EVERY NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
# An identifier value is null exactly where its type is `none`; a date or place of birth is null
# exactly where the sheet says it is not recorded (customer side) or not published (list side).
# A PARTIAL DATE IS NOT ONE OF THESE -- "1978" is a value, and returning null for it is a miss.
NULLABLE = ("customer_identifier_value", "listed_identifier_value", "customer_dob", "listed_dob",
            "customer_place_of_birth", "listed_place_of_birth")


def score(fields, records, golds):
    """A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned
    something else). The six nullable fields are a `hit` when the model matches gold's null, never
    a `miss` by default the way a corpus with no nullable fields would treat any null."""
    by_field, cells = {}, []
    for alert_id, rec in sorted(records.items()):
        g = golds.get(alert_id) or {}
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
            cells.append({"doc": alert_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": want is not None,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
            d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)
    hallucinated = sum(1 for c in cells if c["verdict"] == "wrong" and not c["stated"])

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": hallucinated,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields if f.get("type") == "enum"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a model that answers nothing score as a careful one, so an unanswered row
    is counted on its own and never as a correct call -- which on a screening queue is the whole
    difference between an alert nobody adjudicated and an alert somebody dismissed.
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


def score_verdicts(records, flags, golds):
    """The adjudication, the deciding identifier and the escalation flag, all scored against gold,
    plus the no-gold consistency diagnostic.

    records: {alert_id: {field: {value,...}}} from the run.
    flags:   {alert_id: needs_escalation_or_None} from the run's own pure code.
    golds:   {alert_id: gold dict}. Gold's verdict and deciding identifier are re-derived here by
             the SAME rulebook lookup the kit publishes, and gold's needs_escalation by the SAME
             rule src/extract.py applies -- so no truth this grades against is a separately-typed
             label that could drift from the code.
    """
    rows, open_rows, flag_rows, deciding_rows = [], [], [], []
    confusion = {}
    inconsistent = 0
    caught = missed = 0
    false_clearance, over_escalation, false_confidence, false_caution = [], [], [], []
    right_verdict_wrong_reason = []

    for alert_id, g in sorted(golds.items()):
        want = _verdict_of(g)
        want_deciding = _deciding_of(g)
        rec = records.get(alert_id) or {}
        got = (rec.get("verdict") or {}).get("value")
        got = got if got in RB.VERDICTS else None
        got_deciding = (rec.get("deciding_identifier") or {}).get("value")
        got_deciding = got_deciding if got_deciding in RB.DECIDING else None

        rows.append({"doc": alert_id, "want": want, "got": got,
                     "correct": (got is not None and got == want)})
        confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
        confusion[want][got or "unanswered"] += 1

        deciding_rows.append({"doc": alert_id, "want": want_deciding, "got": got_deciding,
                              "correct": (got_deciding is not None
                                          and got_deciding == want_deciding)})
        if got is not None and got == want and got_deciding is not None \
                and got_deciding != want_deciding:
            right_verdict_wrong_reason.append({"doc": alert_id, "verdict": want,
                                               "gold_reason": want_deciding,
                                               "model_reason": got_deciding})

        # ⚑ THE BINARY THAT DECIDES WHETHER A HUMAN EVER SEES THE ALERT AGAIN. Everything that is
        # not `not_a_match` leaves the alert OPEN -- it is either the listed party or it cannot be
        # decided from the file, and both go to a person. Collapsing the three classes onto that
        # one distinction is what makes a false clearance nameable.
        want_open = "yes" if want != "not_a_match" else "no"
        got_open = None if got is None else ("yes" if got != "not_a_match" else "no")
        open_rows.append({"doc": alert_id, "want": want_open, "got": got_open, "verdict": None})
        if want_open == "yes" and got_open == "no":
            false_clearance.append({"doc": alert_id, "gold": want, "model": got})
        if want_open == "no" and got_open == "yes":
            over_escalation.append({"doc": alert_id, "gold": want, "model": got})

        # ⚑ THE NUMBER THIS KIT EXISTS TO PUBLISH, IN BOTH DIRECTIONS.
        # false_confidence: the file cannot decide and the run decided anyway.
        # false_caution:    the file DOES decide and the run reached for "I cannot tell" instead.
        # The second is a real failure too -- an adjudicator that hides behind the third verdict
        # produces a queue nobody can work -- and publishing only the first would flatter the kit.
        if want == "insufficient_information" and got is not None \
                and got != "insufficient_information":
            false_confidence.append({"doc": alert_id, "model": got})
        if want != "insufficient_information" and got == "insufficient_information":
            false_caution.append({"doc": alert_id, "gold": want})

        want_flag = _compute({"verdict": want, "account_status": g.get("account_status")})
        got_flag = flags.get(alert_id)
        flag_rows.append({"doc": alert_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict survive the rulebook re-run over the reply's
        # own values? No gold is used here -- that is the whole point of reporting it.
        self_check = _verdict_of({k: (rec.get(k) or {}).get("value")
                                  for k in ("customer_identifier_type",
                                            "customer_identifier_value",
                                            "listed_identifier_type", "listed_identifier_value",
                                            "customer_dob", "listed_dob",
                                            "customer_place_of_birth", "listed_place_of_birth")})
        if self_check is not None and got is not None and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    n_deciding_correct = sum(1 for r in deciding_rows if r["correct"])
    opened = _matrix(open_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    n_must_stay_open = sum(1 for r in open_rows if r["want"] == "yes")
    n_undecidable = sum(1 for r in rows if r["want"] == "insufficient_information")
    n_decidable = n - n_undecidable

    return {
        "verdict_accuracy": round(n_correct / n, 4),
        "verdict_correct": n_correct,
        "verdict_rows": n,
        "verdict_unanswered": n_unanswered,
        "confusion": confusion,
        "per_class": {v: {"gold": sum(1 for r in rows if r["want"] == v),
                          "correct": sum(1 for r in rows if r["want"] == v and r["correct"])}
                      for v in RB.VERDICTS},
        "open": dict(opened,
                     positive_class="yes (this alert is NOT dismissible on the file)",
                     note="The three-way verdict collapsed onto the one distinction that decides "
                          "whether a human ever sees the alert again. A false negative here is an "
                          "alert the shipped rulebook would have left open and the run closed.",
                     rows=open_rows),
        "false_clearance": false_clearance,
        "false_clearance_count": len(false_clearance),
        "false_clearance_rate_pct": (round(100.0 * len(false_clearance) / n_must_stay_open, 2)
                                     if n_must_stay_open else None),
        "over_escalation": over_escalation,
        "over_escalation_count": len(over_escalation),
        "false_confidence": false_confidence,
        "false_confidence_count": len(false_confidence),
        "false_confidence_rate_pct": (round(100.0 * len(false_confidence) / n_undecidable, 2)
                                      if n_undecidable else None),
        "false_caution": false_caution,
        "false_caution_count": len(false_caution),
        "false_caution_rate_pct": (round(100.0 * len(false_caution) / n_decidable, 2)
                                   if n_decidable else None),
        "deciding": {
            "accuracy": round(n_deciding_correct / n, 4),
            "correct": n_deciding_correct,
            "rows": n,
            "right_verdict_wrong_reason": right_verdict_wrong_reason,
            "right_verdict_wrong_reason_count": len(right_verdict_wrong_reason),
            "note": "Which identifier produced the verdict, scored on its own. A run can land on "
                    "the right verdict for the wrong reason, and on an adjudication a person has "
                    "to sign, the reason is half the answer.",
            "detail": deciding_rows,
        },
        "escalation_flag": dict(flag_matrix,
                                positive_class="yes (not dismissible on the file, account live)",
                                note="needs_escalation compares the run's own verdict and "
                                     "account_status against the same rule run over GOLD's "
                                     "values. It is a business condition, so it needs labels -- "
                                     "unlike the consistency diagnostic below, which does not. It "
                                     "orders a worklist and freezes nothing.",
                                rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the rulebook over the "
                    "run's OWN extracted values and counts the replies whose stated verdict "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "alerts -- but it is blind to a reply that misreads an identifier or a date "
                    "and then reasons correctly from the misreading.",
        },
        "rows": rows,
    }
