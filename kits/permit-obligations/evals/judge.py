"""Score a register-reading run. PURE CODE -- gold is exact and every answer is one value, so `==`
(with light normalisation) settles it.

⚑ FOUR THINGS ARE SCORED SEPARATELY AND NEVER FOLDED TOGETHER, because on a monitor they are four
different failures and three of them are invisible inside an accuracy figure:

1. FIELD EXTRACTION -- the reading half, comparable to every other kit in this series. Its
   denominator is every fact printed on every register, so a condition block the run never returned
   costs its eight cells rather than quietly leaving the denominator smaller.
2. THE STATUS VERDICT -- the deciding half. Five-way exact: overdue / due_in_window / not_yet_due /
   not_binding / not_determinable. THE MODEL NEVER ANSWERS THIS. It is computed by
   src/rulebook.py::decide() over the model's OWN extracted values, and compared against the same
   function run over gold's. Every error here is therefore an inherited reading error, which is the
   honest thing to publish about a monitor of this shape.
3. DATE ARITHMETIC -- the due date, on the rows where one is DERIVED rather than stated (a cycle
   dated from the last recorded entry, or an annual report dated from the period it was credited
   to). An obligation found but mis-dated is a different failure from one missed entirely, and an
   accuracy figure cannot tell them apart.
4. THE FALSE-ALARM RATE -- ⚑ THE NUMBER THAT MATTERS MOST HERE, and it is in the headline rather
   than a footnote. A monitoring queue that cries wolf is worse than no queue, because a person has
   to clear every row on it by hand and the cost falls on them every single day. It is defined
   against the worklist the kit actually proposes: of the obligations this run put in front of
   somebody, what share did not need to be there.

And its mirror, published beside it and never averaged into it: MISSED ACTIONS -- obligations that
needed action and the run left off the list.

One diagnostic that is not a grade: how often the SITE'S OWN register flag disagrees with the
computed status. It needs no gold at all, so it is the one figure here a forker can compute on
registers nobody has labelled. It is reported, and it is deliberately not called a guardrail --
this kit's guardrail is the escalation condition in src/extract.py::compute().

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run read the register
the shipped rulebook is applied to. The rulebook is illustrative and is not an authority; a run that
scores 100 pct here has agreed with data/rulebook.json, which is a different and much smaller claim
than being right about a real permit.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(field, got, want):
    return norm(got) == norm(want)


def _flat(gold_ob):
    """A gold obligation reduced to the recorded values a reply is scored against."""
    return {k: gold_ob.get(k) for k in
            ("condition_id", "obligation_type", "condition_state", "last_done",
             "period_credited", "stated_due", "trigger_state", "register_flag")}


def _derived(gold_ob):
    """Is this row's gold due date DERIVED by arithmetic rather than read off the page?

    Cycle rows are dated from the last recorded entry; annual reports from the period credited.
    An event-triggered row's due date is STATED on the register, so it is a reading and belongs to
    grader 1 -- counting it here would flatter the arithmetic figure with cells that involve none.
    """
    spec = RB.TYPES.get(gold_ob.get("obligation_type")) or {}
    return spec.get("basis") in ("cycle", "reporting_period")


def score(fields, ob_fields, records, golds):
    """Grader 1: per-cell exact match over every fact printed on every register.

    THREE NULLABLE FIELDS, and each null is a STATED fact rather than a convenience:
      last_done        null where the register says the entry was logged with no date, and on every
                       event-triggered row, where the line says it does not apply;
      period_credited  null on everything that is not an annual report;
      stated_due       null wherever the register states no date.
    A null that matches gold is a `hit`, never a `miss` by default.

    ⚠︎ THE DENOMINATOR IS GOLD'S, NOT THE REPLY'S. A condition block the run never returned scores
    its eight cells as misses rather than shrinking the denominator, because on a monitoring queue
    a row nobody returned and a row nobody needed look identical in every rate that quietly drops
    it. `row_recall_pct` is published beside this so a reader can tell a cell problem from a row
    problem.
    """
    by_field, cells = {}, []
    rows_expected = rows_found = spurious = 0
    spurious_ids = []

    for reg_id, g in sorted(golds.items()):
        rec = records.get(reg_id) or {}
        got_top = rec.get("fields") or {}
        for f in fields:
            name = f["name"]
            got = (got_top.get(name) or {}).get("value")
            want = g.get(name)
            cells.append(_cell_row(reg_id, None, f, got, want,
                                   (got_top.get(name) or {}).get("span"),
                                   (got_top.get(name) or {}).get("spannable", True), by_field))

        got_rows = {o.get("condition_id"): o for o in (rec.get("obligations") or [])
                    if o.get("condition_id")}
        gold_rows = {o["condition_id"]: o for o in g.get("obligations") or []}
        rows_expected += len(gold_rows)
        rows_found += len(set(got_rows) & set(gold_rows))
        extra = sorted(set(got_rows) - set(gold_rows))
        spurious += len(extra)
        spurious_ids += ["%s/%s" % (reg_id, c) for c in extra]

        for cid, gob in sorted(gold_rows.items()):
            cellmap = (got_rows.get(cid) or {}).get("cells") or {}
            for f in ob_fields:
                name = f["name"]
                cell = cellmap.get(name) or {}
                cells.append(_cell_row(reg_id, cid, f, cell.get("value"), gob.get(name),
                                       cell.get("span"), cell.get("spannable", True), by_field))

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)
    hallucinated = sum(1 for c in cells if c["verdict"] == "wrong" and not c["stated"])
    enums = sorted({f["name"] for f in list(fields) + list(ob_fields) if f.get("type") == "enum"})

    return {
        "by_field": by_field,
        "cells": cells,
        "rows": {"expected": rows_expected, "found": rows_found,
                 "missing": rows_expected - rows_found, "spurious": spurious,
                 "spurious_ids": spurious_ids[:40],
                 "row_recall_pct": round(100.0 * rows_found / rows_expected, 2)
                                   if rows_expected else None},
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": hallucinated,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": enums,
            "span_rate": round(spanned / valued, 4) if valued else None,
            "row_recall_pct": round(100.0 * rows_found / rows_expected, 2)
                              if rows_expected else None,
            "spurious_row_count": spurious,
        },
    }


def _cell_row(reg_id, cid, f, got, want, span, spannable, by_field):
    if equal(f, got, want):
        v = "hit"
    elif norm(got) is None:
        v = "miss"
    else:
        v = "wrong"
    row = {"doc": reg_id, "condition": cid, "field": f["name"], "verdict": v,
           "got": got, "want": want, "stated": want is not None,
           "span": bool(span), "spannable": spannable}
    d = by_field.setdefault(f["name"], {"hit": 0, "miss": 0, "wrong": 0})
    d[v] += 1
    return row


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A ROW THAT WAS NEVER ANSWERED IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a run that returns nothing score as a careful one, so an unanswered row is
    counted on its own and never as a correct call -- which on a monitoring queue is the whole
    difference between an obligation nobody raised and an obligation nobody needed to.
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


def score_statuses(records, flags, golds):
    """Graders 2, 3 and 4, plus the escalation guardrail and the no-gold diagnostic.

    records: {register_id: the extracted record} from the run.
    flags:   {register_id: escalate_or_None} from the run's own pure code.
    golds:   {register_id: gold dict}. Gold's status and due date are re-derived here by the SAME
             rulebook lookup the kit publishes, and gold's escalate flag by the SAME rule
             src/extract.py applies -- so neither truth this grades against is a separately-typed
             label that could drift from the code.
    """
    status_rows, work_rows, nd_rows, flag_rows, date_rows = [], [], [], [], []
    confusion = {}
    false_alarms, missed = [], []
    flag_disagreements = 0
    flag_rows_total = 0

    for reg_id, g in sorted(golds.items()):
        rec = records.get(reg_id) or {}
        # ⚑ THE RUN'S OWN ANSWER IS READ OFF THE RUN, AND GOLD'S TRUTH IS RE-DERIVED HERE. That
        # asymmetry is the point: src/extract.py is where the pure-code rule actually runs, so
        # taking its answer is what makes this a grade of the shipped pipeline rather than of a
        # second implementation. It is also what lets the FREE FLOOR be scored by this same
        # function while deriving its statuses from the site's register flag instead.
        computed = {o["condition_id"]: o for o in (rec.get("obligations") or [])
                    if o.get("condition_id")}
        gold_rows = {o["condition_id"]: o for o in g.get("obligations") or []}
        seen_ids = set()

        for cid, gob in sorted(gold_rows.items()):
            seen_ids.add(cid)
            want = RB.decide(g["register_date"], _flat(gob))["status"]
            got_d = computed.get(cid)
            got = (got_d or {}).get("status")
            got = got if got in RB.STATUSES else None

            status_rows.append({"doc": reg_id, "condition": cid, "want": want, "got": got,
                                "correct": got is not None and got == want})
            confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
            confusion[want][got or "unanswered"] += 1

            # ⚑ THE HEADLINE. Everything that is `overdue` or `due_in_window` goes on somebody's
            # list today; everything else does not. Collapsing five classes onto that one
            # distinction is what makes a false alarm nameable.
            want_action = "yes" if want in RB.ACTIONABLE else "no"
            got_action = None if got is None else ("yes" if got in RB.ACTIONABLE else "no")
            work_rows.append({"doc": reg_id, "condition": cid,
                              "want": want_action, "got": got_action, "verdict": None})
            if want_action == "no" and got_action == "yes":
                false_alarms.append({"doc": reg_id, "condition": cid, "gold": want, "model": got})
            if want_action == "yes" and got_action != "yes":
                missed.append({"doc": reg_id, "condition": cid, "gold": want,
                               "model": got or "not returned"})

            # ⚑ "CANNOT DETERMINE" AS ITS OWN GRADER. A monitor that never reaches for it is not
            # cautious, it is guessing -- so how often the run reaches for it CORRECTLY is a
            # published number rather than a class hidden inside a five-way accuracy.
            nd_rows.append({"doc": reg_id, "condition": cid,
                            "want": "yes" if want == "not_determinable" else "no",
                            "got": None if got is None
                                   else ("yes" if got == "not_determinable" else "no"),
                            "verdict": None})

            # ⚑ DATE ARITHMETIC, ON THE ROWS WHERE A DUE DATE IS DERIVED. Excluded rather than
            # counted as misses: rows whose rule stops before any date (not binding, not
            # determinable, trigger not fired) and rows whose due date is stated on the page.
            gold_due = RB.decide(g["register_date"], _flat(gob))["due_date"]
            if _derived(gob) and gold_due:
                date_rows.append({"doc": reg_id, "condition": cid, "want": gold_due,
                                  "got": (got_d or {}).get("due_date"),
                                  "correct": (got_d or {}).get("due_date") == gold_due})

        # A row the run invented is on the worklist too if the rulebook makes it actionable, and
        # it is a false alarm of the worst kind: a person is sent to look at a condition the
        # register does not carry.
        for cid, d in sorted(computed.items()):
            if cid in seen_ids:
                continue
            if d.get("status") in RB.ACTIONABLE:
                work_rows.append({"doc": reg_id, "condition": cid, "want": "no", "got": "yes",
                                  "verdict": None, "spurious": True})
                false_alarms.append({"doc": reg_id, "condition": cid, "gold": "not on the register",
                                     "model": d.get("status")})

        # The diagnostic: does the SITE'S OWN flag agree with the computed status? No gold is used
        # here -- that is the whole point of reporting it.
        for cid, d in sorted(computed.items()):
            flag = None
            for o in rec.get("obligations") or []:
                if o.get("condition_id") == cid:
                    flag = (o.get("values") or {}).get("register_flag")
            if flag not in ("on track", "attention", "closed") or d.get("status") is None:
                continue
            flag_rows_total += 1
            expected = ("attention" if d["status"] in RB.ACTIONABLE
                        else "closed" if d["status"] == "not_binding" else "on track")
            if flag != expected:
                flag_disagreements += 1

        want_flag = _compute({"register_date": g["register_date"],
                              "obligations": [_flat(o) for o in g.get("obligations") or []]})
        got_flag = flags.get(reg_id)
        flag_rows.append({"doc": reg_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

    n = len(status_rows) or 1
    n_correct = sum(1 for r in status_rows if r["correct"])
    n_unanswered = sum(1 for r in status_rows if r["got"] is None)
    work = _matrix(work_rows, "yes")
    nd = _matrix(nd_rows, "yes")
    esc = _matrix(flag_rows, "yes")
    raised = work["true_positive"] + work["false_positive"]
    must_act = sum(1 for r in work_rows if r["want"] == "yes")
    n_dates = len(date_rows)
    n_dates_ok = sum(1 for r in date_rows if r["correct"])

    return {
        "status_accuracy": round(n_correct / n, 4),
        "status_correct": n_correct,
        "status_rows": n,
        "status_unanswered": n_unanswered,
        "confusion": confusion,
        "worklist": dict(work,
                         positive_class="yes (this obligation needs action today)",
                         note="The five-way status collapsed onto the one distinction a monitoring "
                              "desk acts on. A false positive here is a row somebody has to clear "
                              "by hand for nothing; a false negative is an obligation nobody "
                              "raised.",
                         rows=work_rows),
        "false_alarms": false_alarms,
        "false_alarm_count": len(false_alarms),
        "false_alarm_rate_pct": round(100.0 * len(false_alarms) / raised, 2) if raised else None,
        "worklist_raised": raised,
        "missed_actions": missed,
        "missed_action_count": len(missed),
        "missed_action_rate_pct": round(100.0 * len(missed) / must_act, 2) if must_act else None,
        "not_determinable": dict(nd,
                                 positive_class="yes (the register does not carry what the rule "
                                                "needs)",
                                 note="Scored on its own because a monitor that never says "
                                      "'cannot determine' is guessing, and a monitor that says it "
                                      "everywhere is useless. Both directions matter.",
                                 rows=nd_rows),
        "due_dates": {
            "scored": n_dates,
            "correct": n_dates_ok,
            "accuracy_pct": round(100.0 * n_dates_ok / n_dates, 2) if n_dates else None,
            "note": "Only rows where the due date is DERIVED -- a cycle dated from the last "
                    "recorded entry, or an annual report dated from the reporting period credited. "
                    "Rows whose date is stated on the register, and rows where the rule stops "
                    "before any date, are excluded rather than counted as misses.",
            "rows": [r for r in date_rows if not r["correct"]][:40],
        },
        "escalate": dict(esc,
                         positive_class="yes (something already overdue, and the site's own "
                                        "register flag is quiet about it)",
                         note="A BUSINESS CONDITION, so unlike the diagnostic below it genuinely "
                              "needs labels, and saying so is half of what makes the number "
                              "believable. It is scored against the same rule run over GOLD's own "
                              "values.",
                         rows=flag_rows),
        "register_flag_diagnostic": {
            "rows_compared": flag_rows_total,
            "disagreements": flag_disagreements,
            "disagreement_pct": round(100.0 * flag_disagreements / flag_rows_total, 2)
                                if flag_rows_total else None,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It compares the site's OWN register "
                    "flag against the status the rulebook computes from the same row, and uses no "
                    "gold at all -- so a forker can compute it on registers nobody has labelled. "
                    "It is blind to a reply that misreads a date and then computes a status "
                    "consistent with the misreading, and it says nothing about which of the two "
                    "is right when they disagree.",
        },
        "rows": status_rows,
    }
