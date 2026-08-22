"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from src import rulebook as RB                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402
from src.extract import count as _count             # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ THREE NULLABLE FIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   option_granted_date is null exactly where the register carries TWO entries that disagree about
#                       it. That is a state the register is in, not a value it is missing.
#   trigger_date        is null where there is no triggering event at all, and where there is one
#                       and the register records it as not yet occurred.
#   expiry_date         is null exactly where no expiry can be counted -- which is the whole
#                       `not_determinable` class, so the invariant below is two-way.
NULLABLE = {"option_granted_date", "trigger_date", "expiry_date"}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["register_ref"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate register_ref in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d register(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no register: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for reg_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (reg_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s are nullable in this corpus"
                % (f["name"], n_null, ", ".join(sorted(NULLABLE))))

    # ⚑ EVERY DATE IN GOLD MUST PARSE. A date the rulebook cannot read flows straight through to
    # `not_determinable` for a reason the corpus never intended, and it would do so silently.
    for reg_id, r in sorted(by_id.items()):
        for key in ("register_as_of", "option_granted_date", "trigger_date", "expiry_date"):
            v = r.get(key)
            if v is not None and RB.parse_date(v) is None:
                bad("%s: %s=%r is not a readable ISO date" % (reg_id, key, v))

    # ⚑ GOLD MUST AGREE WITH ITS OWN COUNT. This is the check that makes the whole kit honest: the
    # label is not a second opinion about the status column, it is the arithmetic.
    disagree_status, disagree_expiry = [], []
    for reg_id, r in sorted(by_id.items()):
        c = _count(r)
        if c["status"] != r.get("status"):
            disagree_status.append(reg_id)
        if c["expiry_date"] != r.get("expiry_date"):
            disagree_expiry.append(reg_id)
    if disagree_status:
        bad("%d gold row(s) label a status their own values do not count to: %s"
            % (len(disagree_status), disagree_status[:5]))
    if disagree_expiry:
        bad("%d gold row(s) label an expiry their own values do not count to: %s"
            % (len(disagree_expiry), disagree_expiry[:5]))

    # ⚑ THE NULLABILITY INVARIANT, BOTH WAYS: no expiry is exactly the not_determinable class, and
    # nothing else produces one on this corpus.
    wrong_nd = [s for s, r in by_id.items()
                if (r.get("expiry_date") is None) != (r.get("status") == "not_determinable")]
    if wrong_nd:
        bad("%d row(s) where a null expiry and status=='not_determinable' disagree: %s"
            % (len(wrong_nd), sorted(wrong_nd)[:5]))

    # ⚑ THE HARD CASES, ASSERTED RATHER THAN TRUSTED. Each is a reading a careless reader gets
    # wrong, and each has to be MEASURED rather than anecdotal, so each has a floor.

    # 1. an extension the register RECORDS as exercised that the acts do not perfect.
    unperfected = [s for s, r in by_id.items()
                   if r["extensions_recorded_taken"] > r["extensions_perfected"]]
    for s in unperfected:
        r = by_id[s]
        if r["status"] not in ("lapsed", "lapsing"):
            bad("%s: an unperfected extension must leave a worklist row, gold says %r"
                % (s, r["status"]))
        counted = RB.decide(r["register_as_of"], r["clock_basis"], r["trigger_status"],
                            r["option_granted_date"], r["trigger_date"],
                            r["initial_term_months"], r["extension_months_each"],
                            r["extensions_recorded_taken"])
        if counted["status"] != "live":
            bad("%s: counting the extension the register records must read as live, got %r"
                % (s, counted["status"]))
    if len(unperfected) < 3:
        bad("only %d row(s) record an extension the acts never perfected -- the sharpest case in "
            "the rulebook (an entry that says exercised, an act that never happened) needs at "
            "least 3 to be measured rather than anecdotal" % len(unperfected))
    else:
        print("  info  %d row(s) record an extension as exercised that was never perfected -- and "
              "on every one, counting it reads as live" % len(unperfected))

    # 2. a clock that has not started.
    not_started = [s for s, r in by_id.items() if r["trigger_status"] == "not_occurred"]
    for s in not_started:
        if by_id[s]["status"] != "not_determinable":
            bad("%s: a clock that has not started cannot produce %r"
                % (s, by_id[s]["status"]))
    if len(not_started) < 3:
        bad("only %d row(s) have a triggering event that has not occurred -- the clock-not-started "
            "case needs at least 3" % len(not_started))
    else:
        print("  info  %d row(s) run their clock from an event that has not happened" % len(not_started))

    # 3. two entries disagreeing about a grant date the clock RUNS FROM.
    conflict_fatal = [s for s, r in by_id.items()
                      if r["option_granted_date"] is None and r["clock_basis"] == "grant_date"]
    for s in conflict_fatal:
        if by_id[s]["status"] != "not_determinable":
            bad("%s: an unsettled grant date on a grant-date clock cannot produce %r"
                % (s, by_id[s]["status"]))
    if len(conflict_fatal) < 3:
        bad("only %d row(s) carry two disagreeing grant dates on a grant-date clock -- the "
            "contradiction case needs at least 3" % len(conflict_fatal))
    else:
        print("  info  %d row(s) carry two entries that disagree about a grant date the clock runs "
              "from" % len(conflict_fatal))

    # 4. ⚑ THE FALSE-ALARM TRAP, AND IT IS THE ONE THIS KIT CARES MOST ABOUT. The same two
    #    disagreeing entries, on a register whose clock runs from a triggering event that HAS
    #    occurred. The grant date is not an input, so the record is genuinely live -- and a reader
    #    who flags every contradiction cries wolf here.
    conflict_immaterial = [s for s, r in by_id.items()
                           if r["option_granted_date"] is None
                           and r["clock_basis"] == "triggering_event"
                           and r["trigger_status"] == "occurred"]
    for s in conflict_immaterial:
        if by_id[s]["status"] == "not_determinable":
            bad("%s: a grant-date disagreement is immaterial when the clock runs elsewhere -- "
                "gold answering not_determinable here would build the false alarm into the corpus"
                % s)
    if len(conflict_immaterial) < 3:
        bad("only %d row(s) carry an IMMATERIAL grant-date disagreement -- without at least 3, "
            "this corpus cannot tell a careful reader from one that flags every contradiction, "
            "and the false-alarm rate is the number this kit exists to publish"
            % len(conflict_immaterial))
    else:
        print("  info  %d row(s) carry a grant-date disagreement that changes nothing -- the "
              "false-alarm trap" % len(conflict_immaterial))

    # 5. the register's own status line, wrong in both directions.
    carried_live_but_not = [s for s, r in by_id.items()
                            if r["register_status"] == "live" and r["status"] != "live"]
    carried_lapsed_but_live = [s for s, r in by_id.items()
                               if r["register_status"] == "lapsed" and r["status"] == "live"]
    if len(carried_live_but_not) < 3:
        bad("only %d row(s) are carried as live and are not -- the register-is-optimistic case "
            "needs at least 3" % len(carried_live_but_not))
    if len(carried_lapsed_but_live) < 3:
        bad("only %d row(s) are carried as lapsed and are in fact live -- WITHOUT THIS DIRECTION "
            "the free floor can never raise a false alarm, and a floor that cannot cry wolf "
            "flatters itself on the number this kit exists to publish"
            % len(carried_lapsed_but_live))
    print("  info  the register's own status line is wrong on %d row(s): %d carried live that are "
          "not, %d carried lapsed that are live"
          % (len(carried_live_but_not) + len(carried_lapsed_but_live),
             len(carried_live_but_not), len(carried_lapsed_but_live)))

    # 6. the short-month clause, exercised rather than merely stated.
    clamped = []
    for s, r in sorted(by_id.items()):
        c = _count(r)
        if c["expiry_date"] and c["clock_start_date"]:
            if RB.parse_date(c["expiry_date"]).day != RB.parse_date(c["clock_start_date"]).day:
                clamped.append(s)
    if len(clamped) < 3:
        bad("only %d row(s) exercise the short-month clause -- a rule the rulebook states, the "
            "prompt repeats and no row tests is a rule this corpus cannot measure" % len(clamped))
    else:
        print("  info  %d row(s) land on the short-month clause (the expiry's day-of-month is "
              "clamped)" % len(clamped))

    # ⚑ NO GRADER MAY BE DEGENERATE. A status class with no members, a worklist that is all one
    # answer, or a constant escalation flag would score perfectly and mean nothing.
    counts = {}
    for r in by_id.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for v in RB.STATUSES:
        if not counts.get(v):
            bad("gold has no %r rows -- the four-way status grader would be degenerate" % v)
    print("  info  statuses: %s" % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in RB.STATUSES))

    n_action = sum(1 for r in by_id.values() if r["status"] in RB.NEEDS_ACTION)
    if n_action in (0, len(by_id)):
        bad("every register has the same worklist answer (%d of %d need somebody) -- the "
            "false-alarm and missed-lapse rates this kit exists to publish would both be "
            "undefined" % (n_action, len(by_id)))
    else:
        print("  info  %d of %d registers need somebody today; %d are genuinely live"
              % (n_action, len(by_id), len(by_id) - n_action))

    n_flag = sum(1 for r in by_id.values()
                 if _compute(r.get("status"), r.get("register_status")))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code escalation flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d registers are not live AND still carried as live -- the escalation "
              "flag" % (n_flag, len(by_id)))

    # ⚑ WHAT THE FREE FLOOR STRUCTURALLY CANNOT SAY, COUNTED RATHER THAN ASSERTED. A two-value
    # status column has no word for `lapsing` and none for `not_determinable`.
    unsayable = sum(1 for r in by_id.values()
                    if r["status"] in ("lapsing", "not_determinable"))
    print("  info  %d of %d registers carry a status a two-value column cannot express at all "
          "(lapsing, not_determinable)" % (unsayable, len(by_id)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL REGISTER DETECTOR, and this is the check that says so --
    # written in from the start, on the lesson a sibling kit in this series paid for live: its
    # first keyword list fired on a negation inside a relaxed note and mis-registered four rows.
    try:
        from evals.baseline import WORRIED_KEYWORDS
        from tools.build_corpus import CALM_NOTES, WORRIED_NOTES
    except ImportError as exc:                      # a lone fork may not carry tools/
        print("  info  register check skipped: %s" % exc)
    else:
        def worried(note):
            return any(k in note.lower() for k in WORRIED_KEYWORDS)
        before = len(problems)
        for note in CALM_NOTES:
            if worried(note):
                bad("the free floor reads a CALM note as worried -- a keyword in %r fires on prose "
                    "that says the opposite: %r"
                    % ([k for k in WORRIED_KEYWORDS if k in note.lower()], note))
        for note in WORRIED_NOTES:
            if not worried(note):
                bad("the free floor reads a concerned note as calm -- no keyword matches: %r" % note)
        if len(problems) == before:
            print("  info  the free floor classifies all %d note templates to the register they "
                  "were written as" % (len(CALM_NOTES) + len(WORRIED_NOTES)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d register(s), %d field(s), gold consistent with the corpus and with its "
          "own rulebook count" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
