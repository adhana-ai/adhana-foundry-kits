"""Score an adjudication run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(claim, field) exact match, the extraction grade;
2. a confusion matrix on `covered` against gold's own verdict -- which gold got by the same
   six-branch priority rule run over the values the record states. DENIAL IS THE POSITIVE CLASS:
   a claim that should be denied and gets called covered is the failure a warranty desk pays for
   in cash, so recall is reported on "no". THIS IS THE HEADLINE. Coverage is the whole question
   the kit asks;
3. a confusion matrix on the pure-code `needs_review` flag against the same flag computed from
   GOLD's own values -- "is this the claim somebody has to open a recovery on today". It is a
   business condition, so unlike a self-consistency check it genuinely needs labels, and saying so
   is half of what makes the number believable;
4. `narrative_finding` accuracy on its own -- did the reply read the technician's story or the
   dealer's coded cause. It is scored separately from the other twelve fields because it is the
   only extracted field whose answer is not written anywhere in the record: every other field is
   copied or calculated, this one is READ.

And two diagnostics that are not grades, both of which need no gold:

- how often the reply's stated `covered` disagrees with the same six-branch rule re-run over the
  reply's OWN extracted values;
- how often the reply's stated `months_in_service` disagrees with the date arithmetic re-run over
  the reply's OWN two dates.

⚑ AND ONE BREAKDOWN THAT IS THE POINT OF THE CORPUS: `covered` accuracy per DECIDING BRANCH. A
single verdict accuracy tells you the model is good; the per-branch table tells you whether it can
apply a plan's own limit rather than reaching for the bumper-to-bumper one, which is the finding a
buyer needs and the one an average erases.

⚠︎ ONE VOCABULARY NOTE, SO THE CODE AND THE PUBLISHED BOARD CANNOT BE READ AS DISAGREEING. The
report page lists FIVE graders, not four: it counts the self-consistency check as one, because the
board's contract is "every grader run over the answer set" and this is run over every answer. This
file calls it a diagnostic, because it grades nothing against a reference standard and must never
be quoted as an accuracy. Both are true; the difference is what the two surfaces are for, and the
board's own entry for it says so in its `decides` and `when_not`.
"""
import re

from src.extract import compute as _compute
from src.extract import coverage_verdict as _cv
from src.extract import months_between as _months
from src.extract import LABOR_OPS, PLAN_COMPONENTS, PLANS, WEAR_PARTS, EXCLUSIONS


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


def deciding_branch(g):
    """Which branch of the rule settles this gold row. Pure function of gold's own values -- the
    same function tools/build_corpus.py asserts its composition against, restated here so the
    scorer does not import the generator (a fork may not carry tools/)."""
    if g.get("narrative_finding") in EXCLUSIONS:
        return "exclusion"
    if g.get("claimed_labor_op") != LABOR_OPS.get(g.get("failed_component")):
        return "labor_op"
    if g.get("failed_component") in WEAR_PARTS:
        return "wear"
    if g.get("failed_component") not in PLAN_COMPONENTS.get(g.get("coverage_plan"), []):
        return "component_list"
    lim = PLANS.get(g.get("coverage_plan")) or {}
    if (g.get("months_in_service") or 0) > lim.get("months", 0) \
            or (g.get("odometer_miles") or 0) > lim.get("miles", 0):
        return "limit_exceeded"
    return "inside_terms"


def score(fields, records, golds):
    """A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned
    something else). No field in this corpus is legitimately null on any row, so a `miss` is
    always a real miss here -- stated rather than assumed, and asserted by evals/check_labels.py."""
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
    nonspannable = sorted({f["name"] for f in fields
                           if f.get("type") == "enum" or f["name"] == "months_in_service"})

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": sum(1 for c in cells if c["verdict"] == "wrong"),
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": nonspannable,
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
    """The coverage verdict and the recovery flag, both scored against gold, plus the two
    no-gold diagnostics and the per-branch breakdown.

    records: {claim_ref: {field: {value,...}}} from the run.
    flags:   {claim_ref: needs_review_or_None} from the run's own pure code.
    golds:   {claim_ref: gold dict}. Gold's verdict is re-derived here by the SAME rule the kit
             publishes, and gold's needs_review by the SAME rule src/extract.py applies -- so
             neither truth this grades against is a separately-typed label that could drift from
             the code.

    Positive class is "no" -- the claim is not covered. Recall is therefore "of every claim that
    really should be denied, how many did the run deny".
    """
    rows, flag_rows, finding_rows = [], [], []
    by_branch = {}
    inconsistent = 0
    month_inconsistent = 0
    caught = missed = 0
    for claim_ref, g in sorted(golds.items()):
        want = _cv(g.get("coverage_plan"), g.get("months_in_service"), g.get("odometer_miles"),
                   g.get("failed_component"), g.get("claimed_labor_op"),
                   g.get("narrative_finding"))
        rec = records.get(claim_ref) or {}
        got = (rec.get("covered") or {}).get("value")
        branch = deciding_branch(g)
        rows.append({"doc": claim_ref, "want": want, "got": got, "verdict": None,
                     "branch": branch, "needs_review": bool(flags.get(claim_ref))})

        b = by_branch.setdefault(branch, {"of": 0, "hit": 0, "unanswered": 0})
        b["of"] += 1
        if got not in ("yes", "no"):
            b["unanswered"] += 1
        elif got == want:
            b["hit"] += 1

        # narrative_finding on its own -- the only field that is READ rather than copied.
        finding_rows.append({"doc": claim_ref,
                             "want": g.get("narrative_finding"),
                             "got": (rec.get("narrative_finding") or {}).get("value"),
                             "cause_code": g.get("cause_code")})

        want_flag = _compute({"covered": want, "claim_status": g.get("claim_status")})
        got_flag = flags.get(claim_ref)
        flag_rows.append({"doc": claim_ref,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # Diagnostic 1: does the reply's own verdict survive the same rule re-run over the reply's
        # own values? No gold is used here -- that is the whole point of reporting it.
        self_check = _cv((rec.get("coverage_plan") or {}).get("value"),
                         (rec.get("months_in_service") or {}).get("value"),
                         (rec.get("odometer_miles") or {}).get("value"),
                         (rec.get("failed_component") or {}).get("value"),
                         (rec.get("claimed_labor_op") or {}).get("value"),
                         (rec.get("narrative_finding") or {}).get("value"))
        if self_check is not None and got in ("yes", "no") and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

        # Diagnostic 2: does the reply's stated months_in_service survive the date arithmetic
        # re-run over the reply's OWN two dates?
        m_self = _months((rec.get("in_service_date") or {}).get("value"),
                         (rec.get("repair_date") or {}).get("value"))
        m_got = (rec.get("months_in_service") or {}).get("value")
        if m_self is not None and isinstance(m_got, (int, float)) and m_self != m_got:
            month_inconsistent += 1

    matrix = _matrix(rows, "no")
    flag_matrix = _matrix(flag_rows, "yes")

    f_answered = sum(1 for r in finding_rows if r["got"] is not None)
    f_hit = sum(1 for r in finding_rows if norm(r["got"]) == norm(r["want"]))
    # The records the coded cause disagrees with the narrative on -- the ones the shortcut fails.
    _cause_for = {"defect": "defect", "collision_damage": "damage",
                  "unauthorized_modification": "modification",
                  "missed_maintenance": "maintenance"}
    trap = [r for r in finding_rows if r["cause_code"] != _cause_for.get(r["want"])]
    trap_hit = sum(1 for r in trap if norm(r["got"]) == norm(r["want"]))

    for b in by_branch.values():
        b["accuracy"] = round(b["hit"] / b["of"], 4) if b["of"] else None

    return {
        "positive_class": "no (the claim is not covered)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "by_branch": by_branch,
        "narrative_finding": {
            "of": len(finding_rows), "answered": f_answered, "hit": f_hit,
            "accuracy": round(f_hit / len(finding_rows), 4) if finding_rows else None,
            "cause_code_trap_of": len(trap), "cause_code_trap_hit": trap_hit,
            "cause_code_trap_accuracy": round(trap_hit / len(trap), 4) if trap else None,
            "note": "The only extracted field whose answer is not written anywhere in the record. "
                    "The trap subset is the rows where the CODED Cause Code disagrees with what "
                    "the narrative describes -- a reply that copies the coded field scores 0 on "
                    "them by construction.",
        },
        "review_flag": dict(flag_matrix, positive_class="yes (not covered and already paid)",
                            note="needs_review compares the run's own covered and claim_status "
                                 "against the same two-boolean rule run over GOLD's values. It is "
                                 "a business condition, so it needs labels -- unlike the "
                                 "consistency diagnostics below, which do not.",
                            rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "replies_disagreeing_with_own_dates": month_inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "DIAGNOSTICS, NOT THIS KIT'S GUARDRAIL. The first re-runs the six-branch "
                    "coverage rule over the run's OWN extracted values and counts the replies "
                    "whose stated verdict disagrees with it; the second re-runs the month "
                    "arithmetic over the run's OWN two dates. Both use no gold, so a forker can "
                    "compute them on unlabelled claims -- but both are blind to a reply that "
                    "misreads a value and then judges that misreading correctly.",
        },
        "rows": rows,
    }
