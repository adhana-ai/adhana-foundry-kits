"""Score a filing pre-check run. PURE CODE -- gold is exact and the answer is one value per cell,
so `==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(pack, field) exact match, the extraction grade -- including the ARITHMETIC cells, which are
   pulled out and reported on their own because "did it add the right entries up" is a different
   question from "did it copy the right identifier";
2. DEFECT DETECTION. Of the defects this corpus seeded, how many did the run name? Reported as
   recall and precision over defect codes, plus a per-code breakdown, plus the share of packs whose
   defect set the run reproduced EXACTLY;
3. ⚑ THE FALSE-ALARM RATE, AND IT IS THE HEADLINE OF THIS KIT. Of the packs with nothing wrong with
   them, on what share did the run raise a defect anyway? A QC queue that cries wolf is worse than
   no queue at all, because a person has to clear every row it produces, and the first thing a team
   does with a queue full of noise is stop reading it. It is reported first, in its own block, with
   its own denominator, and it is never averaged into an accuracy figure where it disappears;
4. a confusion matrix on the pure-code `needs_recompute` flag against the same rule computed from
   GOLD's own defect list -- "does this filing have to go back to the preparer". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `defects_found` disagrees with
the rulebook re-run over the model's OWN extracted values. That needs no gold, so it is the one
figure here a forker can still compute on packs nobody has labelled -- it is reported, and it is
deliberately not called a guardrail, because this kit's guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. The rulebook is invented and is not an authority; a run that scores 100 pct
here has agreed with `data/rulebook.json`, which is a different and much smaller claim than being
right about a real filing.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import defect_set as _defect_set

# The three fields that are LISTS wearing a string's clothes. Comparing them as raw strings would
# score a correct answer wrong for putting two codes in the other order, which is a scoring defect
# and not a model one.
LIST_FIELDS = ("defects_found", "missing_identification_elements", "miscoded_transaction_ids")

# The cells that are ARITHMETIC rather than transcription. Pulled out and reported separately
# because a kit whose whole job is re-adding a cage log should say how often it adds correctly,
# rather than burying two cells in a fourteen-field average.
ARITHMETIC_FIELDS = ("draft_reported_total", "log_qualifying_total")


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _tokens(v):
    n = norm(v)
    if n is None:
        return None
    return tuple(sorted(t.strip() for t in n.replace(";", ",").split(",") if t.strip()))


def equal(field, got, want):
    name = field["name"] if isinstance(field, dict) else field
    if name in LIST_FIELDS:
        return _tokens(got) == _tokens(want)
    g, w = norm(got), norm(want)
    return g == w


def score(fields, records, golds):
    """Six fields in this corpus are legitimately null on some packs -- there is often no linked
    record, no missing identification element and no mis-coded transaction, and on the packs whose
    total cannot be computed there is no qualifying total either. A null is a `hit` when gold
    agrees, never a `miss` by default the way a corpus with no nullable fields would treat any null.
    A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned
    something else).
    """
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
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
            d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)
    hallucinated = sum(1 for c in cells if c["verdict"] == "wrong" and not c["stated"])

    arith = [c for c in cells if c["field"] in ARITHMETIC_FIELDS]
    arith_hit = sum(1 for c in arith if c["verdict"] == "hit")

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
            "non_spannable_fields": sorted({f["name"] for f in fields
                                            if not f.get("spannable", f.get("type") != "enum")}),
            "span_rate": round(spanned / valued, 4) if valued else None,
            "arithmetic_cells": len(arith),
            "arithmetic_correct": arith_hit,
            "arithmetic_accuracy_pct": (round(100.0 * arith_hit / len(arith), 2)
                                        if arith else None),
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a model that answers nothing score as a careful one, so an unanswered row is
    counted on its own and never as a correct call -- which on a QC queue is the whole difference
    between a filing nobody checked and a filing somebody passed.
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


def score_defects(records, flags, golds):
    """Defect detection, the false-alarm rate, the recompute flag and the no-gold diagnostic.

    records: {case_id: {field: {value,...}}} from the run.
    flags:   {case_id: needs_recompute_or_None} from the run's own pure code.
    golds:   {case_id: gold dict}. Gold's defect list is re-derived here by the SAME rulebook pass
             the kit publishes, and gold's needs_recompute by the SAME rule src/extract.py applies
             -- so neither truth this grades against is a separately-typed label that could drift
             from the code.
    """
    rows, flag_rows = [], []
    per_code = {c: {"seeded": 0, "found": 0, "false_alarm": 0} for c in RB.DEFECTS}
    exact = 0
    answered = 0
    tp = fp = fn_ = 0
    clean_rows, clean_false_alarm = 0, []
    inconsistent = 0
    caught = missed = 0
    misses = []

    for case_id, g in sorted(golds.items()):
        want = _defect_set(g.get("defects_found"))
        want = set() if want is None else want
        rec = records.get(case_id) or {}
        got = _defect_set((rec.get("defects_found") or {}).get("value"))

        rows.append({"doc": case_id, "want": sorted(want),
                     "got": None if got is None else sorted(got),
                     "correct": (got is not None and got == want)})
        if got is not None:
            answered += 1
            if got == want:
                exact += 1
            tp += len(want & got)
            fp += len(got - want)
            fn_ += len(want - got)
            for c in (want - got):
                misses.append({"doc": case_id, "missed": c})
        else:
            fn_ += len(want)
            for c in want:
                misses.append({"doc": case_id, "missed": c, "unanswered": True})

        for c in want:
            per_code[c]["seeded"] += 1
            if got is not None and c in got:
                per_code[c]["found"] += 1
        if got is not None:
            for c in (got - want):
                if c in per_code:
                    per_code[c]["false_alarm"] += 1

        # ⚑ THE FALSE-ALARM DENOMINATOR IS THE CLEAN PACKS AND ONLY THE CLEAN PACKS. A defect
        # raised on a pack that already has a different real defect costs the queue nothing extra
        # -- the row was going to be opened anyway. A defect raised on a filing with nothing wrong
        # with it is a row that never needed to exist, and that is the cost this number measures.
        if not want:
            clean_rows += 1
            if got:
                clean_false_alarm.append({"doc": case_id, "flagged": sorted(got)})

        want_flag = _compute({"defects_found": g.get("defects_found")})
        got_flag = flags.get(case_id)
        flag_rows.append({"doc": case_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own defect list survive the rulebook re-run over the
        # reply's own values? No gold is used here -- that is the whole point of reporting it.
        self_check = set(RB.defects_of({k: (rec.get(k) or {}).get("value")
                                        for k in ("draft_reported_total", "log_qualifying_total",
                                                  "draft_window_applied", "linked_record_id",
                                                  "draft_includes_linked_record",
                                                  "missing_identification_elements",
                                                  "identification_captured_on", "gaming_day",
                                                  "miscoded_transaction_ids")}))
        if got is not None and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    n = len(rows) or 1
    flag_matrix = _matrix(flag_rows, "yes")

    insufficient_seeded = per_code["insufficient_information"]["seeded"]
    insufficient_found = per_code["insufficient_information"]["found"]

    return {
        "defect_set_exact": exact,
        "defect_set_rows": n,
        "defect_set_exact_pct": round(100.0 * exact / n, 2),
        "packs_unanswered": n - answered,
        "defect_true_positive": tp,
        "defect_false_positive": fp,
        "defect_false_negative": fn_,
        "defect_recall_pct": round(100.0 * tp / (tp + fn_), 2) if (tp + fn_) else None,
        "defect_precision_pct": round(100.0 * tp / (tp + fp), 2) if (tp + fp) else None,
        "defect_misses": misses,
        "per_code": per_code,
        # ⚑ THE HEADLINE BLOCK.
        "false_alarm": {
            "clean_packs": clean_rows,
            "clean_packs_flagged": len(clean_false_alarm),
            "rate_pct": (round(100.0 * len(clean_false_alarm) / clean_rows, 2)
                         if clean_rows else None),
            "rows": clean_false_alarm,
            "codes_named_that_gold_does_not_carry": fp,
            "note": "Of the packs with nothing wrong with them, the share on which this run raised "
                    "a defect anyway. A QC queue that cries wolf is worse than no queue, because a "
                    "person has to clear every row it produces. This is the number to read first.",
        },
        "insufficient_information": {
            "seeded": insufficient_seeded,
            "reached_correctly": insufficient_found,
            "recall_pct": (round(100.0 * insufficient_found / insufficient_seeded, 2)
                           if insufficient_seeded else None),
            "false_alarm": per_code["insufficient_information"]["false_alarm"],
            "note": "A pre-check that never says 'this record does not carry what the check needs' "
                    "is not cautious, it is guessing -- and a confident wrong 'clean' is the "
                    "failure that actually hurts on a filing queue. This is how often the run "
                    "reached for it when it was the right answer, and how often it reached for it "
                    "when it was not.",
        },
        "needs_recompute": dict(flag_matrix,
                                positive_class="yes (the totals must be recomputed before anyone "
                                               "submits)",
                                note="needs_recompute compares the run's own defect list against "
                                     "the same rule run over GOLD's. It is a business condition, "
                                     "so it needs labels -- unlike the consistency diagnostic "
                                     "below, which does not.",
                                rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "defect_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the rulebook over the "
                    "run's OWN extracted values and counts the replies whose stated defect list "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "packs -- but it is blind to a reply that mis-adds the log and then reasons "
                    "correctly from the wrong total, which on this kit is the commonest way to be "
                    "wrong.",
        },
        "rows": rows,
    }
