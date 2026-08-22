"""THE COUNTING RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. What starts an option clock,
what perfects an extension, how extensions stack and how far ahead "about to lapse" looks are all
things a reader has to be able to open, read, disagree with and replace -- not constants buried in
a Python module. `data/rulebook.json` is that file. Everything below is the arithmetic that reads
it.

⚠︎ THE SHIPPED RULEBOOK IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no option agreement, no rights-management system's own logic, no guild or trade body
schedule, no standard form and no statute. The real authority for any option is the executed
agreement and the lawyer who reads it. See data/SOURCES.md, and the same sentence is printed on the
kit's own UI where a reader actually reads the answer.

⚑ THIS KIT WATCHES NOTHING. It reads ONE snapshot of a register that somebody else assembled and
proposes a worklist. It does not poll, subscribe, schedule, alert, escalate, file or clear, and
nothing in it runs unattended. There is no daemon here and there is no state between documents.

⚑ THE COUNT, IN ORDER, AND THE ORDER IS THE WHOLE DIFFICULTY:

  1. WHAT STARTS THE CLOCK? A grant-date clock starts on the grant date -- and where two entries
     disagree about it, the start is NOT SETTLED and the answer is `not_determinable`. A
     triggering-event clock starts on the date the event occurred, and until it occurs there is
     nothing to count from. An option whose clock has not started is not an option with a long
     time left.
  2. WHICH EXTENSIONS ACTUALLY COUNT? Only PERFECTED ones. A payment-controlled extension needs a
     payment reference and a payment date; a notice-controlled one needs notice served on the
     GRANTOR OF RECORD. "recorded: exercised" is a clerk's entry, not an act.
  3. ADD THE MONTHS, CONSECUTIVELY, FROM THE CLOCK START. Not from the date an extension was
     exercised. Calendar months, clamped to the end of a short month, added in one step from the
     original start so the clamping cannot compound.
  4. COMPARE AGAINST THE AS-OF DATE AND THE WINDOW. On or before it: `lapsed`. Inside the window:
     `lapsing`. Beyond it: `live`.

⚠︎ THE REGISTER'S OWN STATUS LINE IS NEVER AN INPUT TO ANY OF THAT, and neither is the clerk's
note. Both are extracted, both are displayed, and neither moves a day.
"""
import calendar
import datetime
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")

STATUSES = ("live", "lapsing", "lapsed", "not_determinable")
CLOCK_BASES = ("grant_date", "triggering_event")
TRIGGER_STATES = ("not_applicable", "occurred", "not_occurred")
REGISTER_STATES = ("live", "lapsed")

# The statuses that put a row on somebody's worklist. `not_determinable` is inside this set
# deliberately -- a record nobody can date is a record somebody has to open, and treating an
# unknown as a pass is the one thing a monitoring queue must never do.
NEEDS_ACTION = ("lapsing", "lapsed", "not_determinable")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

WINDOW_DAYS = int(R["window_days"])


def parse_date(value):
    """An ISO date, or None. Deliberately strict: a date this function cannot read is a date the
    count must not guess at, and `None` flows through to `not_determinable` rather than to a
    plausible-looking expiry."""
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def add_months(start, months):
    """Calendar months, added in ONE step from the original date, clamped to the end of a short
    target month.

    ⚠︎ ADDED IN ONE STEP ON PURPOSE. Adding twelve months as twelve separate additions clamps
    twelve times, so 2025-01-31 walks to 2025-02-28 and then never gets its 31st back -- an option
    granted on the last day of January would expire three days early after a year. One addition
    from the original start date cannot compound, which is why the rulebook states it that way and
    why this function takes the WHOLE term rather than being called in a loop.
    """
    if start is None or months is None:
        return None
    months = int(months)
    y = start.year + (start.month - 1 + months) // 12
    m = (start.month - 1 + months) % 12 + 1
    d = min(start.day, calendar.monthrange(y, m)[1])
    return datetime.date(y, m, d)


def clock_start(clock_basis, trigger_status, option_granted_date, trigger_date):
    """(iso_date_or_None, why_not_or_None) -- the date the option period actually runs from.

    ⚑ THIS IS WHERE THREE OF THIS CORPUS'S FIVE PLANTED CONFUSIONS ARE SETTLED, and each of them
    is settled by REFUSING rather than by picking:

      - a triggering-event clock whose event has not occurred -> nothing to count from;
      - a grant-date clock with no settled grant date (two entries disagreeing) -> nothing to
        count from, and the rule explicitly does not break the tie;
      - a triggering-event clock whose event HAS occurred, on a record that also happens to carry
        two disagreeing grant dates -> the grant date is not an input, so the disagreement is
        IMMATERIAL and the count proceeds. Flagging that record is a false alarm, and a false
        alarm on a monitoring queue costs a person the same as a real one.
    """
    if clock_basis == "triggering_event":
        if trigger_status != "occurred":
            return None, ("the option clock runs from a triggering event, and the register does "
                          "not record that event as having occurred")
        d = parse_date(trigger_date)
        if d is None:
            return None, ("the option clock runs from a triggering event the register records as "
                          "occurred, but states no date for it")
        return d, None
    if clock_basis == "grant_date":
        d = parse_date(option_granted_date)
        if d is None:
            return None, ("the option clock runs from the grant date, and the register does not "
                          "settle a single grant date for this grant")
        return d, None
    return None, "the register does not state what starts the option clock"


def expiry(clock_basis, trigger_status, option_granted_date, trigger_date,
           initial_term_months, extension_months_each, extensions_perfected):
    """(iso_expiry_or_None, why_not_or_None). Only PERFECTED extensions are added."""
    start, why = clock_start(clock_basis, trigger_status, option_granted_date, trigger_date)
    if start is None:
        return None, why
    try:
        initial = int(initial_term_months)
        each = int(extension_months_each)
        n = int(extensions_perfected)
    except (TypeError, ValueError):
        return None, ("the register does not state the term, the extension length or how many "
                      "extensions were perfected as a whole number of months")
    if initial < 0 or each < 0 or n < 0:
        return None, "a negative term, extension length or extension count cannot be counted"
    end = add_months(start, initial + each * n)
    return (end.isoformat() if end else None), None


def decide(register_as_of, clock_basis, trigger_status, option_granted_date, trigger_date,
           initial_term_months, extension_months_each, extensions_perfected):
    """THE RULE, in one place. {status, expiry_date, reason, days_to_expiry, undetermined_because}.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    values, both to produce the published answer and for the no-gold consistency diagnostic. They
    cannot drift about what `lapsing` means.

    ⚠︎ IT PROPOSES A WORKLIST. IT NEVER EXERCISES, RENEWS, LAPSES OR RELEASES ANYTHING. The return
    value is a status with the count that produced it attached; a qualified person reads the
    agreement. Nothing in this kit writes, dispatches, files or clears anything.
    """
    out = {"status": None, "expiry_date": None, "reason": None, "days_to_expiry": None,
           "undetermined_because": None, "clock_start_date": None, "window_days": WINDOW_DAYS}

    as_of = parse_date(register_as_of)
    if as_of is None:
        out["status"] = "not_determinable"
        out["undetermined_because"] = "the register does not state the date it is current as at"
        out["reason"] = ("Without the date this snapshot is current as at, there is nothing to "
                         "measure an expiry against. This is not a clearance.")
        return out

    start, why = clock_start(clock_basis, trigger_status, option_granted_date, trigger_date)
    out["clock_start_date"] = start.isoformat() if start else None

    iso, why2 = expiry(clock_basis, trigger_status, option_granted_date, trigger_date,
                       initial_term_months, extension_months_each, extensions_perfected)
    if iso is None:
        out["status"] = "not_determinable"
        out["undetermined_because"] = why or why2
        out["reason"] = ("%s, so no expiry can be counted. This is not a clearance -- it is a "
                         "record somebody has to open." % (out["undetermined_because"] or
                                                          "The count cannot be started"))
        return out

    end = parse_date(iso)
    out["expiry_date"] = iso
    out["days_to_expiry"] = (end - as_of).days

    try:
        n = int(extensions_perfected)
        each = int(extension_months_each)
        initial = int(initial_term_months)
    except (TypeError, ValueError):                 # unreachable: expiry() already returned
        n = each = initial = 0
    added = ("%d month%s of initial term" % (initial, "" if initial == 1 else "s")
             + ("" if n == 0 else ", plus %d perfected extension%s of %d month%s"
                % (n, "" if n == 1 else "s", each, "" if each == 1 else "s")))

    if out["days_to_expiry"] <= 0:
        out["status"] = "lapsed"
        out["reason"] = ("The option ran from %s -- %s -- and expired on %s, %d day(s) before this "
                         "register was current. Whatever the status line says, the term is spent."
                         % (out["clock_start_date"], added, iso, -out["days_to_expiry"]))
    elif out["days_to_expiry"] <= WINDOW_DAYS:
        out["status"] = "lapsing"
        out["reason"] = ("The option ran from %s -- %s -- and expires on %s, in %d day(s), inside "
                         "the %d-day window this rulebook watches."
                         % (out["clock_start_date"], added, iso, out["days_to_expiry"],
                            WINDOW_DAYS))
    else:
        out["status"] = "live"
        out["reason"] = ("The option ran from %s -- %s -- and expires on %s, in %d day(s), beyond "
                         "the %d-day window. Nothing is due on it today."
                         % (out["clock_start_date"], added, iso, out["days_to_expiry"],
                            WINDOW_DAYS))
    return out


def status_of(values):
    """Just the status string, from a dict of extracted values, or None when the values are
    outside the vocabulary the rulebook can count."""
    d = decide(values.get("register_as_of"), values.get("clock_basis"),
               values.get("trigger_status"), values.get("option_granted_date"),
               values.get("trigger_date"), values.get("initial_term_months"),
               values.get("extension_months_each"), values.get("extensions_perfected"))
    return d["status"] if d["status"] in STATUSES else None
