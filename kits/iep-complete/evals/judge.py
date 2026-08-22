"""Score a completeness-check run. PURE CODE -- gold is exact and the answer is one value per cell,
so `==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(plan, field) exact match across all fourteen fields, the extraction grade;
2. THE COMPONENT STATE, scored on its own over the seven component cells per plan -- because that
   subset is where the whole difficulty is, and averaging it into the fourteen-field figure would
   let a run that copies four identifiers correctly carry a run that cannot read a goal. It carries
   THIS KIT'S HEADLINE NUMBER: of every component that is PRESENT AND NOT MEASURABLE, how many did
   the run wave through as complete. That is `passed_unmeasurable`, and it is counted and named
   separately rather than averaged into an accuracy where it disappears;
3. THE FALSE-DEFECT RATE, the other direction and never subtracted from the first. A worklist that
   raises defects on sound components is worse than no worklist, because a person has to clear
   every row -- and the commonest way to produce one here is to tick seven boxes on a plan whose
   pupil is below the rulebook's transition age, where the seventh component was never required;
4. the plan OUTCOME, four-way and collapsed onto the one distinction a reviewer acts on (does this
   plan need work at all), plus a confusion matrix on the pure-code `on_worklist` flag against the
   same rule computed from GOLD's own values.

And one diagnostic that is not a grade: how often the reply's stated `plan_outcome` disagrees with
the rulebook re-run over the reply's OWN seven states. That needs no gold, so it is the one figure
here a forker can still compute on plans nobody has labelled -- it is reported, and it is
deliberately not called a guardrail, because this kit's guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. The rulebook is invented and is not an authority; a run that scores 100 pct
here has agreed with `data/rulebook.json`, which is a different and much smaller claim than being
right about a real plan.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import correct_outcome as _outcome_of

# The two states that put NOTHING on a reviewer's worklist. Naming the set rather than testing
# `== "present_complete"` is what makes `not_required` count as a clearance on both sides of every
# matrix below -- awarded wrongly it is a free exit from a real requirement, and a grader that only
# looked for `present_complete` would score that exit as a miss of a different kind.
CLEARED = ("present_complete", "not_required")
NEEDS_WORK = ("absent", "present_not_measurable")


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


def score(fields, records, golds):
    """`pupil_age` is the one legitimately-null field in this corpus -- null exactly where the plan
    says the age is not stated. A null there is a `hit`, not a `miss`, when gold agrees. A cell is a
    `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned something else).
    """
    by_field, cells = {}, []
    for plan_id, rec in sorted(records.items()):
        g = golds.get(plan_id) or {}
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
            cells.append({"doc": plan_id, "field": name, "verdict": v, "got": got, "want": want,
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
    negative" would let a model that answers nothing score as a careful one, so an unanswered row is
    counted on its own and never as a correct call -- which on a worklist is the whole difference
    between a plan nobody cleared and a plan somebody cleared.
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
    """The component states, the plan outcome and the worklist flag, all scored against gold, plus
    the no-gold consistency diagnostic.

    records: {plan_id: {field: {value,...}}} from the run.
    flags:   {plan_id: on_worklist_or_None} from the run's own pure code.
    golds:   {plan_id: gold dict}. Gold's outcome is re-derived here by the SAME rulebook lookup the
             kit publishes, and gold's on_worklist by the SAME rule src/extract.py applies -- so
             neither truth this grades against is a separately-typed label that could drift from
             the code.
    """
    comp_cells, defect_rows = [], []
    passed_unmeasurable, missed_absent, false_defect = [], [], []
    comp_confusion = {}

    rows, needs_rows, flag_rows = [], [], []
    confusion = {}
    inconsistent = 0
    caught = missed = 0
    unaddressed = []          # a plan needing work that the run called complete

    for plan_id, g in sorted(golds.items()):
        rec = records.get(plan_id) or {}

        # ---- layer one: the seven component states ------------------------------------------
        for key in RB.COMPONENTS:
            want = g.get(key)
            got = (rec.get(key) or {}).get("value")
            got = got if got in RB.STATES else None
            comp_cells.append({"doc": plan_id, "component": key, "want": want, "got": got,
                               "correct": got is not None and got == want})
            comp_confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
            comp_confusion[want][got or "unanswered"] += 1

            if want == "present_not_measurable" and got in CLEARED:
                passed_unmeasurable.append({"doc": plan_id, "component": key, "model": got})
            if want == "absent" and got in CLEARED:
                missed_absent.append({"doc": plan_id, "component": key, "model": got})
            if want in CLEARED and got in NEEDS_WORK:
                false_defect.append({"doc": plan_id, "component": key, "gold": want, "model": got})

            defect_rows.append({"doc": "%s:%s" % (plan_id, key),
                                "want": "yes" if want in NEEDS_WORK else "no",
                                "got": None if got is None else
                                       ("yes" if got in NEEDS_WORK else "no"),
                                "verdict": None})

        # ---- layer two: the plan outcome -----------------------------------------------------
        want_outcome = _outcome_of(g)
        got_outcome = (rec.get("plan_outcome") or {}).get("value")
        got_outcome = got_outcome if got_outcome in RB.OUTCOMES else None

        rows.append({"doc": plan_id, "want": want_outcome, "got": got_outcome,
                     "correct": (got_outcome is not None and got_outcome == want_outcome)})
        confusion.setdefault(want_outcome, {}).setdefault(got_outcome or "unanswered", 0)
        confusion[want_outcome][got_outcome or "unanswered"] += 1

        # ⚑ THE DISTINCTION A REVIEWER ACTS ON. Everything that is not `complete` means "somebody
        # has to open this plan" -- write the missing section, rewrite the goal, or go and find the
        # pupil's age. Collapsing the four classes onto that one distinction is what makes a false
        # negative nameable.
        want_needs = "yes" if want_outcome != "complete" else "no"
        got_needs = None if got_outcome is None else ("yes" if got_outcome != "complete" else "no")
        needs_rows.append({"doc": plan_id, "want": want_needs, "got": got_needs, "verdict": None})
        if want_needs == "yes" and got_needs == "no":
            unaddressed.append({"doc": plan_id, "gold": want_outcome, "model": got_outcome})

        want_flag = _compute({"plan_outcome": want_outcome, "plan_status": g.get("plan_status")})
        got_flag = flags.get(plan_id)
        flag_rows.append({"doc": plan_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own outcome survive the rulebook re-run over the reply's
        # own states? No gold is used here -- that is the whole point of reporting it.
        self_check = _outcome_of({k: (rec.get(k) or {}).get("value")
                                  for k in list(RB.COMPONENTS) + ["pupil_age"]})
        if self_check is not None and got_outcome is not None and self_check != got_outcome:
            inconsistent += 1
            if got_outcome != want_outcome:
                caught += 1
        elif got_outcome != want_outcome:
            missed += 1

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    needs = _matrix(needs_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    defect_matrix = _matrix(defect_rows, "yes")
    n_must_flag = sum(1 for r in needs_rows if r["want"] == "yes")

    n_comp = len(comp_cells) or 1
    n_comp_correct = sum(1 for c in comp_cells if c["correct"])
    n_unmeasurable = sum(1 for c in comp_cells if c["want"] == "present_not_measurable")
    n_absent = sum(1 for c in comp_cells if c["want"] == "absent")
    n_cleared = sum(1 for c in comp_cells if c["want"] in CLEARED)

    return {
        "component_cells": n_comp,
        "component_correct": n_comp_correct,
        "component_accuracy": round(n_comp_correct / n_comp, 4),
        "component_confusion": comp_confusion,
        "component_defect_detection": dict(
            defect_matrix,
            positive_class="yes (this component needs work: absent, or present and not measurable)",
            note="Every (plan, component) pair, collapsed onto the one question a worklist row "
                 "answers. A false negative is a component the rulebook would have flagged and the "
                 "run cleared; a false positive is a row somebody has to clear for nothing."),
        "passed_unmeasurable": passed_unmeasurable,
        "passed_unmeasurable_count": len(passed_unmeasurable),
        "passed_unmeasurable_of": n_unmeasurable,
        "passed_unmeasurable_rate_pct": (round(100.0 * len(passed_unmeasurable) / n_unmeasurable, 2)
                                         if n_unmeasurable else None),
        "missed_absent": missed_absent,
        "missed_absent_count": len(missed_absent),
        "missed_absent_of": n_absent,
        "missed_absent_rate_pct": (round(100.0 * len(missed_absent) / n_absent, 2)
                                   if n_absent else None),
        "false_defect": false_defect,
        "false_defect_count": len(false_defect),
        "false_defect_of": n_cleared,
        "false_defect_rate_pct": (round(100.0 * len(false_defect) / n_cleared, 2)
                                  if n_cleared else None),
        "plan_outcome_accuracy": round(n_correct / n, 4),
        "plan_outcome_correct": n_correct,
        "plan_outcome_rows": n,
        "plan_outcome_unanswered": n_unanswered,
        "confusion": confusion,
        "needs_work": dict(needs,
                           positive_class="yes (somebody has to open this plan)",
                           note="The four-way outcome collapsed onto the one distinction a "
                                "reviewer acts on. A false negative here is a plan the shipped "
                                "rulebook would have put on the worklist and the run cleared.",
                           rows=needs_rows),
        "unaddressed": unaddressed,
        "unaddressed_count": len(unaddressed),
        "unaddressed_rate_pct": (round(100.0 * len(unaddressed) / n_must_flag, 2)
                                 if n_must_flag else None),
        "worklist_flag": dict(flag_matrix,
                              positive_class="yes (not complete and already in effect)",
                              note="on_worklist compares the run's own outcome and plan_status "
                                   "against the same rule run over GOLD's values. It is a business "
                                   "condition, so it needs labels -- unlike the consistency "
                                   "diagnostic below, which does not.",
                              rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "outcome_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the rulebook over the "
                    "run's OWN seven component states and counts the replies whose stated outcome "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "plans -- but it is blind to the failure this kit cares about most: a reply "
                    "that calls an unmeasurable goal complete and then computes the outcome "
                    "perfectly from that reading is entirely self-consistent and entirely wrong.",
        },
        "rows": rows,
    }
