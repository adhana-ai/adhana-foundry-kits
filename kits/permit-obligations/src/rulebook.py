"""THE OBLIGATION RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. The decision here is an
interval lookup plus date arithmetic over what a register happens to record, so the intervals and
the action windows have to be a thing a reader can open, read, disagree with and replace -- not a
dict buried in a Python module. `data/rulebook.json` is that file. Everything below is the
arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no permit, licence condition, regulator's guidance, industry code or statutory schedule,
and no real permit, operator, site or administering body was consulted or is named. It is not a
substitute for the permit instrument, its amendments, or a qualified person reading them. See
data/SOURCES.md, and the same sentence is printed on the kit's own UI where a reader actually reads
the worklist.

⚑ THE KIT WATCHES NOTHING. It reads one register that somebody else assembled, as at one moment,
and proposes a worklist. It does not poll, subscribe, schedule, alert, escalate, file or clear, and
nothing in it runs unattended.

⚑ FIVE CHECKS, IN THIS ORDER, AND THE ORDER IS THE WHOLE DIFFICULTY:

  1. IS THE REGISTER EVEN READABLE? No register date, no condition state the rulebook carries, or
     an obligation type it does not carry -- `not_determinable`. The kit names what it could not
     work out rather than inventing a status, because on a monitoring queue a confident wrong
     "clear" is the failure that actually hurts.
  2. DOES THE CONDITION STILL BIND? A superseded condition still printed on the register, or one
     waived in writing, is `not_binding` whatever its dates say. THIS CHECK COMES BEFORE ANY DATE
     ARITHMETIC, and that ordering is the single biggest lever on the false-alarm rate: every
     superseded and waived row on this corpus is constructed to look overdue if you compute a due
     date first.
  3. HAS THE TRIGGER FIRED? An event-triggered condition whose trigger has not occurred is
     `not_yet_due` -- a real answer, not an omission. One the register says nothing about is
     `not_determinable`, because an unrecorded trigger is not the same fact as one that did not
     fire.
  4. WHAT IS THE DUE DATE? Cycle types: the last recorded date plus the type's interval. Periodic
     reports: 31 March of the year after the year AFTER the one the register credits as filed --
     the filing DATE is never an input. A cycle row with no date, or a report with no period, stops
     here as `not_determinable`.
  5. WHERE DOES THAT DATE SIT? Before the register date: `overdue`. Within the type's OWN action
     window: `due_in_window`. Beyond it: `not_yet_due`. The window is 60 days for a financial
     assurance and 30 for everything else, and flattening that to one number gets both classes
     wrong in opposite directions.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")

STATUSES = ("overdue", "due_in_window", "not_yet_due", "not_binding", "not_determinable")

# The two statuses that put a row on somebody's worklist. Everything the kit is judged on most
# harshly -- the false-alarm rate and the missed-action count -- is defined against this pair, so
# it is named once here rather than spelled inline in the judge, the app and the baseline.
ACTIONABLE = ("overdue", "due_in_window")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

TYPES = R["obligation_types"]
CONDITION_STATES = tuple(R["condition_states"])
TRIGGER_STATES = tuple(R["trigger_states"])
OBLIGATION_TYPES = tuple(sorted(TYPES))


def parse_date(value):
    """A YYYY-MM-DD string to a date, or None.

    Deliberately strict. A monitor that guesses at "March 2026" or "Q1" has invented the very thing
    it is supposed to be reading, and every downstream number would be a number about the guess.
    """
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def parse_period(value):
    """A reporting period label to the calendar year it covers, or None.

    The register writes the period as a bare four-digit year. Anything else -- a quarter, a range,
    a blank -- returns None and the row becomes `not_determinable`, which is the right answer:
    a report credited to a period nobody can name does not tell you which year is still outstanding.
    """
    if value in (None, ""):
        return None
    s = str(value).strip()
    if len(s) == 4 and s.isdigit():
        year = int(s)
        if 1900 <= year <= 2999:
            return year
    return None


def window_days(obligation_type):
    """The action window for this type, in days, or None when the rulebook does not carry it.

    ⚠︎ PER TYPE, NEVER GLOBAL. `financial_assurance` is 60 because re-lodging a security is
    arranged with a third party; everything else is 30. A caller that hardcodes one number gets
    false alarms on the readings and missed renewals on the securities, in the same run.
    """
    spec = TYPES.get(obligation_type)
    return None if spec is None else int(spec["window_days"])


def interval_days(obligation_type):
    """The cycle length for a cycle-based type, or None for the two types that have no cycle."""
    spec = TYPES.get(obligation_type)
    if spec is None or spec.get("basis") != "cycle":
        return None
    return int(spec["interval_days"])


def report_deadline(period_year):
    """The deadline for the report covering `period_year`: 31 March of the year after it.

    Kept as its own function because it is read twice -- once to work out which period is still
    outstanding, once to date it -- and a second inline copy of the same month-day is a second
    place to change when the rulebook's deadline moves.
    """
    month, day = (int(x) for x in R["obligation_types"]["periodic_report"]["deadline_month_day"]
                  .split("-"))
    return datetime.date(period_year + 1, month, day)


def next_report_period(period_credited):
    """The reporting year that is next outstanding, given the year already credited as filed.

    ⚠︎ THE FILING DATE IS NOT AN INPUT HERE AND THAT IS THE WHOLE TRAP. A register row can carry a
    filing date from last month against a reporting period two years back; the year in between is
    still outstanding, and only this function's argument says so.
    """
    return None if period_credited is None else period_credited + 1


def due_date(register_date, ob):
    """The date the next instance of this obligation falls due, or None when the rule cannot get
    that far. Split out from `decide()` so the date arithmetic can be graded on its own -- an
    obligation found but mis-dated is a different failure from one missed entirely."""
    return decide(register_date, ob)["due_date"]


def status(register_date, ob):
    """Just the status string, or None when it is outside the rulebook's vocabulary."""
    s = decide(register_date, ob)["status"]
    return s if s in STATUSES else None


def decide(register_date, ob):
    """THE RULE, in one place. {status, reason, due_date, days_to_due, undetermined_because}.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words (so the model knows which fields matter and why), and
    evals/judge.py runs it over the model's OWN extracted values to produce the worklist that is
    scored. They cannot drift about what a status means.

    ⚠︎ THE MODEL NEVER RETURNS A STATUS. It returns what the register says; this function decides.
    That is deliberate and it is the shape of the whole kit: every status error on the published
    numbers is inherited from a reading error, and the false-alarm rate is therefore a measurement
    of reading accuracy propagated through a rule, not of a model's judgement about compliance.

    ⚠︎ IT PROPOSES. IT NEVER FILES, NOTIFIES, ESCALATES OR CLEARS. The return value is a status
    with its reasoning attached, for a person who reads the permit.
    """
    out = {"status": None, "reason": None, "due_date": None, "days_to_due": None,
           "undetermined_because": None}

    def undetermined(why, reason=None):
        out["status"] = "not_determinable"
        out["undetermined_because"] = why
        out["reason"] = reason or why
        return out

    rd = parse_date(register_date)
    if rd is None:
        return undetermined(
            "the register carries no readable register date, so nothing can be measured against it")

    state = ob.get("condition_state")
    if state not in CONDITION_STATES:
        return undetermined(
            "the condition state is missing or is not one this rulebook carries",
            "The register does not say whether this condition still binds, so its dates cannot be "
            "read as a deadline.")

    # ⚑ CHECK 2, AND IT IS SECOND FOR A REASON. Every superseded and waived row on this corpus
    # carries a stale date that would compute as overdue. Reading the state first is what stops a
    # monitoring queue filling up with conditions that were closed out months ago.
    if state == "superseded":
        out["status"] = "not_binding"
        out["reason"] = ("This condition has been superseded by a later one in a permit amendment. "
                         "It is still printed on the register and it binds nothing, whatever its "
                         "dates say.")
        return out
    if state == "waived":
        out["status"] = "not_binding"
        out["reason"] = ("This condition has been waived in writing by the administering body. It "
                         "binds nothing, whatever its dates say.")
        return out

    otype = ob.get("obligation_type")
    spec = TYPES.get(otype)
    if spec is None:
        return undetermined(
            "the obligation type is missing or is not one this rulebook carries",
            "This rulebook carries no interval or window for the obligation type recorded here, so "
            "no due date can be worked out for it.")
    basis = spec["basis"]
    win = int(spec["window_days"])

    if basis == "trigger":
        ts = ob.get("trigger_state")
        if ts == "not_occurred":
            out["status"] = "not_yet_due"
            out["reason"] = ("The event that engages this condition has not occurred, so nothing "
                             "is due under it. This is a recorded fact, not a gap in the register.")
            return out
        if ts != "occurred":
            return undetermined(
                "the register does not record whether the trigger event has occurred",
                "This condition engages only when a named event occurs, and the register does not "
                "say whether it has. An unrecorded trigger is not the same fact as one that did "
                "not fire.")
        due = parse_date(ob.get("stated_due"))
        if due is None:
            return undetermined(
                "the trigger is recorded as having occurred and no resulting due date is stated",
                "The register records the trigger event but states no date by which the response "
                "is due, so there is nothing to measure against the register date.")

    elif basis == "cycle":
        last = parse_date(ob.get("last_done"))
        if last is None:
            return undetermined(
                "the register records this obligation but carries no date for the last one",
                "This obligation runs on a cycle dated from the last time it was done, and the "
                "register carries no date for that. A logged entry with no date cannot date the "
                "next one.")
        due = last + datetime.timedelta(days=int(spec["interval_days"]))

    elif basis == "reporting_period":
        credited = parse_period(ob.get("period_credited"))
        if credited is None:
            return undetermined(
                "the register credits this report to no readable reporting period",
                "An annual report is measured by the PERIOD it covers, not by the date it was "
                "filed, and the register credits this one to no period this rulebook can read.")
        outstanding = next_report_period(credited)
        due = report_deadline(outstanding)

    else:                                           # pragma: no cover - guarded by the file itself
        return undetermined("the rulebook carries a basis this code does not implement: %r" % basis)

    out["due_date"] = due.isoformat()
    out["days_to_due"] = (due - rd).days

    if due < rd:
        out["status"] = "overdue"
        out["reason"] = ("Due %s, %d day(s) before this register was drawn."
                         % (due.isoformat(), (rd - due).days))
    elif (due - rd).days <= win:
        out["status"] = "due_in_window"
        pretty = otype.replace("_", " ")
        out["reason"] = ("Due %s, %d day(s) away, inside the %d-day action window this rulebook "
                         "gives %s%s." % (due.isoformat(), (due - rd).days, win,
                                          _article(pretty), pretty))
    else:
        out["status"] = "not_yet_due"
        pretty = otype.replace("_", " ")
        out["reason"] = ("Due %s, %d day(s) away, beyond the %d-day action window this rulebook "
                         "gives %s%s." % (due.isoformat(), (due - rd).days, win,
                                          _article(pretty), pretty))
    return out


def _article(noun):
    """"a" or "an" for a type name. Trivial, and it is here because the alternative was on the page.

    ⚠︎ FOUND BY OPENING THE UI, NOT BY ANY GATE. The reason strings below are the only prose this
    kit renders beside a status, and the shipped page read "beyond the 30-day action window this
    rulebook gives a inspection". Every gate was green over it: the status was right, the date was
    right, and nothing anywhere reads a reason string.
    """
    return "an " if noun[:1].lower() in "aeiou" else "a "


def worklist(register_date, obligations):
    """Every obligation whose status puts it on somebody's list today, in register order.

    Pure code over already-extracted values. It is the only thing this kit produces that a person
    would act on, and it is a PROPOSAL: nothing here files, notifies, escalates or clears.
    """
    out = []
    for ob in obligations or []:
        d = decide(register_date, ob)
        if d["status"] in ACTIONABLE:
            out.append(dict(d, condition_id=ob.get("condition_id"),
                            obligation_type=ob.get("obligation_type")))
    return out
