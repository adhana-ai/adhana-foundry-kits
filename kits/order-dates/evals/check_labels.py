"""Check the gold calendar before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import calendar_rules as CR                # noqa: E402
from src import extract as EX                       # noqa: E402
from src import segment as SEG                      # noqa: E402
from src.extract import compute as _compute         # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ FOUR NULLABLE SUBFIELDS, AND EACH NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   period_days           is null exactly on an explicit_date paragraph -- nothing is counted.
#   trigger_event         is null on explicit_date and on anything counted from the Order itself.
#   trigger_event_date    is null when the events table says the event is NOT RECORDED -- and that
#                         is the whole `undatable` class, so the invariant below is two-way.
#   stated_date           is null on everything that is not explicit_date.
#   party_calculated_date is null wherever no party wrote a date next to the obligation.
#   due_date              is null IF AND ONLY IF the obligation cannot be dated at all.
NULLABLE = {"period_days", "trigger_event", "trigger_event_date", "stated_date",
            "party_calculated_date", "due_date"}

# Floors on the hard cases. Each is a reading a careless counter gets wrong, and each has to be
# MEASURED rather than anecdotal, so each has a minimum.
MIN_EXPLICIT_NONBUSINESS = 8     # a stated date on a weekend or holiday -- it does NOT move
MIN_ROLLED = 20                  # a calendar period that DOES move
MIN_TWO_DAY_ROLL = 3             # ... and moves more than one day, over a holiday-adjacent weekend
MIN_BUSINESS = 40                # periods counted in business days
MIN_UNDATABLE = 12               # obligations nothing on the Order dates
MIN_PARTY_WRONG = 20             # parentheticals that disagree with the rulebook
MIN_STRUCK = 15                  # deadline-shaped paragraphs that set no date

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    fields = EX.load_fields()
    subs = [s["name"] for s in EX.subfields(fields)]
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["order_id"]: r for r in rows}

    if len(by_id) != len(rows):
        bad("duplicate order_id in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))
    missing = docs - set(by_id)
    if missing:
        bad("%d order(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no order: %s" % (len(orphan), sorted(orphan)[:5]))

    every = [(oid, d) for oid, r in sorted(by_id.items()) for d in r["deadlines"]]

    # Every subfield the schema names must be present on every gold obligation, and only the
    # nullable ones may be null.
    for oid, d in every:
        for name in subs:
            if name not in d:
                bad("%s p%s: gold is missing subfield %r" % (oid, d.get("paragraph"), name))
            elif d[name] is None and name not in NULLABLE:
                bad("%s p%s: %r is null and is not a nullable field" % (oid, d["paragraph"], name))
        if d["basis"] not in CR.BASES:
            bad("%s p%s: basis %r is not one the rulebook carries" % (oid, d["paragraph"],
                                                                      d["basis"]))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK COMPUTATION. This is the check that makes the whole
    # kit honest: the label is not somebody's opinion about a date, it is the arithmetic.
    disagree = []
    for oid, d in every:
        want = CR.due_date(d["basis"], d["period_days"], by_id[oid]["order_date"],
                           d["trigger_event_date"], d["stated_date"])
        if want != d["due_date"]:
            disagree.append("%s p%s" % (oid, d["paragraph"]))
    if disagree:
        bad("%d gold obligation(s) carry a due_date their own values do not produce: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE NULLABILITY INVARIANT, BOTH WAYS: a due_date is null exactly when the obligation is
    # undatable, and nothing else on this corpus produces one.
    wrong_null = ["%s p%s" % (oid, d["paragraph"]) for oid, d in every
                  if (d["due_date"] is None) != bool(d["undatable"])]
    if wrong_null:
        bad("%d obligation(s) where due_date nullness and `undatable` disagree: %s"
            % (len(wrong_null), wrong_null[:5]))
    wrong_trigger = ["%s p%s" % (oid, d["paragraph"]) for oid, d in every
                     if d["undatable"] and d["trigger_event_date"] is not None]
    if wrong_trigger:
        bad("%d undatable obligation(s) carry a trigger event date: %s"
            % (len(wrong_trigger), wrong_trigger[:5]))

    # ⚑ EVERY GOLD VALUE MUST BE READABLE OFF THE PARAGRAPH IT LABELS. A corpus whose labels are
    # not in its own text is not a corpus, it is a second opinion.
    for oid, r in sorted(by_id.items()):
        text = EX.load_doc(oid)
        paras = SEG.numbered(text)
        if r["matter_number"] not in text:
            bad("%s: matter number not stated in the order" % oid)
        for d in r["deadlines"]:
            p = paras.get(d["paragraph"])
            if p is None:
                bad("%s: paragraph %s is labelled and is not in the order" % (oid, d["paragraph"]))
                continue
            if d["item"] not in p["text"]:
                bad("%s p%s: item %r is not in its own paragraph" % (oid, d["paragraph"],
                                                                     d["item"]))
            if d["trigger_event"] and d["trigger_event"] not in p["text"]:
                bad("%s p%s: trigger event is not named in its own paragraph" % (oid,
                                                                                 d["paragraph"]))
        for n in r["non_deadline_paragraphs"]:
            if n in {d["paragraph"] for d in r["deadlines"]}:
                bad("%s: paragraph %d is labelled both a deadline and not one" % (oid, n))

    # ⚑ THE PURE-CODE FLAG MUST AGREE WITH GOLD'S OWN VALUES. One rule, two readers.
    flag_disagree = ["%s p%s" % (oid, d["paragraph"]) for oid, d in every
                     if bool(_compute(d)) != bool(d["undatable"])]
    if flag_disagree:
        bad("%d obligation(s) where src/extract.py::compute() disagrees with gold's own "
            "`undatable`: %s" % (len(flag_disagree), flag_disagree[:5]))

    # ⚑ THE HARD CASES, ASSERTED RATHER THAN TRUSTED.
    explicit_off = [d for _o, d in every
                    if d["basis"] == "explicit_date" and d["due_date"]
                    and not CR.is_business_day(CR.parse(d["due_date"]))]
    if len(explicit_off) < MIN_EXPLICIT_NONBUSINESS:
        bad("only %d stated date(s) fall on a weekend or a court holiday -- the do-NOT-roll case "
            "needs at least %d to be measured rather than anecdotal"
            % (len(explicit_off), MIN_EXPLICIT_NONBUSINESS))
    else:
        print("  info  %d stated date(s) fall on a weekend or a court holiday and do NOT move"
              % len(explicit_off))

    rolled = [d for _o, d in every if d["rolled"]]
    two_day = 0
    for oid, d in every:
        if not d["rolled"]:
            continue
        w = CR.compute(d["basis"], d["period_days"], by_id[oid]["order_date"],
                       d["trigger_event_date"], d["stated_date"])
        if (CR.parse(w["due_date"]) - CR.parse(w["rolled_from"])).days > 2:
            two_day += 1
    if len(rolled) < MIN_ROLLED:
        bad("only %d obligation(s) roll forward -- needs at least %d" % (len(rolled), MIN_ROLLED))
    elif two_day < MIN_TWO_DAY_ROLL:
        bad("only %d roll(s) move MORE than one day -- the holiday-adjacent weekend case needs at "
            "least %d" % (two_day, MIN_TWO_DAY_ROLL))
    else:
        print("  info  %d obligation(s) roll forward off a weekend or a court holiday, %d of them "
              "by more than one day" % (len(rolled), two_day))

    business = [d for _o, d in every if d["basis"] in CR.BUSINESS]
    if len(business) < MIN_BUSINESS:
        bad("only %d obligation(s) count in BUSINESS days -- needs at least %d"
            % (len(business), MIN_BUSINESS))
    else:
        print("  info  %d obligation(s) count in business days rather than calendar days"
              % len(business))

    undatable = [d for _o, d in every if d["undatable"]]
    if len(undatable) < MIN_UNDATABLE:
        bad("only %d obligation(s) cannot be dated from the Order -- the 'insufficient "
            "information' answer needs at least %d to be scoreable" % (len(undatable),
                                                                       MIN_UNDATABLE))
    else:
        print("  info  %d obligation(s) cannot be dated from the four corners of the Order"
              % len(undatable))

    party = [d for _o, d in every if d["party_calculated_date"]]
    party_wrong = [d for d in party if d["party_calculated_date"] != d["due_date"]]
    if len(party_wrong) < MIN_PARTY_WRONG:
        bad("only %d parenthetical(s) disagree with the rulebook -- the copy-the-party's-arithmetic "
            "decoy needs at least %d" % (len(party_wrong), MIN_PARTY_WRONG))
    else:
        print("  info  %d of %d obligation(s) carry a party's own calculated date; %d of those are "
              "WRONG" % (len(party), len(every), len(party_wrong)))

    struck = sum(len(r.get("struck_paragraphs") or []) for r in by_id.values())
    if struck < MIN_STRUCK:
        bad("only %d deadline-SHAPED paragraph(s) set no date -- the invented-obligation trap "
            "needs at least %d" % (struck, MIN_STRUCK))
    else:
        print("  info  %d paragraph(s) state an item, a number and a unit and set NO date"
              % struck)

    # ⚑ NO GRADER MAY BE DEGENERATE. A basis with no members, or a flag that is constant, would
    # score perfectly and mean nothing.
    counts = {}
    for _o, d in every:
        counts[d["basis"]] = counts.get(d["basis"], 0) + 1
    for b in CR.BASES:
        if not counts.get(b):
            bad("gold has no %r obligations -- that basis's grader would be degenerate" % b)
    print("  info  bases: %s" % "  ".join("%s=%d" % (b, counts.get(b, 0)) for b in CR.BASES))

    n_flag = sum(1 for _o, d in every if _compute(d))
    if n_flag in (0, len(every)):
        bad("the pure-code undatable flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(every)))

    # ⚑ THE FREE FLOOR MUST BE A FAITHFUL READER AND A FAITHFUL SHORTCUT, and this is the check
    # that says so -- written in from the start, on the lesson a sibling kit in this series paid
    # for live when its floor's keyword list fired on the wrong register for days.
    #
    # Two properties, and both matter: the floor must FIND the same obligations gold does (if it
    # cannot read the order, the gap between it and a model is a gap about reading, not counting),
    # and it must actually be WRONG on the counting (a floor that happens to agree everywhere
    # measures nothing).
    try:
        from evals.baseline import extract as floor_extract
    except ImportError as exc:
        print("  info  floor check skipped: %s" % exc)
    else:
        f_found = f_missed = f_invented = f_datewrong = 0
        for oid, r in sorted(by_id.items()):
            got = floor_extract(EX.load_doc(oid), fields)
            gp = {d["paragraph"]: d for d in r["deadlines"]}
            mp = {row["paragraph"]: row for row in got["deadlines"]}
            f_found += len(set(gp) & set(mp))
            f_missed += len(set(gp) - set(mp))
            f_invented += len(set(mp) - set(gp))
            for k, d in gp.items():
                if k in mp and mp[k]["due_date"] != d["due_date"]:
                    f_datewrong += 1
        if f_missed or f_invented:
            bad("the free floor does not find the same obligations gold does (%d missed, %d "
                "invented) -- fix the floor's reading before publishing a counting gap, or the "
                "gap is measuring the wrong thing" % (f_missed, f_invented))
        else:
            print("  info  the free floor finds all %d obligations and invents none -- the gap it "
                  "opens is a COUNTING gap, not a reading one" % f_found)
        if f_datewrong < 40:
            bad("the free floor mis-dates only %d obligation(s) -- a floor that agrees with the "
                "rulebook nearly everywhere measures nothing" % f_datewrong)
        else:
            print("  info  the free floor mis-dates %d of %d obligation(s)" % (f_datewrong,
                                                                               len(every)))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d order(s), %d obligation(s), %d field(s) -- gold consistent with the "
          "corpus and with its own rulebook computation"
          % (len(docs), len(every), len(subs) + 2))


if __name__ == "__main__":
    main()
