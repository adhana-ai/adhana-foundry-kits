"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import rulebook as RB                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ THREE NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   last_done        null exactly where the register says the entry was logged with no date, and on
#                    every event-triggered row, where the line says it does not apply. The first of
#                    those is the whole `not_determinable` cycle class, so the invariant is two-way.
#   period_credited  null on everything that is not an annual report.
#   stated_due       null wherever the register states no date -- which is every row except an
#                    event-triggered condition whose trigger has occurred.
NULLABLE = {"last_done", "period_credited", "stated_due"}

# Floors on every planted difficulty. Each is MEASURED here rather than left anecdotal, and the run
# is refused if one is not met -- a trap with two instances is a story, not a measurement.
FLOOR = 6

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def _d(s):
    return datetime.date.fromisoformat(s)


def main():
    fields = EX.load_fields()
    ob_fields = EX.load_obligation_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["register_id"]: r for r in rows}
    obs = [(r["register_id"], r["register_date"], o) for r in rows for o in r["obligations"]]

    if len(by_id) != len(rows):
        bad("duplicate register_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))
    missing = docs - set(by_id)
    if missing:
        bad("%d register(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no register: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in ob_fields:
        if f.get("values"):
            for reg_id, _rd, o in obs:
                v = o.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s/%s: %s=%r is not one of %s"
                        % (reg_id, o.get("condition_id"), f["name"], v, f["values"]))

    for f in fields:
        n_null = sum(1 for r in rows if r.get(f["name"]) is None)
        if n_null:
            bad("register-level %s is null in %d gold row(s) -- none of the three is nullable"
                % (f["name"], n_null))
    for f in ob_fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for _i, _rd, o in obs if o.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold obligation(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ CONDITION IDS ARE UNIQUE WITHIN A REGISTER. They are the only key the scorer has for lining
    # a reply's rows up against gold's, so a duplicate would silently make one row unscoreable and
    # the other double-counted.
    for r in rows:
        ids = [o["condition_id"] for o in r["obligations"]]
        if len(set(ids)) != len(ids):
            bad("%s repeats a condition id: %s" % (r["register_id"], sorted(ids)))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK LOOKUP, STATUS AND DATE. This is the check that makes
    # the whole kit honest: the label is not a second opinion about the site's own flag, it is the
    # lookup.
    disagree_status, disagree_date = [], []
    for reg_id, rd, o in obs:
        d = RB.decide(rd, o)
        if d["status"] != o.get("status"):
            disagree_status.append("%s/%s" % (reg_id, o["condition_id"]))
        if d["due_date"] != o.get("due_date"):
            disagree_date.append("%s/%s" % (reg_id, o["condition_id"]))
    if disagree_status:
        bad("%d obligation(s) label a status their own values do not produce: %s"
            % (len(disagree_status), disagree_status[:5]))
    if disagree_date:
        bad("%d obligation(s) label a due date their own values do not produce: %s"
            % (len(disagree_date), disagree_date[:5]))

    # ⚑ THE FIVE PLANTED PIECES OF NOISE, ASSERTED RATHER THAN TRUSTED. Each is a reading a careless
    # monitor gets wrong, and each has a floor so it is measured rather than anecdotal.

    # 1 + 2. Superseded and waived rows must LOOK actionable with the state ignored, or they teach
    # nothing about where false alarms come from.
    for state in ("superseded", "waived"):
        hits = [(i, rd, o) for i, rd, o in obs if o["condition_state"] == state]
        for reg_id, rd, o in hits:
            if o["status"] != "not_binding":
                bad("%s/%s: a %s condition must be not_binding, gold says %r"
                    % (reg_id, o["condition_id"], state, o["status"]))
            as_active = RB.decide(rd, dict(o, condition_state="active"))["status"]
            if as_active not in RB.ACTIONABLE:
                bad("%s/%s: a %s condition that would read as %r with the state ignored is not a "
                    "false-alarm trap at all" % (reg_id, o["condition_id"], state, as_active))
        if len(hits) < FLOOR:
            bad("only %d %s condition(s) -- the largest single source of false alarms available to "
                "a monitor of this shape needs at least %d to be measured" % (len(hits), state, FLOOR))
        else:
            print("  info  %d %s condition(s), every one of which reads as an alarm if the state is "
                  "ignored" % (len(hits), state))

    # 3. An annual report filed RECENTLY and credited to a stale period. The filing date says done;
    # the period says the year in between is outstanding.
    wrong_period = [(i, rd, o) for i, rd, o in obs
                    if o["obligation_type"] == "periodic_report" and o["status"] == "overdue"
                    and o["last_done"] and (_d(rd) - _d(o["last_done"])).days <= 90]
    for reg_id, rd, o in wrong_period:
        deadline = RB.report_deadline(int(o["period_credited"]))
        if _d(o["last_done"]) <= deadline:
            bad("%s/%s: the filing is not dated after the deadline of the period it was credited "
                "to, so it is not the wrong-period trap" % (reg_id, o["condition_id"]))
    if len(wrong_period) < FLOOR:
        bad("only %d annual report(s) are overdue while showing a filing inside the last 90 days -- "
            "the filing-date decoy needs at least %d" % (len(wrong_period), FLOOR))
    else:
        print("  info  %d annual report(s) are OVERDUE while showing a filing dated inside the last "
              "90 days -- the period is the answer, the filing date is not" % len(wrong_period))

    # 4. A cycle entry logged with no date. The honest answer is that nobody can date the next one.
    no_date = [(i, rd, o) for i, rd, o in obs
               if o["last_done"] is None and o["obligation_type"] != "event_triggered"
               and o["condition_state"] == "active"]
    for reg_id, rd, o in no_date:
        if o["obligation_type"] != "periodic_report" and o["status"] != "not_determinable":
            bad("%s/%s: a cycle entry with no date must be not_determinable, gold says %r"
                % (reg_id, o["condition_id"], o["status"]))
    if len(no_date) < FLOOR:
        bad("only %d dateless cycle entr(ies) -- the 'cannot determine' class needs at least %d"
            % (len(no_date), FLOOR))
    else:
        print("  info  %d cycle entr(ies) are logged with no date -- not_determinable, not a guess"
              % len(no_date))

    # 5. A trigger that has not fired, and a trigger nobody recorded. Different facts, and merging
    # them turns an unknown into a clearance.
    not_occurred = [o for _i, _rd, o in obs if o.get("trigger_state") == "not_occurred"]
    not_recorded = [o for _i, _rd, o in obs if o.get("trigger_state") == "not_recorded"]
    for o in not_occurred:
        if o["status"] != "not_yet_due":
            bad("%s: a trigger recorded as NOT occurred must be not_yet_due, gold says %r"
                % (o["condition_id"], o["status"]))
    for o in not_recorded:
        if o["status"] != "not_determinable":
            bad("%s: a trigger the register does not record must be not_determinable, gold says %r"
                % (o["condition_id"], o["status"]))
    for label, hits in (("not occurred", not_occurred), ("not recorded", not_recorded)):
        if len(hits) < FLOOR:
            bad("only %d trigger(s) recorded as %r -- the pair that separates a recorded fact from "
                "an unrecorded one needs at least %d each" % (len(hits), label, FLOOR))
    if len(not_occurred) >= FLOOR and len(not_recorded) >= FLOOR:
        print("  info  %d trigger(s) recorded as NOT occurred (nothing is due) against %d the "
              "register does not record at all (nobody can tell)"
              % (len(not_occurred), len(not_recorded)))

    # ⚑ THE TWO WINDOW TRAPS, AND EACH IS ASSERTED IN BOTH DIRECTIONS. The rulebook gives a
    # financial assurance a 60-day action window and everything else 30, so the same distance to due
    # is inside the window for one type and outside it for the others.
    wide = [(i, rd, o) for i, rd, o in obs
            if o["obligation_type"] == "financial_assurance" and o["status"] == "due_in_window"
            and o["due_date"] and 31 <= (_d(o["due_date"]) - _d(rd)).days <= 60]
    narrow = [(i, rd, o) for i, rd, o in obs
              if o["obligation_type"] in ("monitoring_reading", "inspection")
              and o["status"] == "not_yet_due" and o["due_date"]
              and 31 <= (_d(o["due_date"]) - _d(rd)).days <= 60]
    if len(wide) < FLOOR:
        bad("only %d financial assurance(s) fall due 31-60 days out -- the wide-window trap needs "
            "at least %d, or a reader who uses one 30-day window everywhere is never convicted"
            % (len(wide), FLOOR))
    else:
        print("  info  %d financial assurance(s) fall due 31-60 days out: INSIDE their own 60-day "
              "window, where every other type would still be not_yet_due" % len(wide))
    if len(narrow) < FLOOR:
        bad("only %d reading(s)/inspection(s) fall due 31-60 days out -- the mirror trap needs at "
            "least %d, or a reader who uses one 60-day window everywhere is never convicted"
            % (len(narrow), FLOOR))
    else:
        print("  info  %d reading(s)/inspection(s) fall due 31-60 days out: OUTSIDE their 30-day "
              "window, where a financial assurance would be inside its own" % len(narrow))

    # ⚑ NO GRADER MAY BE DEGENERATE. A status class with no members, a worklist that is everything
    # or nothing, or a constant escalation flag would each score perfectly and mean nothing.
    counts = {}
    for _i, _rd, o in obs:
        counts[o["status"]] = counts.get(o["status"], 0) + 1
    for s in RB.STATUSES:
        if not counts.get(s):
            bad("gold has no %r obligation(s) -- the five-way status grader would be degenerate" % s)
    print("  info  statuses: %s" % "  ".join("%s=%d" % (s, counts.get(s, 0)) for s in RB.STATUSES))

    n_action = sum(1 for _i, _rd, o in obs if o["status"] in RB.ACTIONABLE)
    if n_action in (0, len(obs)):
        bad("every obligation has the same worklist answer (%d of %d) -- the false-alarm rate this "
            "kit exists to publish would be degenerate" % (n_action, len(obs)))
    else:
        print("  info  %d of %d obligations need action today -- the worklist"
              % (n_action, len(obs)))

    empty = sum(1 for r in rows
                if not any(o["status"] in RB.ACTIONABLE for o in r["obligations"]))
    if empty == 0:
        bad("every register has at least one obligation needing action -- a monitor that never "
            "returns an empty worklist has not been tested on one")
    else:
        print("  info  %d register(s) have an EMPTY worklist" % empty)

    n_esc = sum(1 for r in rows
                if _compute({"register_date": r["register_date"], "obligations": r["obligations"]}))
    if n_esc == 0 or n_esc == len(rows):
        bad("the escalation flag is constant across gold (%d of %d) -- it would score perfectly and "
            "mean nothing" % (n_esc, len(rows)))
    else:
        print("  info  %d of %d registers raise the escalation flag -- something already overdue, "
              "and the site's own register says on track or closed" % (n_esc, len(rows)))

    # ⚑ THE FREE FLOOR'S OWN PROPERTIES, ASSERTED BEFORE ANYTHING MAY SPEND -- written in from the
    # start, on the lesson a sibling kit in this series paid for live when its floor's keyword list
    # fired on a negation and mis-registered four records for days.
    try:
        from evals.baseline import FLAG_STATUS, extract as floor
    except ImportError as exc:
        print("  info  floor check skipped: %s" % exc)
    else:
        unreachable = set(RB.STATUSES) - set(FLAG_STATUS.values())
        if unreachable != {"due_in_window", "not_determinable"}:
            bad("the free floor can reach %s, which is not the pair this kit claims a "
                "self-assessment cannot express" % sorted(set(RB.STATUSES) - unreachable))
        else:
            n_unsayable = sum(1 for _i, _rd, o in obs if o["status"] in unreachable)
            print("  info  %d of %d obligations carry a status the free floor is structurally "
                  "incapable of saying (%s)" % (n_unsayable, len(obs), ", ".join(sorted(unreachable))))

        # And the corpus must be READABLE BY PURE CODE, every value, every register. This is the
        # strongest available statement that gold is derivable from the document text rather than
        # from a hidden label -- and it costs nothing.
        bad_cells = 0
        for reg_id, g in sorted(by_id.items()):
            r = floor(EX.load_doc(reg_id), fields, ob_fields)
            for f in fields:
                if r["fields"][f["name"]]["value"] != g[f["name"]]:
                    bad_cells += 1
            got = {o["condition_id"]: o["values"] for o in r["obligations"]}
            for o in g["obligations"]:
                v = got.get(o["condition_id"])
                if v is None:
                    bad_cells += len(ob_fields)
                    continue
                for f in ob_fields:
                    if v.get(f["name"]) != o.get(f["name"]):
                        bad_cells += 1
        if bad_cells:
            bad("%d gold cell(s) cannot be read back off their own register by pure code -- gold is "
                "not derivable from the document text" % bad_cells)
        else:
            print("  info  every one of the %d gold cells is read back off its own register by pure "
                  "regex -- gold is derivable from the text, not from a hidden label"
                  % (len(fields) * len(rows) + len(ob_fields) * len(obs)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d register(s), %d obligation(s), %d field(s), gold consistent with the "
          "corpus and with its own rulebook lookup"
          % (len(docs), len(obs), len(fields) + len(ob_fields)))


if __name__ == "__main__":
    main()
