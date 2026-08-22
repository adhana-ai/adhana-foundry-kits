#!/usr/bin/env python3
"""Generate synthetic permit obligation registers and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one site's obligation register per file) and data/gold.jsonl,
byte-identical on every run. Every site name, permit number, condition identifier, waiver reference
and administering body here is invented. Nothing is fetched and nothing is licensed from anybody,
so the corpus ships under this repo's MIT licence.

⚠︎ NO REAL PERMIT, OPERATOR, MINE, ADMINISTERING BODY OR REGULATION IS REPRODUCED OR NAMED. The
rulebook this corpus is built against is `data/rulebook.json`, which was written for this kit and is
illustrative rather than authoritative. See data/SOURCES.md.

⚑ THE UNIT IS THE OBLIGATION, NOT THE DOCUMENT, AND THAT IS WHAT MAKES THIS A MONITOR CORPUS. Each
file is ONE SITE'S REGISTER AT ONE MOMENT -- the conditions that bind it, and what the record shows
has actually been done. A document therefore carries several obligations at once, in different
states, and the question the kit answers is "which of these needs action, by when, and which cannot
be determined from what is on the page". Nothing here is a stream, a queue or a schedule: it is one
snapshot somebody else assembled.

⚑ GOLD `status` IS A RULEBOOK LOOKUP, NOT A LABEL SOMEBODY TYPED. Every row's status and due date
are derived from the same recorded values the register itself states, by the same function the kit
publishes everywhere else -- src/rulebook.py::decide(), which src/prompt.py states to the model in
words and evals/judge.py runs over the model's own extracted values. No status is ever derived from
the site's own register flag, and the flag never feeds a label.

⚑ THE FIVE PIECES OF DELIBERATE NOISE, AND WHY EACH ONE IS HERE. Each exists because a reader who
skips it puts a row on a worklist that should not be there, or leaves one off that should:

  superseded            -- a condition replaced by a permit amendment and STILL PRINTED on the
                           register, carrying a stale date that computes as overdue. Registers
                           accrete; nobody deletes rows.
  waived                -- the same shape, waived in writing with a reference. Also looks overdue.
  report_wrong_period   -- an annual report FILED LAST MONTH and credited to a reporting period two
                           years back. The filing date says "done"; the period says the year in
                           between is still outstanding.
  no_date_logged        -- a reading recorded as taken with the date column left empty. The next
                           one cannot be dated from it, so the honest answer is
                           `not_determinable` -- and a monitor that answers anything else is
                           guessing.
  event_not_occurred    -- a condition that engages only on a named event, where the register
                           records that the event has not happened. Nothing is due, and that is a
                           recorded fact rather than an omission.

⚑ THE PLANTED CONTRADICTION: the site's own REGISTER FLAG disagrees with the rulebook on
`N_MISFLAGGED` of the rows. A row that is already overdue can carry "on track"; a superseded row
that binds nothing can carry "attention". Anything that classifies off the flag -- including
evals/baseline.py, deliberately -- fails those rows by construction. Anything that runs the rulebook
gets them right.
"""
import argparse
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                     # noqa: E402
from src import segment                            # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_DOCS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER ROW -- the fix a sibling kit in this
# series had to make after its first generator asked for 40 pct ambiguity and delivered 51. A count
# 1.7 standard deviations off its own design is not a corpus property, it is sampling noise being
# published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
BUCKETS = [
    ("cyclic_overdue", 40),          # a reading/inspection/renewal whose cycle has already lapsed
    ("cyclic_due_in_window", 34),    # inside the type's OWN action window
    ("cyclic_not_yet_due", 44),      # beyond it
    ("report_wrong_period", 22),     # filed recently, credited to a stale period -- THE DECOY
    ("report_plain_overdue", 12),    # an annual report simply not filed
    ("report_current", 20),          # filed for the period that was outstanding
    ("event_not_occurred", 20),      # the trigger has not fired, so nothing is due
    ("event_occurred_overdue", 10),  # the trigger fired and the stated date has passed
    ("event_occurred_window", 8),    # the trigger fired and the stated date is close
    ("superseded", 18),              # replaced by an amendment, still printed, LOOKS overdue
    ("waived", 14),                  # waived in writing, still printed, LOOKS overdue
    ("no_date_logged", 16),          # a cycle entry with the date column empty
    ("trigger_not_recorded", 10),    # the register does not say whether the trigger fired
]
N_ROWS = sum(count for _name, count in BUCKETS)      # 268

# Document sizes, exact and then shuffled, summing to N_ROWS across N_DOCS registers.
DOC_SIZES = [4] * 12 + [5] * 16 + [6] * 14 + [7] * 8

N_MISFLAGGED = 107          # 40 pct of the rows, exactly -- a register flag from the wrong register

# ⚑ THE TWO WINDOW TRAPS, FORCED RATHER THAN HOPED FOR. The rulebook gives a financial assurance a
# 60-day action window and everything else 30, so a row falling due in 31-60 days is INSIDE the
# window for one type and OUTSIDE it for the others. A reader who flattens the window to one number
# gets both of these wrong, in opposite directions.
N_WIDE_WINDOW = 10          # financial_assurance, due in 31-60 days -> due_in_window
N_NARROW_MISS = 10          # reading/inspection, due in 31-60 days -> not_yet_due

CYCLE_TYPES = ("monitoring_reading", "inspection", "financial_assurance")

# Invented sites. Nothing here is a real mine, operation, operator or place.
SITES = [
    ("Northreach Ridge Operation", "NR"),
    ("Blackmarsh Flats Mine", "BF"),
    ("Kestrel Hollow Operation", "KH"),
    ("Longmarsh Pit", "LP"),
    ("Hollowfield Rise Mine", "HR"),
    ("Saltpan Gully Operation", "SG"),
    ("Windward Basin Mine", "WB"),
    ("Cold Fork Operation", "CF"),
    ("Stonelick Ridge Mine", "SR"),
    ("Greyfield Downs Operation", "GD"),
]

# Invented administering bodies. Numbered districts, so no reader can mistake one for a real office.
OFFICES = [
    "the Second District Minerals and Environment Office",
    "the Fourth District Minerals and Environment Office",
    "the Sixth District Minerals and Environment Office",
    "the Ninth District Minerals and Environment Office",
]

REQUIREMENTS = {
    "monitoring_reading": [
        "quarterly groundwater quality reading at monitoring bore MB-%02d",
        "quarterly surface water sampling at discharge point DP-%02d",
        "quarterly dust deposition reading at gauge DG-%02d",
        "quarterly boundary noise reading at station NS-%02d",
        "quarterly seepage reading at collection sump SS-%02d",
    ],
    "inspection": [
        "half-yearly geotechnical inspection of the waste rock dump",
        "half-yearly inspection of the tailings storage facility embankment",
        "half-yearly inspection of the sediment control structures",
        "half-yearly inspection of the haul road water crossings",
        "half-yearly inspection of the explosives magazine bund",
    ],
    "financial_assurance": [
        "annual renewal of the rehabilitation security held against this permit",
        "annual re-lodgement of the closure cost estimate with the administering office",
        "annual renewal of the pollution incident financial provision",
    ],
    "periodic_report": [
        "annual environmental performance report for the calendar reporting year",
        "annual water balance report for the calendar reporting year",
        "annual rehabilitation progress report for the calendar reporting year",
        "annual waste and emissions return for the calendar reporting year",
    ],
    "event_triggered": [
        "incident notification to the administering office following any exceedance of a discharge limit",
        "remedial action plan following any recorded slope movement above the trigger level",
        "supplementary sampling round following any detection of seepage outside the containment",
        "notification following any unplanned discharge from the sediment basin",
        "corrective action report following any breach of the dust deposition trigger",
    ],
}

TRIGGER_EVENTS = [
    "discharge limit exceedance recorded",
    "slope movement above the trigger level recorded",
    "seepage detected outside the containment",
    "unplanned discharge from the sediment basin recorded",
    "dust deposition trigger breached",
]

# The site's own summary self-assessment. It is mapped by no field in src/select.py, so it never
# reaches the model at all -- it is the one section a reader can point at and say "that is what
# selection did". It is kept in the corpus because a real register carries one and because it is
# routinely contradicted by the computed worklist.
REGISTER_NOTES = [
    "Site self-assessment at this review: nothing expected to fall due before the next cycle.",
    "Site self-assessment at this review: register believed current; no outstanding items known.",
    "Site self-assessment at this review: a small number of items under follow-up with the office.",
    "Site self-assessment at this review: compliance position considered satisfactory this quarter.",
    "Site self-assessment at this review: awaiting confirmation on one or two historic entries.",
]

FLAGS = ("on track", "attention", "closed")

EXPECTED_STATUS = {
    "cyclic_overdue": "overdue",
    "cyclic_due_in_window": "due_in_window",
    "cyclic_not_yet_due": "not_yet_due",
    "report_wrong_period": "overdue",
    "report_plain_overdue": "overdue",
    "report_current": "not_yet_due",
    "event_not_occurred": "not_yet_due",
    "event_occurred_overdue": "overdue",
    "event_occurred_window": "due_in_window",
    "superseded": "not_binding",
    "waived": "not_binding",
    "no_date_logged": "not_determinable",
    "trigger_not_recorded": "not_determinable",
}

# Which buckets must LOOK actionable if the condition state is ignored. Asserted, not assumed --
# a not_binding row that would have read as not_yet_due anyway teaches nothing about false alarms.
LOOKS_ACTIONABLE = ("superseded", "waived")


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


def _iso(d):
    return d.isoformat()


def _register_dates(rng):
    """One register date per document, spread across 2026 and all distinct.

    They are spread rather than fixed because the whole decision is a comparison against this date:
    a corpus where every register was drawn on the same day would make every report deadline fall on
    the same side of it, and three of the thirteen buckets would collapse into one.
    """
    start = datetime.date(2026, 1, 12)
    span = 250                                    # to 2026-09-19
    picked = sorted(rng.sample(range(span), N_DOCS))
    return [start + datetime.timedelta(days=i) for i in picked]


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns the seven recorded values for a row, and every one is
# ASSERTED against the rulebook in build_all -- a constructor that quietly stops producing its own
# bucket is exactly the defect an exact composition exists to prevent.
# --------------------------------------------------------------------------------------------

def _blank():
    return {"obligation_type": None, "condition_state": "active", "last_done": None,
            "period_credited": None, "stated_due": None, "trigger_state": "not_applicable"}


def _cycle_row(rng, rd, otype, days_to_due):
    """A cycle row whose next instance falls `days_to_due` from the register date (negative = past)."""
    ob = _blank()
    ob["obligation_type"] = otype
    due = rd + datetime.timedelta(days=days_to_due)
    ob["last_done"] = _iso(due - datetime.timedelta(days=RB.interval_days(otype)))
    return ob


def _mk_cyclic_overdue(rng, rd):
    otype = rng.choice(CYCLE_TYPES)
    return _cycle_row(rng, rd, otype, -rng.randint(1, 200))


def _mk_cyclic_due_in_window(rng, rd, wide=False):
    if wide:
        # The trap: a financial assurance falls INSIDE its own 60-day window at 31-60 days out,
        # where every other type would still be `not_yet_due`.
        return _cycle_row(rng, rd, "financial_assurance", rng.randint(31, 60))
    otype = rng.choice(CYCLE_TYPES)
    return _cycle_row(rng, rd, otype, rng.randint(0, RB.window_days(otype)))


def _mk_cyclic_not_yet_due(rng, rd, narrow=False):
    if narrow:
        # The mirror trap: a reading or inspection at 31-60 days out is OUTSIDE its 30-day window,
        # where a financial assurance at the same distance would be inside its own.
        otype = rng.choice(("monitoring_reading", "inspection"))
        return _cycle_row(rng, rd, otype, rng.randint(31, 60))
    otype = rng.choice(CYCLE_TYPES)
    lo = RB.window_days(otype) + 1
    hi = RB.interval_days(otype) - 1
    return _cycle_row(rng, rd, otype, rng.randint(lo, hi))


def _overdue_report_year(rd):
    """The most recent reporting year whose SUCCESSOR's deadline is already behind `rd`."""
    deadline_this_year = RB.report_deadline(rd.year - 1)        # 31 March of rd.year
    base = rd.year - 2 if deadline_this_year < rd else rd.year - 3
    return base


def _mk_report_wrong_period(rng, rd):
    """Filed LAST MONTH, credited to a period two years back. The year between is outstanding."""
    ob = _blank()
    ob["obligation_type"] = "periodic_report"
    ob["period_credited"] = str(_overdue_report_year(rd))
    ob["last_done"] = _iso(rd - datetime.timedelta(days=rng.randint(10, 75)))
    return ob


def _mk_report_plain_overdue(rng, rd):
    """The same year outstanding, and the filing date agrees with the period for once."""
    ob = _blank()
    ob["obligation_type"] = "periodic_report"
    year = _overdue_report_year(rd)
    ob["period_credited"] = str(year)
    filed = RB.report_deadline(year) - datetime.timedelta(days=rng.randint(3, 40))
    ob["last_done"] = _iso(min(filed, rd - datetime.timedelta(days=1)))
    return ob


def _current_report_year(rd):
    """The earliest reporting year whose filing puts the NEXT deadline beyond the action window.

    ⚠︎ COMPUTED, NOT "the overdue year plus one". A register drawn in early March sits weeks away
    from 31 March, so crediting the immediately-preceding year leaves the next report inside the
    30-day window and the row lands in `due_in_window` rather than `not_yet_due` -- which is a real
    status and the wrong bucket. Found by the constructor's own assertion on the first build,
    exactly what the assertion is for.
    """
    win = RB.window_days("periodic_report")
    year = _overdue_report_year(rd)
    while (RB.report_deadline(year + 1) - rd).days <= win:
        year += 1
    return year


def _mk_report_current(rng, rd):
    """The outstanding year has been filed, so the next one is beyond the action window."""
    ob = _blank()
    ob["obligation_type"] = "periodic_report"
    year = _current_report_year(rd)
    ob["period_credited"] = str(year)
    filed = RB.report_deadline(year) - datetime.timedelta(days=rng.randint(2, 45))
    ob["last_done"] = _iso(min(filed, rd - datetime.timedelta(days=1)))
    return ob


def _mk_event_not_occurred(rng, rd):
    ob = _blank()
    ob["obligation_type"] = "event_triggered"
    ob["trigger_state"] = "not_occurred"
    return ob


def _mk_event_occurred(rng, rd, days_to_due):
    ob = _blank()
    ob["obligation_type"] = "event_triggered"
    ob["trigger_state"] = "occurred"
    ob["stated_due"] = _iso(rd + datetime.timedelta(days=days_to_due))
    return ob


def _mk_event_occurred_overdue(rng, rd):
    return _mk_event_occurred(rng, rd, -rng.randint(1, 120))


def _mk_event_occurred_window(rng, rd):
    return _mk_event_occurred(rng, rd, rng.randint(0, 30))


def _mk_trigger_not_recorded(rng, rd):
    ob = _blank()
    ob["obligation_type"] = "event_triggered"
    ob["trigger_state"] = "not_recorded"
    return ob


def _mk_no_date_logged(rng, rd):
    """A cycle entry recorded as done with the date column left empty."""
    ob = _blank()
    ob["obligation_type"] = rng.choice(CYCLE_TYPES)
    ob["last_done"] = None
    return ob


def _mk_not_binding(rng, rd, state):
    """A superseded or waived condition, CONSTRUCTED TO LOOK OVERDUE if the state is ignored."""
    ob = _cycle_row(rng, rd, rng.choice(CYCLE_TYPES), -rng.randint(5, 240))
    ob["condition_state"] = state
    return ob


MAKERS = {
    "cyclic_overdue": _mk_cyclic_overdue,
    "cyclic_due_in_window": _mk_cyclic_due_in_window,
    "cyclic_not_yet_due": _mk_cyclic_not_yet_due,
    "report_wrong_period": _mk_report_wrong_period,
    "report_plain_overdue": _mk_report_plain_overdue,
    "report_current": _mk_report_current,
    "event_not_occurred": _mk_event_not_occurred,
    "event_occurred_overdue": _mk_event_occurred_overdue,
    "event_occurred_window": _mk_event_occurred_window,
    "no_date_logged": _mk_no_date_logged,
    "trigger_not_recorded": _mk_trigger_not_recorded,
}


def _truthful_flag(status):
    if status in RB.ACTIONABLE:
        return "attention"
    if status == "not_binding":
        return "closed"
    return "on track"


def _row_text(cond_id, requirement, ob, extra):
    """One Condition block, exactly as the register prints it."""
    state_line = ob["condition_state"]
    if ob["condition_state"] == "superseded":
        state_line = ("superseded - replaced by condition %s in the permit amendment of %s"
                      % (extra["supersedes"], extra["amendment_date"]))
    elif ob["condition_state"] == "waived":
        state_line = ("waived - written waiver %s from the administering office, dated %s"
                      % (extra["waiver_ref"], extra["waiver_date"]))

    if ob["last_done"] is not None:
        last_line = ob["last_done"]
    elif ob["obligation_type"] == "event_triggered":
        last_line = "not applicable to this condition"
    else:
        last_line = "entry logged, date not recorded"

    period_line = ("%s reporting year" % ob["period_credited"]) if ob["period_credited"] \
        else "not applicable to this condition"

    due_line = ob["stated_due"] if ob["stated_due"] else "not stated"

    ts = ob["trigger_state"]
    if ts == "occurred":
        trig_line = "occurred - %s on %s" % (extra["trigger_event"], extra["trigger_date"])
    elif ts == "not_occurred":
        trig_line = "not occurred - no qualifying event recorded in this cycle"
    elif ts == "not_recorded":
        trig_line = "not recorded"
    else:
        trig_line = "not applicable to this condition"

    return "\n".join([
        _underline("Condition %s" % cond_id),
        "Requirement: %s" % requirement,
        "Obligation type: %s" % ob["obligation_type"],
        "Condition state: %s" % state_line,
        "Last recorded as done: %s" % last_line,
        "Period credited: %s" % period_line,
        "Stated due date: %s" % due_line,
        "Trigger event: %s" % trig_line,
        "Register flag: %s" % ob["register_flag"],
        "",
    ])


def _make_row(rng, rd, bucket, forced):
    if bucket == "superseded":
        return _mk_not_binding(rng, rd, "superseded")
    if bucket == "waived":
        return _mk_not_binding(rng, rd, "waived")
    if bucket == "cyclic_due_in_window":
        return _mk_cyclic_due_in_window(rng, rd, wide=forced)
    if bucket == "cyclic_not_yet_due":
        return _mk_cyclic_not_yet_due(rng, rd, narrow=forced)
    return MAKERS[bucket](rng, rd)


def build_all(rng, n_docs=N_DOCS):
    sizes = list(DOC_SIZES)
    rng.shuffle(sizes)
    if n_docs != N_DOCS:                             # a --n other than the design keeps the shape
        sizes = sizes[:n_docs] or [5]
    total = sum(sizes)

    spec = list(BUCKETS)
    if total != N_ROWS:
        spec = [(name, max(1, round(count * total / N_ROWS))) for name, count in BUCKETS]
    buckets = _deal(rng, total, spec)
    buckets = _repair(buckets, sizes)
    flag_wrong = _deal(rng, total, [(True, N_MISFLAGGED), (False, total - N_MISFLAGGED)])

    reg_dates = _register_dates(rng)[:len(sizes)]
    wide_left, narrow_left = N_WIDE_WINDOW, N_NARROW_MISS

    stats = {"statuses": {}, "buckets": {name: 0 for name, _ in BUCKETS}, "misflagged": 0,
             "wide_window": 0, "narrow_miss": 0, "escalate": 0, "actionable": 0,
             "empty_worklist": 0}
    docs = []
    cursor = 0

    for i, size in enumerate(sizes, 1):
        rd = reg_dates[i - 1]
        site, code = SITES[(i - 1) % len(SITES)]
        site_id = "SITE-%s-%04d" % (code, rng.randint(1000, 9999))
        permit_no = "MP-%04d-%s" % (rng.randint(1000, 9999), rng.choice("ABCDEFGHJK"))
        office = rng.choice(OFFICES)
        reg_id = "REG-%04d" % i

        rows, used_ids = [], set()
        for k in range(size):
            bucket = buckets[cursor]
            wrong_flag = flag_wrong[cursor]
            cursor += 1

            forced = False
            if bucket == "cyclic_due_in_window" and wide_left > 0:
                forced, wide_left = True, wide_left - 1
            elif bucket == "cyclic_not_yet_due" and narrow_left > 0:
                forced, narrow_left = True, narrow_left - 1

            ob = _make_row(rng, rd, bucket, forced)

            while True:
                cond_id = "C-%d.%d" % (rng.randint(2, 14), rng.randint(1, 9))
                if cond_id not in used_ids:
                    used_ids.add(cond_id)
                    break

            template = rng.choice(REQUIREMENTS[ob["obligation_type"]])
            requirement = template % rng.randint(1, 24) if "%02d" in template else template

            d = RB.decide(_iso(rd), ob)
            status = d["status"]
            assert status == EXPECTED_STATUS[bucket], \
                "%s produced %r, not %r" % (bucket, status, EXPECTED_STATUS[bucket])
            if bucket in LOOKS_ACTIONABLE:
                # ⚑ ASSERTED, NOT HOPED FOR: a not-binding row must LOOK actionable with the state
                # ignored, or it teaches nothing about where false alarms come from.
                as_active = RB.decide(_iso(rd), dict(ob, condition_state="active"))["status"]
                assert as_active in RB.ACTIONABLE, \
                    "%s row would read as %r with the state ignored, not as an alarm" \
                    % (bucket, as_active)
            if forced and bucket == "cyclic_due_in_window":
                assert ob["obligation_type"] == "financial_assurance" and 31 <= d["days_to_due"] <= 60
                stats["wide_window"] += 1
            if forced and bucket == "cyclic_not_yet_due":
                assert 31 <= d["days_to_due"] <= 60
                stats["narrow_miss"] += 1

            truthful = _truthful_flag(status)
            if wrong_flag:
                ob["register_flag"] = rng.choice([f for f in FLAGS if f != truthful])
                stats["misflagged"] += 1
            else:
                ob["register_flag"] = truthful

            extra = {
                "supersedes": "C-%d.%d" % (rng.randint(15, 22), rng.randint(1, 9)),
                "amendment_date": _iso(rd - datetime.timedelta(days=rng.randint(120, 900))),
                "waiver_ref": "WV-%04d" % rng.randint(1000, 9999),
                "waiver_date": _iso(rd - datetime.timedelta(days=rng.randint(30, 700))),
                "trigger_event": rng.choice(TRIGGER_EVENTS),
                "trigger_date": (ob["stated_due"] or _iso(rd)),
            }
            if ob["stated_due"]:
                extra["trigger_date"] = _iso(
                    datetime.date.fromisoformat(ob["stated_due"])
                    - datetime.timedelta(days=rng.randint(14, 45)))

            rows.append({"condition_id": cond_id, "requirement": requirement, "bucket": bucket,
                         "ob": ob, "extra": extra, "status": status, "due_date": d["due_date"]})
            stats["buckets"][bucket] += 1
            stats["statuses"][status] = stats["statuses"].get(status, 0) + 1
            if status in RB.ACTIONABLE:
                stats["actionable"] += 1

        note = rng.choice(REGISTER_NOTES)
        text = "\n".join([
            _underline("Site"), "%s (%s)" % (site, site_id), "",
            _underline("Permit"), "%s, issued by %s" % (permit_no, office), "",
            _underline("Register Date"), _iso(rd), "",
            _underline("Register Note"), note, "", "",
        ]) + "\n".join(_row_text(r["condition_id"], r["requirement"], r["ob"], r["extra"])
                       for r in rows)

        obligations = [{"condition_id": r["condition_id"],
                        "obligation_type": r["ob"]["obligation_type"],
                        "condition_state": r["ob"]["condition_state"],
                        "last_done": r["ob"]["last_done"],
                        "period_credited": r["ob"]["period_credited"],
                        "stated_due": r["ob"]["stated_due"],
                        "trigger_state": r["ob"]["trigger_state"],
                        "register_flag": r["ob"]["register_flag"],
                        "status": r["status"], "due_date": r["due_date"],
                        "bucket": r["bucket"]} for r in rows]

        gold = {"register_id": reg_id, "site_id": site_id, "permit_no": permit_no,
                "register_date": _iso(rd), "obligations": obligations}
        gold["escalate"] = _escalate(gold)
        if gold["escalate"]:
            stats["escalate"] += 1
        if not any(o["status"] in RB.ACTIONABLE for o in obligations):
            stats["empty_worklist"] += 1

        docs.append((reg_id, text, gold))

    return docs, stats


def _repair(buckets, sizes):
    """Deterministic repair: no register may consist entirely of conditions that bind nothing.

    A register whose every row is superseded or waived is not a monitoring snapshot, it is a
    closed file, and it would silently make one document's worklist trivially empty for a reason
    the corpus never intended. The shuffle makes it rare rather than impossible, so it is repaired
    here by an in-order swap rather than left to the seed.
    """
    out = list(buckets)
    pos, spans = 0, []
    for size in sizes:
        spans.append((pos, pos + size))
        pos += size
    dead = {"superseded", "waived"}
    for start, end in spans:
        if all(out[i] in dead for i in range(start, end)):
            for j in range(len(out)):
                if not (start <= j < end) and out[j] not in dead:
                    out[start], out[j] = out[j], out[start]
                    break
    return out


def _escalate(gold):
    """THE BUSINESS CONDITION, computed here exactly as src/extract.py::compute() computes it.

    Written from gold's own values so the grader has a labelled truth to score against; the kit
    itself runs the identical rule over whatever the model returned.
    """
    from src.extract import compute
    return compute(gold)


def _verify(docs):
    """Every gold value must be readable off the register it labels, every gold status must be that
    row's own rulebook lookup, and every null must be a STATED fact rather than a convenience. A
    corpus whose labels are not readable off its own text is not a corpus, it is a second opinion."""
    for reg_id, text, gold in docs:
        for field in ("site_id", "permit_no", "register_date"):
            assert gold[field] in text, "%s: %s not stated on the register" % (reg_id, field)
        # ⚠︎ COUNTED OFF THE SEGMENTER, NOT OFF A SUBSTRING. The obvious `text.count("\\nCondition ")`
        # is wrong on this layout and silently doubles: every block ALSO carries a line reading
        # "Condition state: active", which matches the same substring. Counting the headings the
        # kit's own segmenter actually finds is both correct and the thing downstream code sees.
        blocks = [s for s in segment.sections(text) if s["name"].startswith("Condition C-")]
        assert len(gold["obligations"]) == len(blocks), \
            "%s: gold row count (%d) disagrees with the register's own Condition blocks (%d)" \
            % (reg_id, len(gold["obligations"]), len(blocks))
        for ob in gold["obligations"]:
            assert "Condition %s\n" % ob["condition_id"] in text, \
                "%s: condition %s has no block" % (reg_id, ob["condition_id"])
            assert "Obligation type: %s" % ob["obligation_type"] in text
            assert "Condition state: %s" % ob["condition_state"] in text
            assert "Register flag: %s" % ob["register_flag"] in text

            if ob["last_done"] is None:
                assert ("date not recorded" in text or "not applicable" in text), \
                    "%s: a null last_done is not explained in the text" % reg_id
            else:
                assert ob["last_done"] in text, "%s: last_done not stated" % reg_id
            if ob["period_credited"] is None:
                assert "Period credited: not applicable" in text
            else:
                assert "%s reporting year" % ob["period_credited"] in text
            if ob["stated_due"] is None:
                assert "Stated due date: not stated" in text
            else:
                assert ob["stated_due"] in text, "%s: stated_due not stated" % reg_id

            want = RB.decide(gold["register_date"], ob)
            assert ob["status"] == want["status"], \
                "%s/%s: gold status %r disagrees with its own rulebook lookup (%r)" \
                % (reg_id, ob["condition_id"], ob["status"], want["status"])
            assert ob["due_date"] == want["due_date"], \
                "%s/%s: gold due date %r disagrees with its own lookup (%r)" \
                % (reg_id, ob["condition_id"], ob["due_date"], want["due_date"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_DOCS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    docs, stats = build_all(rng, n_docs=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for reg_id, text, _gold in docs:
        with open(os.path.join(CORPUS, "%s.txt" % reg_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _reg_id, _text, gold in docs:
            fh.write(json.dumps(gold) + "\n")

    _verify(docs)

    total_rows = sum(len(g["obligations"]) for _i, _t, g in docs)
    total_bytes = sum(len(t.encode("utf-8")) for _i, t, _g in docs)
    print("registers: %d   obligations: %d   bytes: %d" % (len(docs), total_rows, total_bytes))
    print("statuses: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["statuses"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d of %d obligations (%.0f%%) carry a register flag from the register that CONTRADICTS "
          "the rulebook" % (stats["misflagged"], total_rows,
                            100.0 * stats["misflagged"] / total_rows))
    print("%d obligation(s) need action today -- the worklist this kit proposes" % stats["actionable"])
    print("%d register(s) have an EMPTY worklist -- a monitor that never returns nothing is not "
          "reading" % stats["empty_worklist"])
    print("%d financial assurance(s) fall due in 31-60 days: inside their own 60-day window, "
          "outside every other type's 30" % stats["wide_window"])
    print("%d reading(s)/inspection(s) fall due in 31-60 days: OUTSIDE their 30-day window, where a "
          "financial assurance would be inside its own" % stats["narrow_miss"])
    print("%d register(s) raise the escalation flag -- something already overdue, flagged by the "
          "site's own register as on track or closed" % stats["escalate"])
    print("internal consistency check: PASSED (every gold value is stated on its own register, "
          "every status and due date is that row's own rulebook lookup, every null is explained "
          "in the text)")


if __name__ == "__main__":
    main()
