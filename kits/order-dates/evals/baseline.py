"""A free, rules-and-regex extractor. No model, no key, no spend — scored by the same judge as a
paid run, so the two are directly comparable.

⚑ THIS FLOOR IS A DESK CALENDAR, AND ITS EXTRACTION IS DELIBERATELY GOOD. It reads the Order's
layout, finds the paragraphs that set a deadline, drops the ones that are deadline-SHAPED and set
nothing, and pulls every structured value out by regex. What it cannot do is COUNT. That split is
the whole design: if the floor were bad at reading too, the gap between it and a model would be a
gap about reading, and this kit is not about reading.

⚑ THE THREE CLAUSES, AND EACH IS A THING A REAL PERSON DOES:

  1. IF SOMEBODY HAS ALREADY WRITTEN A DATE NEXT TO THE OBLIGATION, TAKE IT. A proposed order
     arrives with counsel's own arithmetic in a parenthetical and it is right most of the time, so
     copying it is a rational-looking shortcut. `N_PARTY_SLIP` of this corpus's parentheticals are
     an ordinary diary slip on an obligation that was not even hard, and copying breaks exactly
     those.
  2. OTHERWISE COUNT FORWARD ON A WALL CALENDAR. From the Order date, or from the recorded event
     when the paragraph names one — and **treating business days and calendar days alike**, and
     **never moving a date off a weekend or a court holiday**. Those are the two errors, and they
     are not small: a 10-business-day period is fourteen calendar days, more across a holiday.
  3. AND WHEN THE TRIGGERING EVENT HAS NO DATE, COUNT FROM THE ORDER ANYWAY. ⚠︎ THIS IS THE
     EXPENSIVE ONE. The floor never says "cannot be determined" — it always produces a date, and a
     confident date on an obligation nobody can calendar yet is worse than a blank, because a blank
     gets chased and a date gets diarised.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. It
already regexes every value src/calendar_rules.py::compute() needs; calling compute() on them would
score 100 pct and tell you nothing about the model. The floor is the SHORTCUT, not the rulebook,
and the gap it opens is the gap between counting on a calendar and counting by the rules.

⚠︎ AND NOTE WHAT THE FLOOR DOES *NOT* GET WRONG. The pure-code `undatable` flag in
src/extract.py::compute() is run over the floor's own output exactly as it is over a model's, and
the floor reads the events table correctly by regex — so it raises the flag on the same rows. That
is a real finding and it is published rather than hidden: on this shape of work the "which rows
cannot be dated" question is regex-reachable and does not need a model. The arithmetic is what
needs one.
"""
import datetime
import re

from src import calendar_rules as CR
from src.extract import compute as _compute

# Ordinary words a docketing clerk keys on. This list is general — it is not a lookup of this
# corpus's own noise templates, and every phrase in it would fire on a real order written the same
# way. evals/check_labels.py asserts it separates the two registers before any run may spend.
NEGATIONS = ("struck", "withdrawn", "does not apply", "sets no date", "no date is set",
             "is vacated", "supersedes", "enlarges the time")

_PARA = re.compile(r"^(?P<n>\d{1,2})\.\s+(?P<body>.*)$", re.M)
_PAREN = re.compile(r"\((?:counsel's calendar:|the parties calculate this as|"
                    r"calculated in the proposed order as)\s*([^)]+)\)")
_EXPLICIT = re.compile(r"\b(?:on or before|no later than)\s+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})")
# ⚠︎ CASE-INSENSITIVE, AND THAT WAS A REAL DEFECT FOR ONE RUN OF check_labels. Half this corpus's
# paragraphs OPEN with the period -- "Within 45 days after ..." -- so a case-sensitive `\bwithin`
# found 190 of 260 obligations and the pre-flight refused to let the floor be published. A floor
# that cannot read half the orders would have made the counting gap this kit publishes look twice
# as wide as it is.
_PERIOD = re.compile(r"\bwithin\s+(\d{1,3})\s+(business\s+)?days\b", re.I)
_AFTER = re.compile(r"\bafter\s+(?!the date of this Order)(.+?)(?=[,.]|\s+each\b|\s+the parties\b"
                    r"|\s+counsel\b)")
# ⚠︎ `shall` IS LOAD-BEARING AND WAS ADDED AFTER THE FLOOR'S FIRST SCORED PASS. Without it the
# verb alternation matched inside the EVENT phrase "the exchange of expert reports", and six
# obligations came back with the whole rest of the sentence as their `item`. An obligation names
# its duty with a modal; an event phrase does not.
_ITEM = re.compile(r"\bshall\s+(?:exchange|file|serve)\s+(.+?)"
                   r"(?=\s+(?:on or before|no later than|within)\b|\s*\.\s*$|\s*$)")

MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
          "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}


def parse_human(s):
    """"11 February 2027" -> "2027-02-11", or None. The one conversion this corpus asks for."""
    if not s:
        return None
    m = re.match(r"\s*(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\s*$", s)
    if not m or m.group(2) not in MONTHS:
        return None
    return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


def desk_calendar_date(basis, period_days, order_date, trigger_event_date, stated_date,
                       party_calculated_date=None):
    """THE SHORTCUT, in one place, so the corpus's decoy and this floor cannot drift apart.

    ⚑ tools/build_corpus.py IMPORTS THIS FUNCTION. The wrong parentheticals planted in the corpus
    are DEFINED as "the answer a desk calendar gives", so they have to be this function's output.
    A second copy of the arithmetic would drift the day somebody improved the floor, and the decoy
    would quietly stop being the mistake it is documented as.
    """
    if party_calculated_date:
        return party_calculated_date
    if basis == "explicit_date":
        return stated_date
    n = period_days
    if not isinstance(n, int) or n <= 0:
        return None
    # ⚠︎ CLAUSE 3. An undated trigger falls back to the Order date rather than to no answer.
    base = CR.parse(trigger_event_date) or CR.parse(order_date)
    if base is None:
        return None
    # ⚠︎ CLAUSE 2. `business days` is read and then ignored, and nothing is rolled.
    return CR.iso(base + datetime.timedelta(days=n))


def _events(text):
    """The Recorded Events table as {phrase: iso_date_or_None}. Layout reading, not answer reading."""
    m = re.search(r"Recorded Events\n-+\n(.*?)(?:\n\n|\Z)", text, re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line.strip() or line.strip() == "(none recorded)":
            continue
        hit = re.match(r"^(.*?)\s{2,}(.+)$", line)
        if not hit:
            continue
        phrase, raw = hit.group(1).strip(), hit.group(2).strip()
        out[phrase] = None if raw.lower().startswith("not recorded") else parse_human(raw)
    return out


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _deadline_paragraphs(text):
    """Which numbered paragraphs actually SET a deadline, and their bodies.

    The grammar is "an obligation verb plus either a stated date or a counted period"; the
    negation list above then drops the deadline-SHAPED paragraphs that set nothing. Both halves are
    needed: the grammar alone admits every struck paragraph in this corpus, and the negation list
    alone admits every paragraph that merely mentions a date.
    """
    # ⚠︎ THE ORDERED PARAGRAPHS ARE SEPARATED BY BLANK LINES, so the "heading, rule, then everything
    # up to the next blank line" reader that finds the one-line sections above stops after
    # paragraph 1. Found the first time this floor was run against check_labels, which convicted it
    # for finding 25 of 260 obligations. The paragraph cut is src/segment.py::numbered(), the same
    # one the real extractor uses, so the floor and the model are reading the same units.
    from src import segment as SEG
    secs = {s["name"]: s for s in SEG.sections(text)}
    block = secs.get("Deadlines Ordered")
    if block is None:
        return []
    out = []
    for n, p in sorted(SEG.numbered(text).items()):
        if p["start"] < block["start"]:
            continue
        m = _PARA.match(p["text"].strip())
        if not m:
            continue
        body = " ".join(m.group("body").split())
        low = body.lower()
        if any(k in low for k in NEGATIONS):
            continue
        if not (_EXPLICIT.search(body) or _PERIOD.search(body)):
            continue
        out.append((n, body))
    return out


def _one(n, body, order_date, events):
    naked = _PAREN.sub("", body).strip()
    party = None
    p = _PAREN.search(body)
    if p:
        party = parse_human(p.group(1).strip())

    item = None
    hit = _ITEM.search(naked.rstrip("."))
    if hit:
        item = hit.group(1).strip().rstrip(".,")

    ex = _EXPLICIT.search(naked)
    if ex:
        basis, n_days, stated = "explicit_date", None, parse_human(ex.group(1))
        trigger, trigger_date = None, None
    else:
        per = _PERIOD.search(naked)
        n_days = int(per.group(1)) if per else None
        business = bool(per and per.group(2))
        ev = _AFTER.search(naked)
        stated = None
        if ev:
            trigger = ev.group(1).strip().rstrip(".,")
            trigger_date = events.get(trigger)
            basis = "business_days_from_event" if business else "calendar_days_from_event"
        else:
            trigger, trigger_date = None, None
            basis = "business_days_from_order" if business else "calendar_days_from_order"

    return {"paragraph": n, "item": item, "basis": basis, "period_days": n_days,
            "trigger_event": trigger, "trigger_event_date": trigger_date,
            "stated_date": stated, "party_calculated_date": party,
            "due_date": desk_calendar_date(basis, n_days, order_date, trigger_date, stated, party)}


def extract(text, fields=None):
    """Same return shape as src.extract.extract, so the judge cannot tell the two apart."""
    matter = _section(text, "Matter Number")
    order_date = parse_human(_section(text, "Order Date") or "")
    events = _events(text)

    rows = []
    for n, body in _deadline_paragraphs(text):
        row = _one(n, body, order_date, events)
        # The pure-code flag and the pure-code recomputation are run over the floor's own values
        # exactly as they are over a model's — a floor and a real run routed by two different code
        # paths cannot be compared honestly.
        row["undatable"] = _compute(row)
        row["computed_date"] = CR.due_date(row["basis"], row["period_days"], order_date,
                                           row["trigger_event_date"], row["stated_date"])
        # The floor reports no spans. It knows the offsets and could emit them; it does not,
        # because a span is a claim about where a value was READ from and the floor's answer for
        # `due_date` was not read from anywhere at all.
        row["spans"] = {"item": None, "trigger_event": None}
        row["rolled"] = False
        row["rolled_from"] = None
        row["landed_on"] = None
        row["working"] = "desk calendar: counted forward, business days and calendar days alike"
        rows.append(row)

    return {"matter_number": {"value": matter, "spannable": True, "span": None},
            "order_date": {"value": order_date, "spannable": False, "span": None},
            "deadlines": rows,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "raw_text": "", "parsed": True}
