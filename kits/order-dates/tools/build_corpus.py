#!/usr/bin/env python3
"""Generate synthetic scheduling orders and their gold calendars, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one scheduling order per file) and data/gold.jsonl, byte-identical on
every run. Every court, matter number, event and obligation here is invented; no real court, judge,
case, docket number, party or jurisdiction is named anywhere, and no real holiday appears in the
rulebook this corpus is counted against. Nothing is fetched and nothing is licensed from anybody,
so the corpus ships under this repo's MIT licence.

⚠︎ NO PROCEDURAL CODE, COURT RULE, LOCAL RULE, STANDING ORDER OR PUBLISHED HOLIDAY SCHEDULE IS
REPRODUCED. The rulebook this corpus is built against is `data/rulebook.json` (MV-CR-1), which was
written for this kit and is illustrative rather than authoritative. See data/SOURCES.md.

⚑ GOLD `due_date` IS AN ARITHMETIC RESULT, NOT A LABEL SOMEBODY TYPED. Every one of them is
src/calendar_rules.py::compute() run over the same structured values the paragraph itself states --
the same function src/prompt.py states to the model in words (and renders the rulebook for), and
the same one evals/judge.py re-runs over the model's OWN reply for the no-gold diagnostic. It is
never derived from the parenthetical a party wrote next to the obligation, and that parenthetical
never feeds the label.

⚑ THE FIVE WAYS AN ORDER SETS A DEADLINE, AND THE ONE WAY IT SETS NONE. Each bucket below exists
because a reader who applies one rule everywhere gets that bucket wrong:

  explicit_plain        -- the Order names the day. Nothing is counted.
  explicit_nonbusiness  -- the Order names a day that falls on a weekend or a court holiday. IT
                           DOES NOT MOVE. A reader who has learned to roll everything rolls this
                           too, and is wrong.
  cal_order_plain       -- N calendar days from the Order, landing on a business day.
  cal_order_roll        -- N calendar days from the Order, landing on a weekend or holiday, so it
                           moves FORWARD -- sometimes two days, when the neighbouring Monday or
                           Friday is itself a court holiday.
  cal_event_plain       -- the same counted from a recorded triggering event, landing clean.
  cal_event_roll        -- the same, rolling.
  bus_order / bus_event -- N BUSINESS days. Counting these as calendar days is the single most
                           common desk error and it is wrong by two days a week, more across a
                           holiday.
  undatable             -- the period runs from an event the Order does not date. THERE IS NO
                           DATE. Not zero days, not the Order date, not a guess.

⚑ THE PLANTED AMBIGUITY: a party's own arithmetic, written next to the obligation, and wrong on
`N_PARTY_WRONG` of the obligations that carry it. `N_PARTY_DESK` of those wrong ones are exactly
the answer evals/baseline.py's desk-calendar floor produces -- somebody counted it on a wall
calendar -- and `N_PARTY_SLIP` are an ordinary diary slip on an obligation whose arithmetic is not
even hard. Anything that copies the parenthetical fails those by construction. Anything that runs
the rulebook gets them right.
"""
import argparse
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import calendar_rules as CR                # noqa: E402
# ⚑ THE FLOOR'S ARITHMETIC IS IMPORTED, NOT RE-TYPED HERE, AND THAT IS LOAD-BEARING. The wrong
# parentheticals in this corpus are DEFINED as "the answer a desk calendar gives", so they have to
# be that function's output and not a second copy of it. A copy would drift the day somebody
# improved the floor, and the decoy would quietly stop being the mistake it is documented as.
from evals.baseline import desk_calendar_date       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_ORDERS = 52

MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")

# ⚑ EVERY COMPOSITION HERE IS AN EXACT COUNT, SHUFFLED -- never a probability drawn per record.
# A sibling kit in this series asked its generator for 40 pct ambiguity and got 51 pct on the first
# build; a count 1.7 standard deviations off its own design is sampling noise being published as a
# corpus property. So the buckets are dealt, and every constructor is asserted against the rulebook
# as it runs.
BUCKETS = [
    ("explicit_plain", 44),          # the Order names the day, and it is a business day
    ("explicit_nonbusiness", 18),    # the Order names a day that is NOT -- and it does not move
    ("cal_order_plain", 38),         # N calendar days from the Order, landing clean
    ("cal_order_roll", 26),          # N calendar days from the Order, rolling forward
    ("cal_event_plain", 30),         # N calendar days from a recorded event, landing clean
    ("cal_event_roll", 20),          # N calendar days from a recorded event, rolling forward
    ("bus_order", 32),               # N BUSINESS days from the Order
    ("bus_event", 28),               # N BUSINESS days from a recorded event
    ("undatable", 24),               # the triggering event is not dated -- there is no date
]
N_OBLIGATIONS = sum(c for _n, c in BUCKETS)          # 260

# Obligations per order, and non-obligation paragraphs per order. Both dealt, so no order has a
# predictable shape and no reader can count the answers off the file length.
OBLIG_PER_ORDER = [(4, 13), (5, 26), (6, 13)]        # 13*4 + 26*5 + 13*6 = 260
NOISE_PER_ORDER = [(1, 26), (2, 26)]                 # 78 non-obligation paragraphs

N_STRUCK = 30            # of the 78, this many are a deadline-shaped paragraph that sets NO date
N_PARTY = 96             # obligations carrying a party's own calculated date
N_PARTY_DESK = 28        # ... of which these are the DESK-CALENDAR answer, and wrong
N_PARTY_SLIP = 12        # ... and these are an ordinary diary slip, wrong on an easy obligation
N_PARTY_WRONG = N_PARTY_DESK + N_PARTY_SLIP          # 40

# The Order's own date always falls on a business day, and so does every recorded event. A court
# does not enter an order on a Sunday, and a corpus whose base dates wander onto weekends would be
# measuring the generator rather than the counting.
FIRST_ORDER_DAY = datetime.date(2027, 1, 5)
LAST_ORDER_DAY = datetime.date(2027, 10, 29)

# Invented divisions and courtrooms. None of this is mapped by any field, so none of it is ever
# sent to a provider -- it is the visible half of what src/select.py saves.
#
# ⚠︎ "Commercial List" STOOD IN THIS LIST AND WAS CHANGED, even though this section never leaves
# the machine and no field reads it. It is a real docket name in more than one jurisdiction, and a
# label that reads as a real institution inside an invented court is exactly the thing a reader has
# to stop and check. The replacement is the SAME LENGTH on purpose: the corpus stayed at 57,002
# bytes, data/gold.jsonl came back byte-identical, and no published figure had to be restated.
COURT = "Meridian Vale Civil Court"
DIVISIONS = ["Civil Division A, Courtroom 2", "Civil Division B, Courtroom 4",
             "Civil Division C, Courtroom 1", "Civil Division D, Courtroom 6",
             "Vale Commercial, Courtroom 3"]

# Ordinary docketing items, as generic nouns. No rule name, no form number, nothing that could be
# mistaken for a real court's own vocabulary.
ITEMS = [
    "initial disclosures", "expert disclosures", "rebuttal expert disclosures",
    "responses to written discovery", "the joint status report", "the witness list",
    "the exhibit list", "objections to the exhibit list", "dispositive motions",
    "the opposition to dispositive motions", "the pretrial statement",
    "the mediation certificate", "supplemental briefing", "the privilege log",
    "the settlement conference statement", "the damages computation",
    "the deposition designations", "the proposed findings",
]

# Triggering events, written as the plain phrase the Recorded Events table uses, so an extracted
# `trigger_event` is a verbatim copy rather than a paraphrase somebody has to adjudicate.
EVENTS = [
    "service of written discovery",
    "the case management conference",
    "the deposition of the designated representative",
    "entry of the protective order",
    "the filing of the amended pleading",
    "completion of document production",
    "appointment of the neutral",
    "the ruling on the pending motion",
    "the close of fact discovery",
    "the exchange of expert reports",
]

CAL_PERIODS = (7, 10, 14, 15, 20, 21, 25, 28, 30, 35, 40, 45, 60, 75, 90, 120)
BUS_PERIODS = (3, 5, 7, 10, 12, 14, 15, 20, 25)

# Wordings. None of them opens with the item, so `item` is always stated in lower case exactly as
# the field asks for it -- "verbatim, and also in lower case" is a contradiction the moment a
# sentence starts with the thing you want copied.
W_EXPLICIT = [
    "The parties shall exchange %(item)s on or before %(date)s.",
    "Each party shall file %(item)s no later than %(date)s.",
    "Counsel shall serve %(item)s on or before %(date)s.",
]
W_CAL_ORDER = [
    "Within %(n)d days of the date of this Order, the parties shall exchange %(item)s.",
    "The parties shall file %(item)s within %(n)d days after the date of this Order.",
    "Each party shall serve %(item)s within %(n)d days of the date of this Order.",
]
W_CAL_EVENT = [
    "The parties shall serve %(item)s within %(n)d days after %(event)s.",
    "Within %(n)d days after %(event)s, each party shall file %(item)s.",
    "Each party shall exchange %(item)s within %(n)d days after %(event)s.",
]
W_BUS_ORDER = [
    "The parties shall file %(item)s within %(n)d business days after the date of this Order.",
    "Within %(n)d business days of the date of this Order, counsel shall serve %(item)s.",
]
W_BUS_EVENT = [
    "Within %(n)d business days after %(event)s, the parties shall file %(item)s.",
    "Each party shall serve %(item)s within %(n)d business days after %(event)s.",
]

PARENTHETICAL = [
    " (counsel's calendar: %s)",
    " (the parties calculate this as %s)",
    " (calculated in the proposed order as %s)",
]

# Paragraphs that set NO deadline. Four of the seven carry a date or a number, because a paragraph
# that looks nothing like a deadline tests nothing.
W_NOISE = [
    "The trial previously set for %(date)s is vacated and will be reset by separate order.",
    "The parties shall confer in good faith regarding the scope of expert discovery.",
    "This Order supersedes the scheduling order entered %(date)s in its entirety.",
    "Each party shall bear its own costs of the case management conference.",
    "The page limit for any dispositive motion is thirty pages, exclusive of exhibits.",
    "Nothing in this Order enlarges the time to complete fact discovery.",
    "Any request to modify the dates set above shall be made by written motion.",
]

# ⚑ THE SECOND DECOY, AND IT IS DEADLINE-SHAPED ON PURPOSE. A struck paragraph states an item, a
# number and a unit -- everything an obligation states -- and sets no date at all. Anything that
# pattern-matches "within N days" into a docket entry produces an obligation the Order does not
# impose, which on a docketing desk is a diary entry nobody owes and somebody has to clear.
W_STRUCK = [
    "The deadline for %(item)s, previously fixed at within %(n)d days of the date of this Order, "
    "is STRUCK. No date is set by this paragraph.",
    "The requirement that %(item)s be served within %(n)d business days after the case management "
    "conference is WITHDRAWN and sets no date here.",
    "Paragraph 2 of the scheduling order entered %(date)s, requiring %(item)s within %(n)d days, "
    "does not apply in this matter and sets no date.",
]


def human(d):
    """A date as a Meridian Vale order writes it: 11 February 2027. One format, everywhere in the
    document, so a model that returns ISO has done a real conversion rather than a copy."""
    if d is None:
        return "not recorded"
    d = CR.parse(d)
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


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


def _business_day_in(rng, lo, hi):
    for _ in range(500):
        d = lo + datetime.timedelta(days=rng.randint(0, (hi - lo).days))
        if CR.is_business_day(d):
            return d
    raise RuntimeError("no business day between %s and %s" % (lo, hi))


# ---------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns the structured values of ONE obligation and each is
# asserted against the rulebook in build_all -- a constructor that quietly stops producing its own
# bucket is exactly the defect an exact composition exists to prevent.
# ---------------------------------------------------------------------------------------------

def _explicit(rng, order_date, want_business):
    for _ in range(2000):
        d = order_date + datetime.timedelta(days=rng.randint(21, 210))
        if CR.is_business_day(d) == want_business:
            return {"basis": "explicit_date", "period_days": None, "trigger_event": None,
                    "trigger_event_date": None, "stated_date": CR.iso(d)}
    raise RuntimeError("explicit: exhausted")


def _from_order(rng, order_date, business, want_roll):
    periods = list(BUS_PERIODS if business else CAL_PERIODS)
    rng.shuffle(periods)
    basis = "business_days_from_order" if business else "calendar_days_from_order"
    for n in periods:
        if not business:
            raw = CR.add_calendar_days(order_date, n)
            if CR.is_business_day(raw) == want_roll:
                continue
        return {"basis": basis, "period_days": n, "trigger_event": None,
                "trigger_event_date": None, "stated_date": None}
    raise RuntimeError("from_order: no period gives roll=%r at %s" % (want_roll, order_date))


def _from_event(rng, order_date, events, business, want_roll):
    """Pick (or open) a recorded event on this order and a period that satisfies the bucket.

    `events` is this order's own table and is mutated: an event already on it is reused where it
    works, which is what a real order looks like -- several obligations hanging off one conference.
    """
    basis = "business_days_from_event" if business else "calendar_days_from_event"
    periods = list(BUS_PERIODS if business else CAL_PERIODS)
    recorded = [k for k, v in events.items() if v is not None]
    unused = [e for e in EVENTS if e not in events]
    rng.shuffle(unused)

    for _ in range(600):
        if recorded and (not unused or rng.random() < 0.45):
            phrase = rng.choice(recorded)
            base = CR.parse(events[phrase])
            fresh = False
        elif unused:
            phrase = unused[0]
            base = _business_day_in(rng, order_date - datetime.timedelta(days=14),
                                    order_date + datetime.timedelta(days=60))
            fresh = True
        else:
            break
        rng.shuffle(periods)
        for n in periods:
            if business:
                due = CR.parse(CR.add_business_days(base, n).isoformat())
            else:
                raw = CR.add_calendar_days(base, n)
                if CR.is_business_day(raw) == want_roll:
                    continue
                due = CR.next_business_day(raw)
            # A deadline the Order sets must fall AFTER the Order. An event 14 days back with a
            # 7-day period would otherwise produce a date that was already past when it was made.
            if due <= order_date:
                continue
            if fresh:
                events[phrase] = CR.iso(base)
            return {"basis": basis, "period_days": n, "trigger_event": phrase,
                    "trigger_event_date": CR.iso(base), "stated_date": None}
    raise RuntimeError("from_event: exhausted at %s" % order_date)


def _undated_event(rng, order_date, events, business):
    """The obligation with no date: its triggering event is on the table and says `not recorded`."""
    unused = [e for e in EVENTS if e not in events]
    if not unused:
        raise RuntimeError("undatable: no spare event phrase")
    phrase = rng.choice(unused)
    events[phrase] = None
    basis = "business_days_from_event" if business else "calendar_days_from_event"
    n = rng.choice(BUS_PERIODS if business else CAL_PERIODS)
    return {"basis": basis, "period_days": n, "trigger_event": phrase,
            "trigger_event_date": None, "stated_date": None}


EXPECTED = {
    "explicit_plain": ("explicit_date", True),
    "explicit_nonbusiness": ("explicit_date", False),
    "cal_order_plain": ("calendar_days_from_order", False),
    "cal_order_roll": ("calendar_days_from_order", True),
    "cal_event_plain": ("calendar_days_from_event", False),
    "cal_event_roll": ("calendar_days_from_event", True),
    "bus_order": ("business_days_from_order", False),
    "bus_event": ("business_days_from_event", False),
    "undatable": (None, False),
}


def _make(rng, bucket, order_date, events, undatable_business):
    if bucket == "explicit_plain":
        return _explicit(rng, order_date, want_business=True)
    if bucket == "explicit_nonbusiness":
        return _explicit(rng, order_date, want_business=False)
    if bucket == "cal_order_plain":
        return _from_order(rng, order_date, business=False, want_roll=False)
    if bucket == "cal_order_roll":
        return _from_order(rng, order_date, business=False, want_roll=True)
    if bucket == "cal_event_plain":
        return _from_event(rng, order_date, events, business=False, want_roll=False)
    if bucket == "cal_event_roll":
        return _from_event(rng, order_date, events, business=False, want_roll=True)
    if bucket == "bus_order":
        return _from_order(rng, order_date, business=True, want_roll=False)
    if bucket == "bus_event":
        return _from_event(rng, order_date, events, business=True, want_roll=False)
    if bucket == "undatable":
        return _undated_event(rng, order_date, events, business=undatable_business)
    raise RuntimeError("unknown bucket %r" % bucket)


def _render(ob):
    """The paragraph body for one obligation, with its parenthetical if it carries one."""
    d = {"item": ob["item"], "n": ob["period_days"], "event": ob["trigger_event"],
         "date": human(ob["stated_date"])}
    text = ob["wording"] % d
    if ob["party_calculated_date"]:
        text += ob["party_wording"] % human(ob["party_calculated_date"])
    return text


def build_all(rng, n_orders=N_ORDERS):
    buckets = _deal(rng, N_OBLIGATIONS, BUCKETS)
    per_order = _deal(rng, n_orders, OBLIG_PER_ORDER)
    noise_per_order = _deal(rng, n_orders, NOISE_PER_ORDER)
    if sum(per_order) != len(buckets):
        # A --n other than the design keeps the shape roughly; the exact deal only holds at 52.
        buckets = (buckets * 20)[:sum(per_order)]
    struck_flags = _deal(rng, sum(noise_per_order),
                         [(True, N_STRUCK), (False, sum(noise_per_order) - N_STRUCK)])
    undatable_business = _deal(rng, len([b for b in buckets if b == "undatable"]) or 1,
                               [(True, 12), (False, 12)])

    orders = []
    bi = ni = ui = 0
    for i in range(1, n_orders + 1):
        order_date = _business_day_in(rng, FIRST_ORDER_DAY, LAST_ORDER_DAY)
        events, items_used, obligations = {}, set(), []

        for _ in range(per_order[i - 1]):
            bucket = buckets[bi]
            bi += 1
            ub = undatable_business[ui % len(undatable_business)] if bucket == "undatable" else False
            if bucket == "undatable":
                ui += 1
            vals = _make(rng, bucket, order_date, events, ub)
            item = rng.choice([x for x in ITEMS if x not in items_used])
            items_used.add(item)
            wording = {"explicit_date": W_EXPLICIT,
                       "calendar_days_from_order": W_CAL_ORDER,
                       "calendar_days_from_event": W_CAL_EVENT,
                       "business_days_from_order": W_BUS_ORDER,
                       "business_days_from_event": W_BUS_EVENT}[vals["basis"]]
            ob = dict(vals, bucket=bucket, item=item, wording=rng.choice(wording),
                      order_date=CR.iso(order_date), party_calculated_date=None,
                      party_kind=None, party_wording=rng.choice(PARENTHETICAL))
            r = CR.compute(ob["basis"], ob["period_days"], CR.iso(order_date),
                           ob["trigger_event_date"], ob["stated_date"])
            ob["due_date"] = r["due_date"]
            ob["rolled"] = r["rolled"]
            ob["rule_note"] = r["reason"]
            ob["undatable"] = r["undatable"]
            obligations.append(ob)

        noise = []
        for _ in range(noise_per_order[i - 1]):
            struck = struck_flags[ni]
            ni += 1
            far = order_date + datetime.timedelta(days=rng.randint(30, 240))
            back = order_date - datetime.timedelta(days=rng.randint(30, 200))
            d = {"item": rng.choice(ITEMS), "n": rng.choice(CAL_PERIODS),
                 "date": human(far if rng.random() < 0.5 else back)}
            noise.append({"struck": struck,
                          "text": (rng.choice(W_STRUCK) if struck else rng.choice(W_NOISE)) % d})

        orders.append({"order_date": CR.iso(order_date), "events": events,
                       "obligations": obligations, "noise": noise,
                       "division": rng.choice(DIVISIONS),
                       "matter": "MVC-27-%05d" % rng.randint(10000, 99999)})

    _assign_parentheticals(rng, orders)
    _number_and_render(rng, orders)
    return orders


def _assign_parentheticals(rng, orders):
    """⚑ THE DECOY IS ASSIGNED GLOBALLY AND EXACTLY, AFTER EVERY OBLIGATION EXISTS.

    Three populations, and the split is the point:
      - DESK: the parenthetical is the answer evals/baseline.py's desk-calendar floor produces, on
        an obligation where that answer is WRONG. Somebody counted it on a wall calendar.
      - SLIP: the parenthetical is an ordinary diary slip on an obligation whose arithmetic is not
        even hard -- the floor would have got it right and copying the parenthetical breaks it.
      - RIGHT: the parenthetical agrees with the rulebook. Most parties get most dates right, and a
        decoy that is wrong every time is a decoy nobody would ever be fooled by.
    """
    every = [ob for o in orders for ob in o["obligations"]]
    desk = {}
    for ob in every:
        desk[id(ob)] = desk_calendar_date(ob["basis"], ob["period_days"], ob["order_date"],
                                          ob["trigger_event_date"], ob["stated_date"], None)

    differs = [ob for ob in every if desk[id(ob)] != ob["due_date"]]
    agrees = [ob for ob in every if desk[id(ob)] == ob["due_date"] and ob["due_date"]]
    rng.shuffle(differs)
    rng.shuffle(agrees)

    if len(differs) < N_PARTY_DESK:
        raise RuntimeError("only %d obligations where the desk calendar is wrong; need %d"
                           % (len(differs), N_PARTY_DESK))
    chosen_desk = differs[:N_PARTY_DESK]
    chosen_slip = agrees[:N_PARTY_SLIP]
    # Membership by identity, never by ==: two obligations on two different orders can be equal
    # dicts, and `in` on a list of dicts would quietly exclude the wrong one.
    taken = {id(ob) for ob in chosen_desk} | {id(ob) for ob in chosen_slip}
    rest = [ob for ob in every if id(ob) not in taken and ob["due_date"]]
    rng.shuffle(rest)
    chosen_right = rest[:N_PARTY - N_PARTY_WRONG]

    for ob in chosen_desk:
        ob["party_calculated_date"] = desk[id(ob)] or ob["order_date"]
        ob["party_kind"] = "desk_calendar"
    for k, ob in enumerate(chosen_slip):
        d = CR.parse(ob["due_date"])
        slip = d + datetime.timedelta(days=31 if k % 2 == 0 else -4)
        ob["party_calculated_date"] = CR.iso(slip)
        ob["party_kind"] = "diary_slip"
    for ob in chosen_right:
        ob["party_calculated_date"] = ob["due_date"]
        ob["party_kind"] = "agrees"


def _number_and_render(rng, orders):
    """Shuffle each order's paragraphs together, number them, and write the document text."""
    for oi, o in enumerate(orders, 1):
        slots = [("ob", ob) for ob in o["obligations"]] + [("noise", nz) for nz in o["noise"]]
        rng.shuffle(slots)
        lines = []
        for k, (kind, payload) in enumerate(slots, 1):
            if kind == "ob":
                payload["paragraph"] = k
                body = _render(payload)
            else:
                payload["paragraph"] = k
                body = payload["text"]
            lines.append("%d. %s" % (k, body))
        o["paragraph_block"] = "\n\n".join(lines)
        o["order_id"] = "ORD-%04d" % oi

        ev = o["events"]
        # A recorded event nothing hangs off is ordinary and is left in: a table that contains
        # exactly the events the obligations use would tell a reader which line to look at.
        width = max([len(k) for k in ev] or [10]) + 3
        ev_lines = ["%s%s" % (k.ljust(width), human(v)) for k, v in ev.items()] or \
                   ["(none recorded)"]

        text = "\n".join([
            _underline("Court"), COURT, "",
            _underline("Division and Courtroom"), o["division"], "",
            _underline("Matter Number"), o["matter"], "",
            _underline("Order Date"), human(o["order_date"]), "",
            _underline("Recorded Events"), "\n".join(ev_lines), "",
            _underline("Deadlines Ordered"), o["paragraph_block"], "",
        ]) + "\n"
        o["text"] = text


def _gold(o):
    return {
        "order_id": o["order_id"],
        "matter_number": o["matter"],
        "order_date": o["order_date"],
        "deadlines": [
            {"paragraph": ob["paragraph"],
             "item": ob["item"],
             "basis": ob["basis"],
             "period_days": ob["period_days"],
             "trigger_event": ob["trigger_event"],
             "trigger_event_date": ob["trigger_event_date"],
             "stated_date": ob["stated_date"],
             "party_calculated_date": ob["party_calculated_date"],
             "due_date": ob["due_date"],
             # Recorded, never scored, and the reason is worth stating: the paragraph number
             # addresses the obligation exactly, so asking a model to echo a whole sentence back
             # would be output tokens spent on a join key that already exists. It is here because
             # a gold calendar a person cannot read next to its own order is not checkable.
             "paragraph_text": _para_text(o, ob["paragraph"]),
             "rolled": ob["rolled"],
             "undatable": ob["undatable"],
             "bucket": ob["bucket"],
             "party_kind": ob.get("party_kind"),
             "rule_note": ob["rule_note"]}
            for ob in sorted(o["obligations"], key=lambda x: x["paragraph"])
        ],
        "non_deadline_paragraphs": sorted(nz["paragraph"] for nz in o["noise"]),
        "struck_paragraphs": sorted(nz["paragraph"] for nz in o["noise"] if nz["struck"]),
    }


def _para_text(o, n):
    for line in o["paragraph_block"].split("\n\n"):
        if line.startswith("%d. " % n):
            return line.split(". ", 1)[1]
    raise RuntimeError("%s: paragraph %d not rendered" % (o["order_id"], n))


def _verify(orders):
    """Every gold value must be stated in the order it labels, and every gold due_date must be that
    obligation's own rulebook computation. A corpus whose labels are not readable off its own text
    is not a corpus, it is a second opinion."""
    from src import segment as SEG
    for o in orders:
        text, g = o["text"], _gold(o)
        assert g["matter_number"] in text, "%s: matter number not stated" % o["order_id"]
        assert human(g["order_date"]) in text, "%s: order date not stated" % o["order_id"]
        paras = SEG.numbered(text)
        for d in g["deadlines"]:
            p = paras.get(d["paragraph"])
            assert p is not None, "%s: paragraph %d not cut" % (o["order_id"], d["paragraph"])
            assert d["item"] in p["text"], \
                "%s p%d: item %r not in its own paragraph" % (o["order_id"], d["paragraph"],
                                                              d["item"])
            if d["trigger_event"]:
                assert d["trigger_event"] in p["text"], \
                    "%s p%d: trigger not in its own paragraph" % (o["order_id"], d["paragraph"])
                assert d["trigger_event"] in text.split("Deadlines Ordered")[0], \
                    "%s p%d: trigger not on the events table" % (o["order_id"], d["paragraph"])
                if d["trigger_event_date"] is None:
                    assert "not recorded" in text, \
                        "%s: an undated event is not marked" % o["order_id"]
            if d["period_days"]:
                assert ("%d days" % d["period_days"]) in p["text"] or \
                       ("%d business days" % d["period_days"]) in p["text"], \
                    "%s p%d: period not stated" % (o["order_id"], d["paragraph"])
            if d["stated_date"]:
                assert human(d["stated_date"]) in p["text"], \
                    "%s p%d: stated date not written out" % (o["order_id"], d["paragraph"])
            if d["party_calculated_date"]:
                assert human(d["party_calculated_date"]) in p["text"], \
                    "%s p%d: parenthetical not written out" % (o["order_id"], d["paragraph"])
            want = CR.due_date(d["basis"], d["period_days"], g["order_date"],
                               d["trigger_event_date"], d["stated_date"])
            assert d["due_date"] == want, \
                "%s p%d: gold due_date %r disagrees with its own rulebook computation (%r)" \
                % (o["order_id"], d["paragraph"], d["due_date"], want)
            basis, business = EXPECTED[d["bucket"]]
            if basis:
                assert d["basis"] == basis, \
                    "%s p%d: bucket %s produced basis %r" % (o["order_id"], d["paragraph"],
                                                             d["bucket"], d["basis"])
            if d["bucket"] == "explicit_plain":
                assert CR.is_business_day(CR.parse(d["due_date"])), \
                    "%s p%d: explicit_plain landed off a business day" % (o["order_id"],
                                                                         d["paragraph"])
            if d["bucket"] == "explicit_nonbusiness":
                assert not CR.is_business_day(CR.parse(d["due_date"])), \
                    "%s p%d: explicit_nonbusiness landed ON a business day" % (o["order_id"],
                                                                              d["paragraph"])
            if d["bucket"] in ("cal_order_roll", "cal_event_roll"):
                assert d["rolled"], "%s p%d: a roll bucket did not roll" % (o["order_id"],
                                                                           d["paragraph"])
            if d["bucket"] in ("cal_order_plain", "cal_event_plain"):
                assert not d["rolled"], "%s p%d: a plain bucket rolled" % (o["order_id"],
                                                                          d["paragraph"])
            if d["bucket"] == "undatable":
                assert d["due_date"] is None and d["undatable"], \
                    "%s p%d: undatable bucket produced a date" % (o["order_id"], d["paragraph"])
        for n in g["non_deadline_paragraphs"]:
            assert n in paras, "%s: noise paragraph %d not cut" % (o["order_id"], n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_ORDERS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    orders = build_all(rng, n_orders=args.n)
    _verify(orders)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for o in orders:
        with open(os.path.join(CORPUS, "%s.txt" % o["order_id"]), "w", encoding="utf-8") as fh:
            fh.write(o["text"])
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for o in orders:
            fh.write(json.dumps(_gold(o)) + "\n")

    every = [ob for o in orders for ob in o["obligations"]]
    counts = {}
    for ob in every:
        counts[ob["bucket"]] = counts.get(ob["bucket"], 0) + 1
    total_bytes = sum(len(o["text"].encode("utf-8")) for o in orders)
    n_noise = sum(len(o["noise"]) for o in orders)
    n_struck = sum(1 for o in orders for nz in o["noise"] if nz["struck"])
    n_party = sum(1 for ob in every if ob["party_calculated_date"])
    n_party_wrong = sum(1 for ob in every
                        if ob["party_calculated_date"] and
                        ob["party_calculated_date"] != ob["due_date"])
    n_rolled = sum(1 for ob in every if ob["rolled"])
    n_undat = sum(1 for ob in every if ob["undatable"])
    n_two_day_roll = 0
    for ob in every:
        if ob["rolled"]:
            r = CR.compute(ob["basis"], ob["period_days"], ob["order_date"],
                           ob["trigger_event_date"], ob["stated_date"])
            if (CR.parse(r["due_date"]) - CR.parse(r["rolled_from"])).days > 2:
                n_two_day_roll += 1
    desk_wrong = sum(1 for ob in every
                     if desk_calendar_date(ob["basis"], ob["period_days"], ob["order_date"],
                                           ob["trigger_event_date"], ob["stated_date"],
                                           ob["party_calculated_date"]) != ob["due_date"])

    print("orders: %d   obligations: %d   bytes: %d" % (len(orders), len(every), total_bytes))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k, _c in BUCKETS))
    print("%d non-deadline paragraph(s), of which %d are deadline-SHAPED and set no date"
          % (n_noise, n_struck))
    print("%d obligation(s) carry a party's own calculated date; %d of those are WRONG"
          % (n_party, n_party_wrong))
    print("%d obligation(s) roll forward off a weekend or a court holiday, %d of them by more "
          "than one day" % (n_rolled, n_two_day_roll))
    print("%d obligation(s) cannot be dated from the four corners of the Order" % n_undat)
    print("%d of %d obligation(s) are dated WRONG by the desk-calendar floor" % (desk_wrong,
                                                                                len(every)))
    print("internal consistency check: PASSED (every gold value is stated in its own paragraph, "
          "every due date is that obligation's own rulebook computation, every bucket produced "
          "the basis and the landing it was dealt)")


if __name__ == "__main__":
    main()
