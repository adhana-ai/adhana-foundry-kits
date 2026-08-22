"""Score an attestation-register run. PURE CODE -- gold is exact and every answer is one value, so
`==` (with light normalisation) settles it. There is no LLM judge in this kit and there should not
be one: every question here is a date comparison or a table lookup, which is the one thing you
should never ask a model to adjudicate.

⚑ FOUR GRADERS, SCORED SEPARATELY AND NEVER FOLDED TOGETHER. A monitoring kit that publishes one
number has hidden the only number anybody acts on.

1. FIELD EXTRACTION -- per (register, person, field) exact match, plus the four register-level
   fields. The reading half, comparable to every other extraction kit in this series.
2. THE STATUS VERDICT -- the PURE-CODE rule (src/rulebook.py) run over the values the model
   returned, against gold's own status. This is the deciding half. It is not a tautology: a
   mis-read date flips a status, so this grader measures the whole pipeline rather than the rule.
3. DATE ARITHMETIC -- the MODEL'S OWN `due_on` against the derivation. No register states a due
   date; it is cycle_opened_on plus the rulebook's cycle length for the role. The model's number
   decides nothing (the kit publishes the code's), which is exactly what makes this a clean
   measurement of arithmetic rather than of copying.
4. ⚑ THE FALSE-ALARM RATE -- OF EVERY PERSON THIS KIT PUT ON THE WORKLIST, WHAT SHARE DID NOT
   BELONG THERE. This is the number that matters most in a monitoring kit and it is in the
   headline rather than a footnote. A queue that cries wolf is worse than no queue, because a human
   has to clear every row, and the row that gets a queue switched off is the partner who is chased
   about an attestation that was fine.

   It is counted STRICTLY: a false alarm is a row the kit flagged whose gold status is `satisfied`
   or `not_required` -- the two answers that mean nothing needed doing. A `not_determinable` row
   the kit flagged as `missing` is counted separately as MISROUTED, because somebody does have to
   open that file; they have to open it for a different reason.

And two more numbers that are not one of the four:

  - `not_determinable` recall and precision on their own. A monitor that never says "cannot
    determine from this record" is not cautious, it is guessing, so how often the kit reaches for
    that answer CORRECTLY is published rather than buried inside a six-way accuracy.
  - a consistency diagnostic: how often the model's own stated `status` disagrees with the rule
    re-run over the model's own extracted values. That needs no gold, so it is the one figure a
    forker can still compute on registers nobody has labelled. It is reported as a diagnostic and
    deliberately NOT called this kit's guardrail.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. That rulebook is illustrative and is not an authority; a run that scores
100 pct here has agreed with `data/rulebook.json`, which is a different and much smaller claim than
being right about a real engagement.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import attester_key, scored_attester_fields


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(field, got, want):
    return norm(got) == norm(want)


def _rows_by_ref(attesters, key="person_ref"):
    out = {}
    for a in attesters:
        ref = a.get(key)
        if ref not in (None, ""):
            out.setdefault(str(ref).strip(), a)
    return out


def score(fields, records, golds):
    """Per-cell extraction accuracy over the register fields and the per-person fields.

    ⚑ ROWS ARE ALIGNED BY `person_ref`, AND THE KEY IS NOT ITSELF A SCORED CELL. Scoring the field
    a row was matched by would make every joined row a free hit. Roster coverage is reported on its
    own instead: how many of gold's people the reply returned, and how many people it returned that
    gold does not have.

    ⚠︎ A GOLD PERSON THE REPLY NEVER MENTIONED IS TEN MISSES, NOT AN ABSENCE. Dropping somebody
    off a monitoring roster is the failure that produces a clean-looking register, so it is scored
    as ten wrong cells and a status of `unanswered`, never quietly excluded from the denominator.
    """
    key = attester_key(fields)
    att_fields = scored_attester_fields(fields)
    by_field, cells = {}, []
    roster_matched = roster_gold = roster_returned = 0

    for reg_id, rec in sorted(records.items()):
        g = golds.get(reg_id) or {}
        for f in fields["register"]:
            name = f["name"]
            got = (rec.get("register") or {}).get(name, {}).get("value")
            want = g.get(name)
            v = "hit" if equal(f, got, want) else ("miss" if norm(got) is None else "wrong")
            cells.append({"doc": reg_id, "person": None, "field": name, "verdict": v,
                          "got": got, "want": want, "stated": want is not None,
                          "span": bool((rec.get("register") or {}).get(name, {}).get("span")),
                          "spannable": (rec.get("register") or {}).get(name, {})
                                       .get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
            d[v] += 1

        got_rows = _rows_by_ref(rec.get("attesters") or [], "person_ref")
        gold_rows = _rows_by_ref(g.get("attesters") or [], key)
        roster_gold += len(gold_rows)
        roster_returned += len(got_rows)
        roster_matched += len(set(got_rows) & set(gold_rows))

        for ref, gp in sorted(gold_rows.items()):
            row = got_rows.get(ref)
            cellmap = (row or {}).get("fields") or {}
            for f in att_fields:
                name = f["name"]
                cell = cellmap.get(name) or {}
                got = cell.get("value")
                want = gp.get(name)
                v = "hit" if equal(f, got, want) else ("miss" if norm(got) is None else "wrong")
                cells.append({"doc": reg_id, "person": ref, "field": name, "verdict": v,
                              "got": got, "want": want, "stated": want is not None,
                              "span": bool(cell.get("span")),
                              "spannable": cell.get("spannable",
                                                    f.get("type") not in ("enum", "derived"))})
                d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
                d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)
    hallucinated = sum(1 for c in cells if c["verdict"] == "wrong" and not c["stated"])

    non_spannable = sorted({f["name"] for f in fields["register"] + fields["attester"]
                            if f.get("type") in ("enum", "derived")})
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
            "non_spannable_fields": non_spannable,
            "span_rate": round(spanned / valued, 4) if valued else None,
            "roster_rows_gold": roster_gold,
            "roster_rows_returned": roster_returned,
            "roster_rows_matched": roster_matched,
            "roster_recall_pct": (round(100.0 * roster_matched / roster_gold, 2)
                                  if roster_gold else None),
            "roster_hallucinated_rows": max(0, roster_returned - roster_matched),
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A ROW THAT WAS NEVER ANSWERED IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a reply that drops half the roster score as a careful one, so an unanswered
    row is counted on its own and never as a correct call -- which on a monitoring queue is the
    whole difference between a person nobody chased and a person somebody cleared.
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


NOTHING_TO_DO = ("satisfied", "not_required")


def score_statuses(fields, records, golds):
    """The status verdict, the date arithmetic, the false-alarm rate, the not-determinable reach,
    the register-level owner-review flag, and the no-gold consistency diagnostic.

    golds' status and due_on are BOTH re-derived here by the same rule the kit publishes, so
    neither truth this grades against is a separately-typed label that could drift from the code.
    """
    key = attester_key(fields)
    rows, work_rows, det_rows, flag_rows = [], [], [], []
    confusion = {}
    false_alarm, missed_breach, misrouted, escalated_instead = [], [], [], []
    due_correct = due_rows = due_null_rows = due_null_correct = 0
    inconsistent = caught = missed = 0
    rule_own_correct = rule_own_rows = 0
    note_split = {"contradicting": {"n": 0, "correct": 0}, "agreeing": {"n": 0, "correct": 0}}

    for reg_id, g in sorted(golds.items()):
        rec = records.get(reg_id) or {}
        got_rows = _rows_by_ref(rec.get("attesters") or [], "person_ref")
        gold_rows = _rows_by_ref(g.get("attesters") or [], key)
        contra_note = bool(g.get("contradicting_note"))

        for ref, gp in sorted(gold_rows.items()):
            want = RB.status_of(gp)
            want_due = RB.decide(gp)["due_on"]
            row = got_rows.get(ref)
            got = (row or {}).get("computed_status")
            got = got if got in RB.STATUSES else None

            correct = (got is not None and got == want)
            rows.append({"doc": reg_id, "person": ref, "want": want, "got": got,
                         "correct": correct})
            confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
            confusion[want][got or "unanswered"] += 1
            bucket = note_split["contradicting" if contra_note else "agreeing"]
            bucket["n"] += 1
            bucket["correct"] += 1 if correct else 0

            # ---- grader 3: the MODEL'S own date arithmetic, which decides nothing here ---------
            if row is not None:
                got_due = ((row.get("fields") or {}).get("due_on") or {}).get("value")
                due_rows += 1
                ok = norm(got_due) == norm(want_due)
                due_correct += 1 if ok else 0
                if want_due is None:
                    due_null_rows += 1
                    due_null_correct += 1 if ok else 0

            # ---- grader 4: the worklist, and the false alarms on it ---------------------------
            want_work = "yes" if want in RB.WORKLIST else "no"
            got_work = None if got is None else ("yes" if got in RB.WORKLIST else "no")
            work_rows.append({"doc": reg_id, "person": ref, "want": want_work, "got": got_work,
                              "verdict": None})
            if got_work == "yes" and want in NOTHING_TO_DO:
                false_alarm.append({"doc": reg_id, "person": ref, "gold": want, "kit": got})
            if got_work == "yes" and want == "not_determinable":
                misrouted.append({"doc": reg_id, "person": ref, "gold": want, "kit": got})
            if want_work == "yes" and got in NOTHING_TO_DO:
                missed_breach.append({"doc": reg_id, "person": ref, "gold": want, "kit": got})
            if want_work == "yes" and got == "not_determinable":
                escalated_instead.append({"doc": reg_id, "person": ref, "gold": want, "kit": got})

            # ---- the "cannot determine from this record" reach --------------------------------
            det_rows.append({"doc": reg_id, "person": ref,
                             "want": "yes" if want == "not_determinable" else "no",
                             "got": None if got is None
                                    else ("yes" if got == "not_determinable" else "no"),
                             "verdict": None})

            # ---- the diagnostic: does the reply's own status survive the rule re-run over the
            # reply's own values? No gold is used here -- that is the whole point of reporting it.
            if row is not None:
                # ⚑ WHAT THE RULE WOULD SAY ABOUT THIS ROW'S OWN VALUES. On any run whose
                # PUBLISHED status is already the rule, this is identical to the status verdict
                # above and carries no information. It is computed anyway because on the FREE
                # FLOOR it is not identical -- the floor's regexed values are exact and its
                # published status is a shortcut, so the gap between these two numbers is exactly
                # the gap between reading a register and deciding from it.
                own = {name: (cell or {}).get("value")
                       for name, cell in ((row.get("fields") or {}).items())}
                rule_own_rows += 1
                rule_own_correct += 1 if RB.status_of(own) == want else 0

                stated = ((row.get("fields") or {}).get("status") or {}).get("value")
                stated = stated if stated in RB.STATUSES else None
                if stated is not None and got is not None and stated != got:
                    inconsistent += 1
                    if got != want:
                        caught += 1
                elif got != want:
                    missed += 1
            elif got != want:
                missed += 1

        # ---- the register-level business condition ----------------------------------------
        want_flag = _compute([RB.status_of(p) for p in (g.get("attesters") or [])])
        got_flag = rec.get("needs_owner_review")
        flag_rows.append({"doc": reg_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    work = _matrix(work_rows, "yes")
    det = _matrix(det_rows, "yes")
    flags = _matrix(flag_rows, "yes")
    n_flagged = work["true_positive"] + work["false_positive"]
    n_must_flag = sum(1 for r in work_rows if r["want"] == "yes")

    return {
        "status_accuracy": round(n_correct / n, 4),
        "status_correct": n_correct,
        "status_rows": n,
        "status_unanswered": n_unanswered,
        "confusion": confusion,
        "by_note_register": {
            k: dict(v, accuracy_pct=(round(100.0 * v["correct"] / v["n"], 2) if v["n"] else None))
            for k, v in note_split.items()
        },
        "due_date": {
            "rows": due_rows,
            "correct": due_correct,
            "accuracy_pct": round(100.0 * due_correct / due_rows, 2) if due_rows else None,
            "null_rows": due_null_rows,
            "null_correct": due_null_correct,
            "note": "The MODEL's own due_on against the derivation (cycle_opened_on + the "
                    "rulebook's cycle length for the role). No register states a due date. The "
                    "kit publishes the CODE's date and this number decides nothing, which is what "
                    "makes it a measurement of arithmetic rather than of copying. `null_rows` are "
                    "the people for whom no due date can be derived at all -- an unrecorded cycle, "
                    "or a role the rulebook gives no cycle length for -- where the correct answer "
                    "is null and answering with a date is inventing a deadline.",
        },
        "worklist": dict(work,
                         positive_class="yes (this person needs action today)",
                         note="The six-way status collapsed onto the one question a monitoring "
                              "queue asks. `missing`, `stale` and `contradicted` are the positive "
                              "class; `satisfied`, `not_required` and `not_determinable` are not.",
                         rows=work_rows),
        # ⚑ THE HEADLINE. Of everybody this kit put on the list, how many did not belong there.
        "false_alarm": len(false_alarm),
        "false_alarm_rate_pct": (round(100.0 * len(false_alarm) / n_flagged, 2)
                                 if n_flagged else None),
        "false_alarm_rows": false_alarm,
        "flagged_rows": n_flagged,
        "misrouted": len(misrouted),
        "misrouted_rows": misrouted,
        "missed_breach": len(missed_breach),
        "missed_breach_rate_pct": (round(100.0 * len(missed_breach) / n_must_flag, 2)
                                   if n_must_flag else None),
        "missed_breach_rows": missed_breach,
        "escalated_instead": len(escalated_instead),
        "escalated_instead_rows": escalated_instead,
        "not_determinable": dict(det,
                                 positive_class="yes (the register cannot answer for this person)",
                                 note="A monitor that never says “cannot determine from this "
                                      "record” is not cautious, it is guessing. This is how often "
                                      "the kit reaches for that answer and is right to.",
                                 rows=det_rows),
        "owner_review": dict(flags,
                             positive_class="yes (this register needs an owner, not a reminder)",
                             note="src/extract.py::compute() over the run's own computed statuses, "
                                  "against the same rule run over GOLD's. A business condition, so "
                                  "unlike the consistency diagnostic it genuinely needs labels, "
                                  "and saying so is half of what makes the number believable.",
                             rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "status_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "rule_over_own_values_rows": rule_own_rows,
            "rule_over_own_values_correct": rule_own_correct,
            "rule_over_own_values_accuracy_pct": (
                round(100.0 * rule_own_correct / rule_own_rows, 2) if rule_own_rows else None),
            "rule_over_own_values_note": "What src/rulebook.py says about each row's OWN extracted "
                    "values. Identical to the status verdict on any run whose published status is "
                    "already the rule, and reported anyway because on the free floor it is not: "
                    "the floor's regexed values are exact, so this number is its READING and its "
                    "published status is its DECIDING, and the distance between them is the gap "
                    "this kit exists to measure.",
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the rulebook over the "
                    "run's OWN extracted values and counts the people whose stated status "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "registers -- but it is blind to a reply that misreads a date and then reasons "
                    "correctly from the misreading, which on this corpus is most of the ways to be "
                    "wrong.",
        },
        "rows": rows,
    }
