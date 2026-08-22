#!/usr/bin/env python3
"""Generate synthetic currency-transaction filing QC packs and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one QC pack per file) and data/gold.jsonl, byte-identical on every run.
Every patron name, address, record number, identification reference and preparer note here is
invented; every property name is a constructed compound noun. Nothing is fetched and nothing is
licensed from anybody, so the corpus ships under this repo's MIT licence.

⚠︎ NO REAL REGULATION, FORM, FILING INSTRUCTION OR COMPLIANCE MANUAL IS REPRODUCED. The rulebook
this corpus is built against is `data/rulebook.json`, which was written for this kit. The threshold,
the aggregation window, the staleness horizon, the identification element list and the whole
transaction-code table are inventions. Amounts are in CU, an invented unit that is not a currency
and maps to none. No real casino, gaming operator, regulator, agency, form number or regulation is
named anywhere in this kit. See data/SOURCES.md.

⚑ GOLD `defects_found` IS A RULEBOOK PASS, NOT A LABEL SOMEBODY TYPED. It is derived from the same
structured values the generator itself decided, with the same rule the kit publishes everywhere
else -- src/rulebook.py::assess(), which src/prompt.py states to the model in words and
evals/judge.py re-runs over the model's own reply. It is never derived from the preparer's note,
and the note never feeds the label.

⚑ THE SIX SEEDED DEFECTS, AND WHY EACH IS ITS OWN BUCKET. Each is a reading a careless checker gets
wrong on its own:

  missed_aggregation       -- qualifying entries on the patron's own record, simply not on the draft.
  window_misapplied        -- the draft aggregated the CALENDAR day, so the 06:00 boundary moved
                              entries in and out wrongly. The total difference has a NAMED cause and
                              must not be reported as a missed aggregation as well.
  identification_gap       -- a required element absent from the draft, or identification captured
                              past the staleness horizon. It changes what the filing SAYS.
  identity_split           -- a second patron record in the log is the same person by both link
                              keys, and the draft aggregated only one of them.
  type_miscode             -- the draft codes an entry differently from the log. The swapped code
                              keeps the same direction and reportability, so the TOTAL is untouched
                              and the defect is purely a coding one.
  threshold_not_crossed    -- the qualifying total never crossed the threshold. No filing is due at
                              all, and the draft should not exist.

plus a seventh answer the gold can award, `insufficient_information`, for a pack carrying a
qualifying entry whose amount the log never captured -- and `none`, for a filing with nothing wrong
with it, which is the most important row in the set because it is the denominator of the
false-alarm rate.

⚑ THE CLEAN BUCKET IS THE HARD ONE, AND IT IS BUILT TO BE. Every clean pack carries at least one
piece of FALSE-ALARM BAIT -- a non-reportable wire or promotional credit sitting in the log, an
entry in the opposite direction, an entry just the wrong side of the 06:00 boundary, or a second
patron record that IS the same person and that the draft correctly did aggregate. All of them look
exactly like the thing a checker is hunting for and all of them are correctly absent from, or
correctly present in, the drafted total. A QC kit that flags these is worse than useless to the
person clearing the queue, and 18 of the 56 packs exist to measure how often it does.

⚑ THE PLANTED AMBIGUITY: the defect list is a rulebook pass, and the PREPARER'S OWN NOTE disagrees
with it on `N_AMBIGUOUS` packs. A defective filing carries a confident note ("Reviewed against the
log line by line; totals agree"); a clean one carries a note that reads as though something is
wrong. Anything that classifies off the note's TONE -- including evals/baseline.py, deliberately --
fails those packs by construction. Anything that runs the rulebook gets them right.
"""
import argparse
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 56

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51.
# A count 1.7 standard deviations off its own design is not a corpus property, it is sampling noise
# being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
#
# ⚑ AND `clean` IS THE BIGGEST BUCKET ON PURPOSE. It is the denominator of the false-alarm rate,
# which is the number this kit leads with, and a false-alarm rate over six rows is a number nobody
# should quote. 18 rows means one false alarm moves it 5.6 points and no further.
BUCKETS = [
    ("clean", 18),                    # nothing wrong with the filing -- and bait in every one
    ("missed_aggregation", 7),        # qualifying entries left off the draft
    ("identification_gap", 7),        # a missing element, or identification past the horizon
    ("window_misapplied", 6),         # the calendar day aggregated instead of the gaming day
    ("identity_split", 6),            # one person, two records, one of them aggregated
    ("type_miscode", 6),              # the draft's code is not the log's code
    ("threshold_not_crossed", 3),     # no filing was due at all
    ("insufficient_information", 3),  # an amount the log never captured
]
N_AMBIGUOUS = 22           # 39 pct, exactly -- a preparer note from the contradicting register
N_CLEAN_WITH_LINK = 4      # clean packs whose linked record the draft CORRECTLY aggregated
N_STALE_ID = 3             # of the identification_gap bucket, how many are stale rather than absent

# Invented properties. Constructed compound nouns; no real casino, resort or operator is named.
PROPERTIES = [
    ("Northgate Floor", "swing shift"),
    ("Harbour Level", "day shift"),
    ("Riverside Concourse", "graveyard shift"),
    ("Old Mill Floor", "swing shift"),
    ("Longview Terrace", "day shift"),
    ("Stonebridge Concourse", "graveyard shift"),
]
CAGES = ["cage 1", "cage 2", "cage 3", "cage 4"]

# Names are BUILT rather than drawn from a list of real ones: an initial plus a two-part constructed
# surname, so every patron in this corpus is mechanically invented and cannot coincide with a real
# person's record by anything but accident.
NAME_A = ["Ash", "Bram", "Cald", "Dray", "Ely", "Fen", "Gars", "Hal", "Kelm", "Lor",
          "Mard", "Nev", "Orm", "Pell", "Quen", "Rast", "Sel", "Thorn", "Vale", "Wend"]
NAME_B = ["combe", "ford", "wick", "stone", "mere", "dale", "worth", "ridge", "haven", "bourne"]
INITIALS = "ABCDEFGHJKLMNPRSTVW"
STREET_TYPE = ["Road", "Lane", "Street", "Way", "Rise"]
TOWNS = ["Milbrook", "Fairholt", "Westhaven", "Kingsmere", "Redditch Cross", "Northfold"]

# Notes whose TONE says "this filing is fine". Used truthfully on a clean pack, and against type on
# a defective one -- half the planted ambiguity.
CONFIDENT_NOTES = [
    "Reviewed against the log line by line; totals agree and the pack is ready to go.",
    "Straightforward one. Nothing on this pack needed anything extra.",
    "Checked the aggregation myself before handing it over. All in order.",
    "Routine filing for this patron. No issues at all with this pack.",
]

# Notes whose TONE says "something is wrong with this filing". Used truthfully on a defective pack,
# and against type on a clean one -- the other half.
ANXIOUS_NOTES = [
    "Not confident the totals tie out -- please re-add these before this goes anywhere.",
    "Something looked off to me on this one; flagged for a second review.",
    "Aggregation on this pack is disputed between the shift leads; under manual audit.",
    "Escalated to the compliance desk -- I would rather someone else checked this pack.",
]

IN_CODES = [c for c, v in RB.CODES.items() if v["direction"] == "in" and v["reportable"]]
OUT_CODES = [c for c, v in RB.CODES.items() if v["direction"] == "out" and v["reportable"]]
NONREPORTABLE = [c for c, v in RB.CODES.items() if not v["reportable"]]


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


def _date(d):
    return d.isoformat()


def _shift(d, days):
    return d + datetime.timedelta(days=days)


def _codes_for(direction, reportable=True):
    if reportable:
        return list(IN_CODES if direction == "cash_in" else OUT_CODES)
    want = "in" if direction == "cash_in" else "out"
    return [c for c in NONREPORTABLE if RB.CODES[c]["direction"] == want]


def _gaming_day_of(date_str, time_str, day):
    """Which gaming day does this timestamp fall in? The 06:00 rule, applied once, here.

    Every other reader of this corpus -- the model, the free floor, a forker -- has to re-derive
    this from the rulebook. The generator is the one place it is computed rather than read, which
    is why gold cannot disagree with the rulebook about where an entry belongs.
    """
    d = datetime.date(*(int(x) for x in date_str.split("-")))
    hh = int(time_str.split(":")[0])
    start = d if hh >= 6 else _shift(d, -1)
    return _date(start)


def _entry(rng, seq, record, direction, day, where="in", reportable=True, amount=None,
           code=None):
    """One cage log entry. `where` is in / before / after, relative to the gaming day."""
    if where == "in":
        if rng.random() < 0.75:
            date, time = _date(day), "%02d:%02d" % (rng.randint(6, 23), rng.randint(0, 59))
        else:
            date, time = _date(_shift(day, 1)), "%02d:%02d" % (rng.randint(0, 5), rng.randint(0, 59))
    elif where == "before":
        date, time = _date(day), "%02d:%02d" % (rng.randint(0, 5), rng.randint(0, 59))
    else:                                        # after -- the NEXT gaming day
        date, time = _date(_shift(day, 1)), "%02d:%02d" % (rng.randint(6, 22), rng.randint(0, 59))
    if code is None:
        code = rng.choice(_codes_for(direction, reportable))
    if amount is None:
        amount = rng.randrange(900, 5200, 50)
    return {"id": "TXN-%05d" % seq, "date": date, "time": time, "record": record,
            "code": code, "amount": amount,
            "gaming_day": _gaming_day_of(date, time, day)}


def _bait(rng, seq, record, direction, day):
    """One piece of FALSE-ALARM BAIT: an entry that looks like a missed aggregation and is not.

    Three shapes, and every one of them is CORRECTLY absent from the drafted total:
      - a non-reportable code (a wire, a promotional credit) -- not currency at all;
      - a reportable entry in the OPPOSITE direction -- a different filing's total;
      - a reportable entry in the right direction, on the wrong side of the 06:00 boundary.
    """
    kind = rng.choice(["nonreportable", "opposite", "outside"])
    if kind == "nonreportable":
        return _entry(rng, seq, record, direction, day, where="in", reportable=False), kind
    if kind == "opposite":
        other = "cash_out" if direction == "cash_in" else "cash_in"
        return _entry(rng, seq, record, other, day, where="in"), kind
    return _entry(rng, seq, record, direction, day,
                  where=rng.choice(["before", "after"])), kind


class Seq(object):
    """Transaction identifiers are unique per pack and ascending in the order the cage wrote them."""

    def __init__(self, rng):
        self.n = rng.randint(1000, 9000)

    def next(self):
        self.n += rng_step
        return self.n


rng_step = 3


def _qualifying(entries, direction, day):
    return [e for e in entries if RB.qualifies(e, direction, _date(day))]


def _patron(rng):
    name = "%s. %s%s" % (rng.choice(INITIALS), rng.choice(NAME_A), rng.choice(NAME_B))
    dob = _date(datetime.date(rng.randint(1955, 1995), rng.randint(1, 12), rng.randint(1, 28)))
    return {
        "name": name,
        "dob": dob,
        "address": "%d %s%s %s, %s" % (rng.randint(2, 240), rng.choice(NAME_A),
                                       rng.choice(NAME_B), rng.choice(STREET_TYPE),
                                       rng.choice(TOWNS)),
        "idref": "IDR-%06d" % rng.randint(100000, 999999),
        "account": "PA-%06d" % rng.randint(100000, 999999),
    }


def _record_id(rng):
    return "PR-%s%s%04d" % (rng.choice(INITIALS), rng.choice(INITIALS), rng.randint(1000, 9999))


# ---------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns a fully-decided pack, and every one is ASSERTED against
# the rulebook in build_all -- a constructor that quietly stops producing its own bucket is exactly
# the defect an exact composition exists to prevent.
# ---------------------------------------------------------------------------------------------

def _base(rng, day, direction, n_qualifying=None, min_total=None, max_total=None):
    """The qualifying spine of a pack: n entries on the patron's own record that all count."""
    seq = Seq(rng)
    record = _record_id(rng)
    for _ in range(4000):
        n = n_qualifying or rng.randint(3, 5)
        entries = [_entry(rng, seq.next(), record, direction, day, where="in") for _ in range(n)]
        total = sum(e["amount"] for e in entries)
        if min_total is not None and total <= min_total:
            continue
        if max_total is not None and total > max_total:
            continue
        return seq, record, entries
    raise RuntimeError("could not build a qualifying spine within the requested total band")


def _mk_clean(rng, day, direction, with_link):
    seq, record, entries = _base(rng, day, direction, min_total=RB.THRESHOLD)
    patron = _patron(rng)
    linked = None
    for _ in range(rng.randint(1, 3)):
        b, _kind = _bait(rng, seq.next(), record, direction, day)
        entries.append(b)
    if with_link:
        linked = _record_id(rng)
        for _ in range(rng.randint(1, 2)):
            entries.append(_entry(rng, seq.next(), linked, direction, day, where="in"))
    qual = _qualifying(entries, direction, day)
    return {"record": record, "patron": patron, "linked": linked, "entries": entries,
            "included": [e["id"] for e in qual], "draft_codes": {},
            "window": "gaming_day", "reported_total": sum(e["amount"] for e in qual),
            "drop_element": None, "stale": False}


def _mk_missed_aggregation(rng, day, direction):
    """⚑ THE DRAFTED TOTAL STAYS ABOVE THE THRESHOLD, AND THAT CONSTRAINT IS NOT COSMETIC. A draft
    whose own stated total is below the threshold raises a second question -- why was it prepared
    at all -- which is `threshold_not_crossed`'s question and not this bucket's. Leaving that
    ambiguity in would let a wrong answer here look like a reasonable reading, and this corpus
    seeds exactly one defect per pack so that it cannot."""
    for _ in range(4000):
        seq, record, entries = _base(rng, day, direction, n_qualifying=rng.randint(4, 5),
                                     min_total=RB.THRESHOLD)
        patron = _patron(rng)
        for _ in range(rng.randint(0, 2)):
            b, _kind = _bait(rng, seq.next(), record, direction, day)
            entries.append(b)
        qual = _qualifying(entries, direction, day)
        n_drop = rng.randint(1, 2)
        dropped = rng.sample(qual, n_drop)
        kept = [e for e in qual if e not in dropped]
        kept_total = sum(e["amount"] for e in kept)
        if kept_total <= RB.THRESHOLD:
            continue
        return {"record": record, "patron": patron, "linked": None, "entries": entries,
                "included": [e["id"] for e in kept], "draft_codes": {},
                "window": "gaming_day", "reported_total": kept_total,
                "drop_element": None, "stale": False}
    raise RuntimeError("missed_aggregation: exhausted")


def _mk_window_misapplied(rng, day, direction):
    """The draft aggregated the CALENDAR day. Entries either side of 06:00 move, and the total
    moves with them -- asserted here rather than hoped for."""
    for _ in range(4000):
        seq, record, entries = _base(rng, day, direction, n_qualifying=rng.randint(3, 4),
                                     min_total=RB.THRESHOLD)
        patron = _patron(rng)
        # One entry BEFORE 06:00 on the gaming day's own date -- belongs to the previous gaming
        # day, and a calendar-day aggregation wrongly counts it.
        entries.append(_entry(rng, seq.next(), record, direction, day, where="before"))
        # One entry after midnight the following morning -- belongs to THIS gaming day, and a
        # calendar-day aggregation wrongly drops it.
        if rng.random() < 0.6:
            e = _entry(rng, seq.next(), record, direction, day, where="in")
            e["date"] = _date(_shift(day, 1))
            e["time"] = "%02d:%02d" % (rng.randint(0, 5), rng.randint(0, 59))
            e["gaming_day"] = _gaming_day_of(e["date"], e["time"], day)
            entries.append(e)
        qual = _qualifying(entries, direction, day)
        calendar = [e for e in entries
                    if e["date"] == _date(day) and RB.reportable(e["code"])
                    and RB.direction_of(e["code"]) == ("in" if direction == "cash_in" else "out")]
        gaming_total = sum(e["amount"] for e in qual)
        calendar_total = sum(e["amount"] for e in calendar)
        # Both totals stay above the threshold, for the same reason missed_aggregation's does: a
        # drafted total below it would raise `threshold_not_crossed`'s question inside a pack that
        # is not about that, and this corpus seeds exactly one defect per pack.
        if gaming_total == calendar_total or min(gaming_total, calendar_total) <= RB.THRESHOLD:
            continue
        return {"record": record, "patron": patron, "linked": None, "entries": entries,
                "included": [e["id"] for e in calendar], "draft_codes": {},
                "window": "calendar_day", "reported_total": calendar_total,
                "drop_element": None, "stale": False}
    raise RuntimeError("window_misapplied: exhausted")


def _mk_identity_split(rng, day, direction):
    for _ in range(4000):
        seq, record, entries = _base(rng, day, direction, n_qualifying=rng.randint(3, 4),
                                     min_total=RB.THRESHOLD)
        patron = _patron(rng)
        linked = _record_id(rng)
        for _ in range(rng.randint(1, 2)):
            entries.append(_entry(rng, seq.next(), linked, direction, day, where="in"))
        if rng.random() < 0.5:
            b, _kind = _bait(rng, seq.next(), record, direction, day)
            entries.append(b)
        qual = _qualifying(entries, direction, day)
        own = [e for e in qual if e["record"] == record]
        own_total = sum(e["amount"] for e in own)
        if own_total <= RB.THRESHOLD:
            continue                    # the draft that was actually prepared must itself be due
        return {"record": record, "patron": patron, "linked": linked, "entries": entries,
                "included": [e["id"] for e in own], "draft_codes": {},
                "window": "gaming_day", "reported_total": own_total,
                "drop_element": None, "stale": False}
    raise RuntimeError("identity_split: exhausted")


def _mk_type_miscode(rng, day, direction):
    """The draft codes one included entry differently from the log. The swapped code keeps the same
    direction AND the same reportability, so the TOTAL is untouched -- this is purely a coding
    defect, and separating it from an arithmetic one is the whole reason the swap is constrained."""
    for _ in range(4000):
        seq, record, entries = _base(rng, day, direction, min_total=RB.THRESHOLD)
        patron = _patron(rng)
        if rng.random() < 0.6:
            b, _kind = _bait(rng, seq.next(), record, direction, day)
            entries.append(b)
        qual = _qualifying(entries, direction, day)
        target = rng.choice(qual)
        alternatives = [c for c in _codes_for(direction, True) if c != target["code"]]
        if not alternatives:
            continue
        return {"record": record, "patron": patron, "linked": None, "entries": entries,
                "included": [e["id"] for e in qual],
                "draft_codes": {target["id"]: rng.choice(alternatives)},
                "window": "gaming_day", "reported_total": sum(e["amount"] for e in qual),
                "drop_element": None, "stale": False}
    raise RuntimeError("type_miscode: exhausted")


def _mk_identification_gap(rng, day, direction, stale):
    seq, record, entries = _base(rng, day, direction, min_total=RB.THRESHOLD)
    patron = _patron(rng)
    if rng.random() < 0.6:
        b, _kind = _bait(rng, seq.next(), record, direction, day)
        entries.append(b)
    qual = _qualifying(entries, direction, day)
    drop = None if stale else rng.choice(RB.ID_ELEMENTS)
    return {"record": record, "patron": patron, "linked": None, "entries": entries,
            "included": [e["id"] for e in qual], "draft_codes": {},
            "window": "gaming_day", "reported_total": sum(e["amount"] for e in qual),
            "drop_element": drop, "stale": stale}


def _mk_threshold_not_crossed(rng, day, direction):
    """A draft that should not exist. The arithmetic on it is right; the filing is not due."""
    seq, record, entries = _base(rng, day, direction, n_qualifying=rng.randint(2, 3),
                                 max_total=RB.THRESHOLD)
    patron = _patron(rng)
    if rng.random() < 0.7:
        b, _kind = _bait(rng, seq.next(), record, direction, day)
        entries.append(b)
    qual = _qualifying(entries, direction, day)
    return {"record": record, "patron": patron, "linked": None, "entries": entries,
            "included": [e["id"] for e in qual], "draft_codes": {},
            "window": "gaming_day", "reported_total": sum(e["amount"] for e in qual),
            "drop_element": None, "stale": False}


def _mk_insufficient_information(rng, day, direction):
    """One qualifying entry's amount was never captured, so no total can be computed from the pack.

    ⚠︎ THE MISSING AMOUNT IS ON A QUALIFYING ENTRY, NEVER ON A PIECE OF BAIT. An uncaptured amount
    on a non-reportable wire changes nothing and would make this bucket a trick question rather
    than a real limit of the record.
    """
    for _ in range(4000):
        seq, record, entries = _base(rng, day, direction, n_qualifying=rng.randint(3, 4),
                                     min_total=RB.THRESHOLD)
        patron = _patron(rng)
        if rng.random() < 0.5:
            b, _kind = _bait(rng, seq.next(), record, direction, day)
            entries.append(b)
        qual = _qualifying(entries, direction, day)
        blank = rng.choice(qual)
        stated = sum(e["amount"] for e in qual if e["id"] != blank["id"])
        if stated <= RB.THRESHOLD:
            continue                    # same one-defect-per-pack constraint as the buckets above
        blank["amount"] = None
        break
    else:
        raise RuntimeError("insufficient_information: exhausted")
    return {"record": record, "patron": patron, "linked": None, "entries": entries,
            "included": [e["id"] for e in qual], "draft_codes": {},
            "window": "gaming_day", "reported_total": stated,
            "drop_element": None, "stale": False}


MAKERS = {
    "clean": _mk_clean,
    "missed_aggregation": _mk_missed_aggregation,
    "window_misapplied": _mk_window_misapplied,
    "identity_split": _mk_identity_split,
    "type_miscode": _mk_type_miscode,
    "identification_gap": _mk_identification_gap,
    "threshold_not_crossed": _mk_threshold_not_crossed,
    "insufficient_information": _mk_insufficient_information,
}

EXPECTED_DEFECTS = {
    "clean": [],
    "missed_aggregation": ["missed_aggregation"],
    "window_misapplied": ["window_misapplied"],
    "identity_split": ["identity_split"],
    "type_miscode": ["type_miscode"],
    "identification_gap": ["identification_gap"],
    "threshold_not_crossed": ["threshold_not_crossed"],
    "insufficient_information": ["insufficient_information"],
}


def render(case_id, pack, day, direction, prop, cage, shift, note):
    """The QC pack as the reader sees it: the draft first, then the log it was prepared from."""
    p = pack["patron"]
    lines = [_underline("Draft Filing"), pack["filing_id"], "",
             _underline("Property And Shift"), "%s, %s, %s" % (prop, shift, cage), "",
             _underline("Patron Record"), pack["record"], "",
             _underline("Gaming Day"), _date(day), "",
             _underline("Direction Reported"), direction, "",
             _underline("Window Applied"),
             ("gaming day (06:00 to 06:00 the next date)" if pack["window"] == "gaming_day"
              else "calendar day (00:00 to 24:00)"), "",
             _underline("Reported Total"), "%d CU" % pack["reported_total"], "",
             _underline("Transactions Included On The Draft")]
    by_id = {e["id"]: e for e in pack["entries"]}
    for tid in pack["included"]:
        e = by_id[tid]
        code = pack["draft_codes"].get(tid, e["code"])
        amount = "amount not captured" if e["amount"] is None else "%d CU" % e["amount"]
        lines.append("%s  %-26s %s" % (tid, code, amount))
    lines += ["", _underline("Patron Identification On The Draft")]
    block = [("full name", p["name"]), ("date of birth", p["dob"]),
             ("residential address", p["address"]),
             ("identification reference", p["idref"]),
             ("patron account number", p["account"])]
    for label, value in block:
        if label == pack["drop_element"]:
            continue
        lines.append("%s: %s" % (label, value))
    lines.append("identification captured on: %s" % pack["captured_on"])
    lines += ["", _underline("Cage Transaction Log")]
    for e in sorted(pack["entries"], key=lambda x: (x["date"], x["time"], x["id"])):
        amount = "amount not captured" if e["amount"] is None else "%d CU" % e["amount"]
        lines.append("%s  %s %s  %-12s %-26s %s"
                     % (e["id"], e["date"], e["time"], e["record"], e["code"], amount))
    lines += ["", _underline("Other Patron Records In This Log")]
    if pack["linked"]:
        lines.append("%s -- date of birth %s, identification reference %s"
                     % (pack["linked"], p["dob"], p["idref"]))
    else:
        lines.append("none -- every entry in this log is booked to the patron record above")
    lines += ["", _underline("Preparer Note"), note, ""]
    return "\n".join(lines) + "\n"


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:                       # a --n other than the design keeps the shape, roughly
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)
    ambiguity = _deal(rng, n, [(True, N_AMBIGUOUS), (False, n - N_AMBIGUOUS)])

    clean_link = _deal(rng, spec[0][1], [(True, N_CLEAN_WITH_LINK),
                                         (False, spec[0][1] - N_CLEAN_WITH_LINK)])
    n_idgap = dict(spec)["identification_gap"]
    id_stale = _deal(rng, n_idgap, [(True, N_STALE_ID), (False, n_idgap - N_STALE_ID)])

    clean_i = idgap_i = 0
    stats = {"defects": {}, "buckets": {name: 0 for name, _ in BUCKETS},
             "ambiguous": 0, "needs_recompute": 0, "bait_packs": 0, "clean_with_link": 0}

    out = []
    for i in range(1, n + 1):
        bucket = buckets[i - 1]
        day = datetime.date(2026, rng.randint(1, 6), rng.randint(1, 27))
        direction = rng.choice(["cash_in", "cash_out"])

        if bucket == "clean":
            pack = _mk_clean(rng, day, direction, clean_link[clean_i])
            if clean_link[clean_i]:
                stats["clean_with_link"] += 1
            clean_i += 1
        elif bucket == "identification_gap":
            pack = _mk_identification_gap(rng, day, direction, id_stale[idgap_i])
            idgap_i += 1
        else:
            pack = MAKERS[bucket](rng, day, direction)

        pack["filing_id"] = "DF-%d-%04d" % (day.year, rng.randint(1000, 9999))
        age = rng.randint(410, 900) if pack["stale"] else rng.randint(20, 380)
        pack["captured_on"] = _date(_shift(day, -age))

        qual = _qualifying(pack["entries"], direction, day)
        qual_total = RB.qualifying_total(pack["entries"], direction, _date(day))
        missing = pack["drop_element"] or None
        miscoded = ", ".join(sorted(pack["draft_codes"])) or None
        linked_included = ("not_applicable" if not pack["linked"]
                           else ("yes" if all(e["id"] in pack["included"] for e in qual
                                              if e["record"] == pack["linked"]) else "no"))

        d = RB.assess(pack["reported_total"], qual_total, pack["window"], pack["linked"],
                      linked_included, missing, pack["captured_on"], _date(day), miscoded)
        defects = sorted(d["defects"])
        assert defects == sorted(EXPECTED_DEFECTS[bucket]), \
            "%s produced %r, not %r" % (bucket, defects, EXPECTED_DEFECTS[bucket])

        ambiguous = ambiguity[i - 1]
        if ambiguous:
            stats["ambiguous"] += 1
        # Tone matches the defect list normally, and contradicts it when ambiguous.
        confident = (not defects) if not ambiguous else bool(defects)
        note = rng.choice(CONFIDENT_NOTES if confident else ANXIOUS_NOTES)

        prop, shift = rng.choice(PROPERTIES)
        cage = rng.choice(CAGES)
        case_id = "QCP-%04d" % i
        text = render(case_id, pack, day, direction, prop, cage, shift, note)

        gold = {
            "case_id": case_id,
            "filing_id": pack["filing_id"],
            "patron_record_id": pack["record"],
            "gaming_day": _date(day),
            "draft_direction": direction,
            "draft_reported_total": pack["reported_total"],
            "log_qualifying_total": qual_total,
            "draft_window_applied": pack["window"],
            "linked_record_id": pack["linked"],
            "draft_includes_linked_record": linked_included,
            "missing_identification_elements": missing,
            "identification_captured_on": pack["captured_on"],
            "miscoded_transaction_ids": miscoded,
            "preparer_note": note,
            "defects_found": ", ".join(defects) if defects else "none",
        }
        out.append((case_id, text, gold, bucket))

        key = ", ".join(defects) if defects else "none"
        stats["defects"][key] = stats["defects"].get(key, 0) + 1
        stats["buckets"][bucket] += 1
        if d["needs_recompute"]:
            stats["needs_recompute"] += 1
        if any(not RB.qualifies(e, direction, _date(day)) for e in pack["entries"]):
            stats["bait_packs"] += 1
    return out, stats


def _verify(rows):
    """Every gold value must be stated in (or derivable from) the pack it labels, and every gold
    defect list must be that pack's own rulebook pass. A corpus whose labels are not readable off
    its own text is not a corpus, it is a second opinion."""
    for case_id, text, gold, bucket in rows:
        for field in ("filing_id", "patron_record_id", "gaming_day", "draft_direction",
                      "identification_captured_on", "preparer_note"):
            assert str(gold[field]) in text, "%s: %s not stated in the pack" % (case_id, field)
        assert "%d CU" % gold["draft_reported_total"] in text, \
            "%s: reported total not stated verbatim" % case_id

        if gold["linked_record_id"] is None:
            assert "none -- every entry in this log is booked" in text, \
                "%s: the absence of a linked record is not stated" % case_id
        else:
            assert gold["linked_record_id"] in text, "%s: linked record not stated" % case_id

        if gold["log_qualifying_total"] is None:
            assert "amount not captured" in text, \
                "%s: an uncomputable total is not explained in the pack" % case_id
        else:
            assert "amount not captured" not in text, \
                "%s: an uncaptured amount on a pack whose total gold computes" % case_id

        if gold["missing_identification_elements"]:
            assert ("\n%s:" % gold["missing_identification_elements"]) not in text, \
                "%s: gold says an element is missing and the pack still prints it" % case_id
        else:
            for el in RB.ID_ELEMENTS:
                assert ("\n%s:" % el) in text, \
                    "%s: required element %r is absent and gold does not say so" % (case_id, el)

        if gold["miscoded_transaction_ids"]:
            for tid in gold["miscoded_transaction_ids"].split(", "):
                assert text.count(tid) >= 2, \
                    "%s: a miscoded id must appear on the draft AND in the log" % case_id

        want = RB.assess(gold["draft_reported_total"], gold["log_qualifying_total"],
                         gold["draft_window_applied"], gold["linked_record_id"],
                         gold["draft_includes_linked_record"],
                         gold["missing_identification_elements"],
                         gold["identification_captured_on"], gold["gaming_day"],
                         gold["miscoded_transaction_ids"])
        got = ", ".join(sorted(want["defects"])) or "none"
        assert gold["defects_found"] == got, \
            "%s: gold defect list %r disagrees with its own rulebook pass (%r)" \
            % (case_id, gold["defects_found"], got)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for case_id, text, _gold, _bucket in rows:
        with open(os.path.join(CORPUS, "%s.txt" % case_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _case_id, _text, gold, _bucket in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _b in rows)
    n_clean = sum(1 for _i, _t, g, _b in rows if g["defects_found"] == "none")
    print("packs: %d   bytes: %d" % (len(rows), total))
    print("defects: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["defects"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d pack(s) are CLEAN -- the denominator of the false-alarm rate" % n_clean)
    print("%d pack(s) carry at least one piece of false-alarm bait (a non-reportable entry, an "
          "opposite-direction entry, or one the wrong side of 06:00)" % stats["bait_packs"])
    print("%d clean pack(s) carry a linked record the draft CORRECTLY aggregated" %
          stats["clean_with_link"])
    print("%d (%.0f%%) carry a preparer note whose TONE contradicts the rulebook's answer"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d pack(s) need the totals recomputed before anyone submits -- the pure-code flag"
          % stats["needs_recompute"])
    print("internal consistency check: PASSED (every gold value is stated in its own pack, every "
          "defect list is that pack's own rulebook pass)")


if __name__ == "__main__":
    main()
