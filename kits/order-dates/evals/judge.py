"""Score a scheduling-order run. PURE CODE -- gold is exact and every answer is one value, so `==`
(with light normalisation) settles it.

Four graders, scored separately and never folded together, plus one diagnostic that is not a grade.

1. FINDING THE OBLIGATIONS. Did the run return a row for every paragraph that sets a deadline, and
   for no paragraph that does not? Recall and precision over the numbered paragraphs. An INVENTED
   obligation is counted and named on its own: on a docketing queue it is a diary entry nobody
   owes, and somebody has to clear it.

2. READING THEM. Per-(obligation, field) exact match over the seven structured values -- what must
   be done, how the paragraph fixes its date, the period, the triggering event, the event's own
   date, any stated date, and the parenthetical a party wrote. This is the reading half, and it is
   comparable to every other extraction kit in this series.

3. THE DATE. Did `due_date` land on the calendar date the shipped rulebook produces? Scored on its
   own, because an obligation found and mis-dated is a different failure from one missed
   altogether -- and it is the failure this kit exists to publish.

   ⚑ THE HEADLINE IS `found_but_misdated`: obligations where ALL SEVEN structured values are exact
   and the date is still wrong. It is the number that separates a reading problem from a counting
   problem, and no other figure here can. Beside it sits `false_dated` -- an obligation gold says
   CANNOT be dated from the four corners of the Order, given a confident date anyway. On a
   docketing queue that is the expensive direction: a blank gets chased and a date gets diarised.

4. THE PURE-CODE `undatable` FLAG, against the same rule computed from GOLD's own values -- "is
   this a row nobody can calendar yet". It is a business condition, so unlike a self-consistency
   check it genuinely needs labels, and saying so is half of what makes the number believable.

And the diagnostic: how often the run's stated `due_date` disagrees with the rulebook re-run over
the run's OWN extracted values. That needs no gold, so it is the one figure here a forker can still
compute on orders nobody has labelled -- it is reported, and it is deliberately not called a
guardrail, because this kit's guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. MV-CR-1 is invented and is not an authority; a run that scores 100 pct
here has agreed with `data/rulebook.json`, which is a different and much smaller claim than being
right about a real order.
"""
import re

from src import calendar_rules as CR
from src.extract import SCORED_SUBFIELDS, SPANNABLE_SUBFIELDS
from src.extract import compute as _compute
from src.extract import recompute as _recompute

ORDER_FIELDS = ("matter_number", "order_date")
NON_SPANNABLE = tuple(f for f in SCORED_SUBFIELDS if f not in SPANNABLE_SUBFIELDS)


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(got, want):
    g, w = norm(got), norm(want)
    # A period the model returned as "30" and gold holds as 30 is the same period. Nothing else is
    # coerced -- a date is compared as the string it is, so "2027-3-4" is not "2027-03-04".
    if isinstance(w, int) and isinstance(g, str) and g.isdigit():
        g = int(g)
    return g == w


def _cell(got, want):
    if equal(got, want):
        return "hit"
    if norm(got) is None:
        return "miss"
    return "wrong"


def score(fields, records, golds):
    """The reading half. Order-level fields plus the seven structured values of every GOLD
    obligation, joined on the paragraph number.

    ⚠︎ A GOLD OBLIGATION THE RUN NEVER RETURNED SCORES SEVEN MISSES, NOT NOTHING. Dropping it would
    let a run that returns two of six obligations score as well as one that returns all six, which
    on a docketing queue is the difference between a calendar and a sample of one.
    """
    by_field, cells = {}, []

    def add(doc, para, name, got, want, span=None, spannable=True):
        v = _cell(got, want)
        cells.append({"doc": doc, "paragraph": para, "field": name, "verdict": v,
                      "got": got, "want": want, "stated": want is not None,
                      "span": bool(span), "spannable": spannable})
        d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
        d[v] += 1

    for order_id, g in sorted(golds.items()):
        rec = records.get(order_id) or {}
        for name in ORDER_FIELDS:
            cell = rec.get(name) or {}
            add(order_id, None, name, cell.get("value"), g.get(name),
                span=cell.get("span"), spannable=bool(cell.get("spannable", name != "order_date")))

        rows = {r.get("paragraph"): r for r in (rec.get("deadlines") or [])
                if r.get("paragraph") is not None}
        for d in g["deadlines"]:
            r = rows.get(d["paragraph"]) or {}
            spans = r.get("spans") or {}
            for name in SCORED_SUBFIELDS:
                add(order_id, d["paragraph"], name, r.get(name), d.get(name),
                    span=spans.get(name), spannable=(name in SPANNABLE_SUBFIELDS))

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
            "non_spannable_fields": sorted(set(NON_SPANNABLE) | {"order_date"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A ROW THAT WAS NEVER ANSWERED IS NOT A NEGATIVE. Folding an unreturned obligation into "true
    negative" would let a run that returns nothing score as a careful one, so an unanswered row is
    counted on its own and never as a correct call.
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


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def score_dates(records, golds, cells):
    """Finding, dating and the undatable flag. `cells` is score()'s own cell list, so
    `found_but_misdated` is computed from the SAME comparisons the extraction grade used rather
    than from a second, subtly different one."""
    cell_ok = {}
    for c in cells:
        if c["paragraph"] is None:
            continue
        key = (c["doc"], c["paragraph"])
        cell_ok[key] = cell_ok.get(key, True) and (c["verdict"] == "hit")

    found = missed = invented = 0
    invented_struck = invented_noise = 0
    date_rows = date_correct = 0
    unanswered_rows = 0
    found_but_misdated = []
    false_dated = []
    undatable_rows_gold = undatable_answered_null = 0
    flag_rows, by_bucket = [], {}
    inconsistent = caught = missed_by_diagnostic = 0
    misdated_examples = []

    for order_id, g in sorted(golds.items()):
        rec = records.get(order_id) or {}
        rows = {r.get("paragraph"): r for r in (rec.get("deadlines") or [])
                if r.get("paragraph") is not None}
        gold_paras = {d["paragraph"] for d in g["deadlines"]}
        struck = set(g.get("struck_paragraphs") or [])

        for p in sorted(set(rows) - gold_paras):
            invented += 1
            if p in struck:
                invented_struck += 1
            else:
                invented_noise += 1
        missed += len(gold_paras - set(rows))
        found += len(gold_paras & set(rows))

        for d in g["deadlines"]:
            r = rows.get(d["paragraph"])
            want = d["due_date"]
            got = r.get("due_date") if r else None
            got = None if got in ("", "null", "None") else got
            date_rows += 1
            answered = r is not None
            if not answered:
                unanswered_rows += 1
            ok = answered and got == want
            if ok:
                date_correct += 1

            b = d.get("bucket") or "unknown"
            bb = by_bucket.setdefault(b, {"rows": 0, "correct": 0})
            bb["rows"] += 1
            bb["correct"] += 1 if ok else 0

            if answered and not ok and cell_ok.get((order_id, d["paragraph"]), False):
                found_but_misdated.append({"doc": order_id, "paragraph": d["paragraph"],
                                           "bucket": b, "gold": want, "model": got})
            if answered and not ok and len(misdated_examples) < 40:
                misdated_examples.append({"doc": order_id, "paragraph": d["paragraph"],
                                          "bucket": b, "gold": want, "model": got,
                                          "fields_all_correct":
                                              cell_ok.get((order_id, d["paragraph"]), False)})
            if want is None:
                undatable_rows_gold += 1
                if answered and got is None:
                    undatable_answered_null += 1
                if answered and got is not None:
                    false_dated.append({"doc": order_id, "paragraph": d["paragraph"],
                                        "model": got})

            want_flag = _compute(d)
            got_flag = r.get("undatable") if r else None
            flag_rows.append({"doc": order_id, "paragraph": d["paragraph"],
                              "want": None if want_flag is None else ("yes" if want_flag else "no"),
                              "got": None if got_flag is None else ("yes" if got_flag else "no"),
                              "verdict": None})

            # The diagnostic: does the reply's own date survive the rulebook re-run over the
            # reply's OWN values? No gold is used here -- that is the whole point of reporting it.
            if answered:
                self_check = _recompute(r, (rec.get("order_date") or {}).get("value"))
                if self_check != got:
                    inconsistent += 1
                    if not ok:
                        caught += 1
                elif not ok:
                    missed_by_diagnostic += 1

    n_gold = sum(len(g["deadlines"]) for g in golds.values())
    n_returned = found + invented
    flag_matrix = _matrix(flag_rows, "yes")
    all_fields_ok = sum(1 for k, v in cell_ok.items() if v)

    return {
        "obligations_in_gold": n_gold,
        "obligations_returned": n_returned,
        "obligations_found": found,
        "obligations_missed": missed,
        "invented_obligations": invented,
        "invented_from_struck_paragraphs": invented_struck,
        "invented_from_other_paragraphs": invented_noise,
        "obligation_recall_pct": _pct(found, n_gold),
        "obligation_precision_pct": _pct(found, n_returned),

        "date_rows": date_rows,
        "date_correct": date_correct,
        "date_unanswered": unanswered_rows,
        "date_accuracy_pct": _pct(date_correct, date_rows),
        "date_accuracy_by_bucket": {k: dict(v, pct=_pct(v["correct"], v["rows"]))
                                    for k, v in sorted(by_bucket.items())},

        "rows_with_every_field_correct": all_fields_ok,
        "found_but_misdated_count": len(found_but_misdated),
        "found_but_misdated_pct": _pct(len(found_but_misdated), all_fields_ok),
        "found_but_misdated": found_but_misdated,
        "misdated_examples": misdated_examples,

        "undatable_rows_in_gold": undatable_rows_gold,
        "undatable_answered_null": undatable_answered_null,
        "undatable_recall_pct": _pct(undatable_answered_null, undatable_rows_gold),
        "false_dated_count": len(false_dated),
        "false_dated_rate_pct": _pct(len(false_dated), undatable_rows_gold),
        "false_dated": false_dated,

        "undatable_flag": dict(flag_matrix,
                               positive_class="yes (nothing on the face of the Order dates this "
                                              "obligation)",
                               note="The pure-code flag compares the run's own basis, trigger and "
                                    "event date against the same rule run over GOLD's values. It "
                                    "is a business condition, so it needs labels -- unlike the "
                                    "consistency diagnostic below, which does not.",
                               rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "date_errors": caught + missed_by_diagnostic,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed_by_diagnostic,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the shipped rulebook over "
                    "each row's OWN extracted values and counts the rows whose stated due_date "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "orders -- and it is blind to a row that misreads the period or the event date "
                    "and then counts correctly from the misreading.",
        },
    }
