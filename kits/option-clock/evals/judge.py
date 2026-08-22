"""Score an option-clock run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

⚑ FOUR THINGS ARE SCORED SEPARATELY AND NEVER FOLDED TOGETHER, because in a monitoring kit they
fail for different reasons and cost different amounts:

1. FIELD EXTRACTION -- per-(register, field) exact match. The reading half, comparable to every
   other kit in this series.
2. THE STATUS VERDICT -- the deciding half. `live` / `lapsing` / `lapsed` / `not_determinable`,
   counted in PURE CODE from the run's own extracted values, four-way against gold, PLUS a binary
   confusion matrix on the only distinction a worklist has: does this row need somebody today, or
   not. Two directions are named separately and never averaged:
     - FALSE ALARM: gold says the option is live and the run put it on the worklist. ⚑ THIS IS THE
       NUMBER THAT MATTERS MOST IN A MONITOR KIT. A queue that cries wolf is worse than no queue,
       because a person has to clear every row on it, and the second week they stop reading it.
     - MISSED LAPSE: gold says the option needs action and the run reported it `live`. This is the
       EXPENSIVE error -- an option nobody looked at is an option nobody exercised.
3. DATE ARITHMETIC -- the derived expiry, exact match, over the registers where an expiry can be
   counted at all. An obligation found but mis-dated is a different failure from one missed, and a
   date that is a week out on a 45-day window silently changes the status.
4. THE ESCALATION FLAG -- the pure-code business condition (not live, and still carried as live)
   against the same rule run over GOLD's own values. It is a business condition, so unlike a
   self-consistency check it genuinely needs labels, and saying so is half of what makes the number
   believable.

And two diagnostics that are not grades:
  - CONSISTENCY: how often the model's own stated `status` disagrees with the rulebook re-run over
    the model's OWN extracted values. That needs no gold, so it is the one figure here a forker can
    still compute on registers nobody has labelled.
  - NOTE-CONTRADICTION: accuracy restricted to the registers whose clerk note is written in the
    register that points the wrong way. It is a subset of the status grade, reported separately
    because "did the prose talk it out of the count" is a different question from "was it right".

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. The rulebook is illustrative and is not an authority; a run that scores
100 pct here has agreed with `data/rulebook.json`, which is a different and much smaller claim than
being right about a real option.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import counted_status as _counted
from src.extract import count as _count


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
    """option_granted_date, trigger_date and expiry_date are the three legitimately-null fields in
    this corpus -- null exactly where the register carries two disagreeing grant dates, where there
    is no triggering event or it has not occurred, and where no expiry can be counted. All three are
    a `hit` when the model matches gold, never a `miss` by default the way a corpus with no nullable
    fields would treat any null. A cell is a `hit`, a `miss` (returned nothing where gold has a
    value) or `wrong` (returned something else).
    """
    by_field, cells = {}, []
    for reg_id, rec in sorted(records.items()):
        g = golds.get(reg_id) or {}
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
            cells.append({"doc": reg_id, "field": name, "verdict": v, "got": got, "want": want,
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
            "non_spannable_fields": sorted(
                {f["name"] for f in fields
                 if f.get("type") == "enum" or f.get("spannable") is False}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a model that answers nothing score as a calm one, so an unanswered row is
    counted on its own and never as a correct call -- which on a monitoring queue is the whole
    difference between a register nobody flagged and a register somebody cleared.
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


def _values_of(rec):
    return {k: (rec.get(k) or {}).get("value") for k in rec}


def score_clock(records, published, flags, golds):
    """The published status, the published expiry, the worklist matrix and the escalation flag, all
    scored against gold, plus the two diagnostics.

    records:   {register_ref: {field: {value,...}}} from the run.
    published: {register_ref: {"status":..., "expiry_date":...}} -- THE ANSWER THE SYSTEM STANDS
               BEHIND. For a model run that is src/extract.py's pure-code COUNT over the extracted
               values; for the free floor it is the register's own status column. Scoring the
               PUBLISHED answer rather than recomputing one here is what makes the two comparable:
               a grader that silently ran the rulebook over the floor's values would be scoring a
               system that does not exist, because the floor counts nothing.
    flags:     {register_ref: escalate_now_or_None} from the run's own pure code.
    golds:     {register_ref: gold dict}. Gold's status and expiry are re-derived HERE by the SAME
               rulebook count the kit publishes, and gold's escalation flag by the SAME rule
               src/extract.py applies -- so no truth this grades against is a separately-typed
               label that could drift from the code.
    """
    rows, work_rows, flag_rows, date_rows = [], [], [], []
    confusion = {}
    inconsistent = 0
    caught = missed_diag = 0
    false_alarm, missed_lapse = [], []
    phantom_expiry, missing_expiry = [], []
    claimed_correct = claimed_rows = 0
    note_rows = note_correct = 0

    for reg_id, g in sorted(golds.items()):
        gold_count = _count(g)
        want = gold_count["status"]
        want_expiry = gold_count["expiry_date"]

        rec = records.get(reg_id) or {}
        vals = _values_of(rec)
        pub = published.get(reg_id) or {}
        got = pub.get("status") if pub.get("status") in RB.STATUSES else None
        got_expiry = pub.get("expiry_date")

        rows.append({"doc": reg_id, "want": want, "got": got,
                     "correct": (got is not None and got == want)})
        confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
        confusion[want][got or "unanswered"] += 1

        # ⚑ THE ONE DISTINCTION A WORKLIST HAS. `lapsing`, `lapsed` and `not_determinable` all mean
        # "somebody has to open this today"; only `live` means "not today". Collapsing the four
        # classes onto that is what makes both error directions nameable.
        want_work = "yes" if want in RB.NEEDS_ACTION else "no"
        got_work = None if got is None else ("yes" if got in RB.NEEDS_ACTION else "no")
        work_rows.append({"doc": reg_id, "want": want_work, "got": got_work, "verdict": None})
        if want_work == "no" and got_work == "yes":
            false_alarm.append({"doc": reg_id, "gold": want, "run": got})
        if want_work == "yes" and got_work == "no":
            missed_lapse.append({"doc": reg_id, "gold": want, "run": got})

        # ⚑ DATE ARITHMETIC, SCORED ONLY WHERE THERE IS A DATE TO GET RIGHT. A register whose clock
        # has not started has no expiry, and counting those as date failures would fold the
        # not_determinable class into the arithmetic grade twice. A date offered where gold has
        # none is counted on its own, as a phantom expiry, because inventing a due date is a
        # different and worse failure than declining to give one.
        if want_expiry is not None:
            date_rows.append({"doc": reg_id, "want": want_expiry, "got": got_expiry,
                              "correct": (got_expiry is not None
                                          and norm(got_expiry) == norm(want_expiry))})
            if got_expiry is None:
                missing_expiry.append({"doc": reg_id, "gold": want_expiry})
        elif got_expiry is not None:
            phantom_expiry.append({"doc": reg_id, "run": got_expiry})

        want_flag = _compute(want, g.get("register_status"))
        got_flag = flags.get(reg_id)
        flag_rows.append({"doc": reg_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The model's OWN stated status, scored as a claim rather than as the answer. The kit
        # publishes the counted one; this says how often the model agreed with the arithmetic it
        # was asked to do.
        claimed = (rec.get("status") or {}).get("value")
        if rec:
            claimed_rows += 1
            if claimed == want:
                claimed_correct += 1

        # The diagnostic: does the reply's own stated status survive the rulebook count re-run over
        # the reply's OWN extracted values? No gold is used here -- that is the whole point of
        # reporting it. On a system that publishes the count (this kit) the two agree by
        # construction and the diagnostic is a check on the MODEL's arithmetic; on one that
        # publishes a status column (the free floor) it is a check on the column.
        self_counted = _counted(vals) if rec else None
        if claimed in RB.STATUSES and self_counted is not None and claimed != self_counted:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed_diag += 1

        if g.get("note_register") and rec:
            contradicting = ((g["note_register"] == "calm") != (want == "live"))
            if contradicting:
                note_rows += 1
                if got == want:
                    note_correct += 1

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    work = _matrix(work_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    n_live = sum(1 for r in work_rows if r["want"] == "no")
    n_action = sum(1 for r in work_rows if r["want"] == "yes")
    n_dates = len(date_rows) or 1
    n_date_correct = sum(1 for r in date_rows if r["correct"])

    return {
        "status_accuracy": round(n_correct / n, 4),
        "status_correct": n_correct,
        "status_rows": n,
        "status_unanswered": n_unanswered,
        "confusion": confusion,
        "worklist": dict(work,
                         positive_class="yes (this option needs somebody today)",
                         note="The four-way status collapsed onto the one distinction a worklist "
                              "has. lapsing, lapsed and not_determinable are all `yes`; only live "
                              "is `no`. A false positive here is a FALSE ALARM and a false "
                              "negative is a MISSED LAPSE, and the two are named separately "
                              "because they cost different people different things.",
                         rows=work_rows),
        "false_alarm": false_alarm,
        "false_alarm_count": len(false_alarm),
        "false_alarm_rate_pct": (round(100.0 * len(false_alarm) / n_live, 2) if n_live else None),
        "false_alarm_denominator": n_live,
        "missed_lapse": missed_lapse,
        "missed_lapse_count": len(missed_lapse),
        "missed_lapse_rate_pct": (round(100.0 * len(missed_lapse) / n_action, 2)
                                  if n_action else None),
        "missed_lapse_denominator": n_action,
        "dates": {
            "rows": date_rows,
            "scored": len(date_rows),
            "correct": n_date_correct,
            "accuracy_pct": round(100.0 * n_date_correct / n_dates, 2) if date_rows else None,
            "missing_expiry": missing_expiry,
            "missing_expiry_count": len(missing_expiry),
            "phantom_expiry": phantom_expiry,
            "phantom_expiry_count": len(phantom_expiry),
            "note": "The COUNTED expiry, exact match, over the registers where an expiry can be "
                    "counted at all. A phantom expiry is a date produced for a register whose "
                    "clock the rulebook says cannot be started -- inventing a due date is worse "
                    "than declining to give one, so it is counted on its own rather than folded "
                    "in here.",
        },
        "escalate_flag": dict(flag_matrix,
                              positive_class="yes (not live, and still carried as live)",
                              note="escalate_now compares the run's own counted status and the "
                                   "register's carried status against the same rule run over "
                                   "GOLD's values. It is a business condition, so it needs labels "
                                   "-- unlike the consistency diagnostic below, which does not.",
                              rows=flag_rows),
        "claimed_status": {
            "rows": claimed_rows,
            "correct": claimed_correct,
            "accuracy_pct": (round(100.0 * claimed_correct / claimed_rows, 2)
                             if claimed_rows else None),
            "note": "The model's OWN stated status, scored as a claim. This kit publishes the "
                    "COUNTED status, not this one -- a due date is arithmetic and arithmetic done "
                    "in prose is arithmetic nobody can check. The gap between the two is the "
                    "consistency diagnostic below.",
        },
        "note_contradiction": {
            "rows": note_rows,
            "correct": note_correct,
            "accuracy_pct": (round(100.0 * note_correct / note_rows, 2) if note_rows else None),
            "note": "Counted-status accuracy restricted to the registers whose clerk note is "
                    "written in the register that points the wrong way -- a relaxed note on a "
                    "lapsed option, or a worried one on an option with two years to run.",
        },
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "status_errors": caught + missed_diag,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed_diag,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the rulebook count over "
                    "the run's OWN extracted values and counts the replies whose stated status "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "registers -- but it is blind to a reply that misreads a date or an extension "
                    "and then counts correctly from the misreading, which is exactly the failure "
                    "this corpus is built to produce.",
        },
        "rows": rows,
    }
