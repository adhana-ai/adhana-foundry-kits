"""THE COUNTING RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. What makes a scheduling
order hard is not reading it, it is COUNTING it: what a business day is, whether the day the clock
starts on is counted, and what happens when the last day lands on a day the court is shut. Those
three answers differ between jurisdictions and they are the whole difference between two calendars
built off the same order. So they live in a file a reader can open, disagree with and replace --
`data/rulebook.json` -- and everything below is the arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS INVENTED AND IS NOT AN AUTHORITY. Meridian Vale is not a place, the
Meridian Vale Civil Court is not a court, and MV-CR-1 reproduces no procedural code, court rule,
local rule, standing order or published holiday schedule of any real jurisdiction. Every holiday on
its list, including the name, was made up for this kit. See data/SOURCES.md, and the same sentence
is printed on the kit's own UI where a reader actually reads the dates.

⚑ FIVE WAYS AN ORDER SETS A DEADLINE, AND THE ARITHMETIC IS DIFFERENT FOR EACH:

  1. explicit_date            -- the Order names the day. Nothing is counted, and NOTHING ROLLS:
                                 an explicit 3 April that falls on a Saturday is 3 April.
  2. calendar_days_from_order -- every day counts, from the day AFTER the Order date; if the last
                                 day is not a business day it moves FORWARD until it is.
  3. calendar_days_from_event -- the same, from the day after a triggering event the Order records.
  4. business_days_from_order -- only business days count, from the day after the Order date. The
                                 result is a business day by construction, so nothing rolls.
  5. business_days_from_event -- the same, from the day after a recorded event.

⚑ AND THE SIXTH ANSWER IS "NOT YET". A period that runs from an event the Order does not date has
NO date. It is not zero days, it is not the Order date, and it is not a guess -- `compute()`
returns `due_date: None` with `undatable_because` naming what is missing. Treating an undated
trigger as though it were the Order date is the single most expensive shortcut on this shape of
work, and it is what the free floor in evals/baseline.py does, deliberately, so the cost of it is a
number on this kit's page rather than an opinion.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")

BASES = ("explicit_date", "calendar_days_from_order", "calendar_days_from_event",
         "business_days_from_order", "business_days_from_event")

FROM_EVENT = ("calendar_days_from_event", "business_days_from_event")
FROM_ORDER = ("calendar_days_from_order", "business_days_from_order")
BUSINESS = ("business_days_from_order", "business_days_from_event")
CALENDAR = ("calendar_days_from_order", "calendar_days_from_event")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

# date -> holiday name. Built once from the file so there is exactly one spelling of the set and
# no second table to drift from it.
HOLIDAYS = {h["date"]: h["name"] for h in R["holidays"]}

# The rulebook says the trigger day is day zero. Read rather than assumed: a fork that flips this
# to true gets a different calendar from the same orders, which is the whole reason it is a field.
TRIGGER_DAY_COUNTS = bool(R.get("trigger_day_counts"))

ROLLS = set(R["roll"]["applies_to"])


def parse(d):
    """An ISO date string (or a date) to a date, or None. Anything unparseable is None -- a date
    this module cannot read is a date it must not pretend to have counted from."""
    if d in (None, ""):
        return None
    if isinstance(d, datetime.date):
        return d
    try:
        return datetime.date.fromisoformat(str(d).strip())
    except ValueError:
        return None


def iso(d):
    return None if d is None else d.isoformat()


def holiday_name(d):
    """The invented holiday falling on this date, or None."""
    return HOLIDAYS.get(iso(d))


def is_business_day(d):
    """Monday to Friday, and not one of the rulebook's invented court holidays."""
    if d is None:
        return False
    return d.weekday() < 5 and iso(d) not in HOLIDAYS


def why_not_business(d):
    """The reason a date is not a business day, in words, or None when it is one."""
    if d is None:
        return None
    if d.weekday() >= 5:
        return "a %s" % d.strftime("%A")
    name = HOLIDAYS.get(iso(d))
    return ("%s, a court holiday" % name) if name else None


def next_business_day(d):
    """Forward until the calendar reaches a business day. Never backwards, and never more than a
    week -- a rulebook whose holidays swallowed seven days running would be a rulebook to fix."""
    out = d
    for _ in range(14):
        if is_business_day(out):
            return out
        out = out + datetime.timedelta(days=1)
    raise RuntimeError("no business day within 14 days of %s -- check the holiday set" % d)


def add_calendar_days(base, n):
    """`n` calendar days after `base`, with `base` itself as day zero unless the rulebook says
    otherwise. No rolling here -- rolling is a separate decision the caller makes, because it does
    not apply to every basis."""
    start = base if not TRIGGER_DAY_COUNTS else base - datetime.timedelta(days=1)
    return start + datetime.timedelta(days=n)


def add_business_days(base, n):
    """`n` BUSINESS days after `base`. Step forward one day at a time and count only the days that
    are business days; `base` itself is never counted (it is day zero) unless the rulebook flips
    `trigger_day_counts`, in which case a base that is itself a business day counts as the first.

    ⚠︎ A COUNT, NOT A MULTIPLICATION. `n // 5 * 7` is the shortcut everybody reaches for and it is
    wrong the moment a holiday lands inside the window, which is exactly the case this kit's corpus
    is built to test. Stepping is O(n) on a number that is never large here, and it is right.
    """
    out = base
    counted = 0
    if TRIGGER_DAY_COUNTS and is_business_day(base):
        counted = 1
    guard = 0
    while counted < n:
        out = out + datetime.timedelta(days=1)
        guard += 1
        if guard > 4000:
            raise RuntimeError("business-day count ran away from %s (+%s)" % (base, n))
        if is_business_day(out):
            counted += 1
    return out


def base_date_for(basis, order_date, trigger_event_date):
    """Which date the period runs from, or None when this basis needs one the caller has not got."""
    if basis in FROM_ORDER:
        return parse(order_date)
    if basis in FROM_EVENT:
        return parse(trigger_event_date)
    return None


def compute(basis, period_days, order_date, trigger_event_date, stated_date):
    """THE RULE, in one place.

    Returns {due_date, basis, rolled, rolled_from, landed_on, undatable, undatable_because,
    reason} -- `due_date` an ISO string or None.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words AND renders the rulebook into the call, and evals/judge.py
    re-runs it over the model's OWN extracted values for the no-gold consistency diagnostic. They
    cannot drift about what a deadline means.

    ⚠︎ IT COMPUTES A PROPOSED CALENDAR. IT NEVER FILES, SERVES, DOCKETS OR WAIVES ANYTHING. The
    return value is arithmetic with its own working shown; a person with the file and the real
    rules decides what goes on the calendar.
    """
    out = {"due_date": None, "basis": basis, "period_days": period_days,
           "rolled": False, "rolled_from": None, "landed_on": None,
           "undatable": False, "undatable_because": None, "reason": None}

    if basis not in BASES:
        out["undatable"] = True
        out["undatable_because"] = "the paragraph does not state a basis this rulebook carries"
        out["reason"] = out["undatable_because"]
        return out

    if basis == "explicit_date":
        d = parse(stated_date)
        if d is None:
            out["undatable"] = True
            out["undatable_because"] = "the paragraph names no date"
            out["reason"] = out["undatable_because"]
            return out
        out["due_date"] = iso(d)
        why = why_not_business(d)
        out["landed_on"] = why
        # ⚑ THE ONE PLACE THE ANSWER IS NOT THE NEXT BUSINESS DAY. An explicit date is what the
        # Order says. A reader who has learned to roll everything rolls this too, and is wrong.
        out["reason"] = ("The Order names this date, so nothing is counted%s. "
                         "A stated date is never rolled."
                         % ("" if why is None else " -- and it falls on %s, which does not move it"
                            % why))
        return out

    if period_days in (None, "") or not isinstance(period_days, int) or period_days <= 0:
        out["undatable"] = True
        out["undatable_because"] = "the paragraph states no usable number of days"
        out["reason"] = out["undatable_because"]
        return out

    base = base_date_for(basis, order_date, trigger_event_date)
    if base is None:
        out["undatable"] = True
        if basis in FROM_EVENT:
            out["undatable_because"] = "the Order records no date for the triggering event"
            out["reason"] = ("This period runs from an event the Order does not date, so no "
                             "calendar date can be computed from the four corners of the Order. "
                             "This is not a clearance and it is not the Order date.")
        else:
            out["undatable_because"] = "the Order's own date could not be read"
            out["reason"] = out["undatable_because"]
        return out

    if basis in CALENDAR:
        raw = add_calendar_days(base, period_days)
        due = next_business_day(raw) if basis in ROLLS else raw
        out["due_date"] = iso(due)
        if due != raw:
            out["rolled"] = True
            out["rolled_from"] = iso(raw)
            out["landed_on"] = why_not_business(raw)
            out["reason"] = ("%d calendar days after %s is %s, which is %s, so it moves forward to "
                             "%s." % (period_days, iso(base), iso(raw), out["landed_on"], iso(due)))
        else:
            out["reason"] = ("%d calendar days after %s is %s, a business day, so it stands."
                             % (period_days, iso(base), iso(due)))
        return out

    due = add_business_days(base, period_days)
    out["due_date"] = iso(due)
    out["reason"] = ("%d business days after %s is %s. Weekends and court holidays inside the "
                     "window were not counted, so nothing rolls."
                     % (period_days, iso(base), iso(due)))
    return out


def due_date(basis, period_days, order_date, trigger_event_date, stated_date):
    """Just the ISO date, or None. The thin wrapper the corpus generator and the scorer both use."""
    return compute(basis, period_days, order_date, trigger_event_date, stated_date)["due_date"]


def business_days_between(a, b):
    """How many business days a period of calendar days actually contained. Used only by the UI and
    by the free floor's own explanation -- never by the rule."""
    a, b = parse(a), parse(b)
    if a is None or b is None or b < a:
        return None
    n, cur = 0, a + datetime.timedelta(days=1)
    while cur <= b:
        if is_business_day(cur):
            n += 1
        cur += datetime.timedelta(days=1)
    return n
