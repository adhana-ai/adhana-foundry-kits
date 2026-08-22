#!/usr/bin/env python3
"""Generate synthetic engagement independence-attestation registers and their gold labels.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one register per file) and data/gold.jsonl, byte-identical on every run
from a fixed seed. Every engagement reference, person reference, role, relationship description and
administrator's note here is invented. Nothing is fetched and nothing is licensed from anybody, so
the corpus ships under this repo's MIT licence.

⚠︎ NO REAL PROFESSIONAL STANDARD, STANDARD-SETTER'S RULE, REGULATOR'S REQUIREMENT OR FIRM POLICY IS
REPRODUCED. The rulebook this corpus is built against is `data/rulebook.json`, which was written for
this kit and is illustrative rather than authoritative. No real firm, standard-setter, regulator,
standard number, client or person is named anywhere in this file. See data/SOURCES.md.

⚑ A MONITORING SNAPSHOT IS THE DOCUMENT. Each file is ONE engagement's register as it stood at one
moment: who is on the engagement and when their cycle opened, what has actually been filed and
when, what each return declared, and what the register elsewhere records about those relationships.
There is no stream, no schedule and no state. One call per register, one checkable gold.

⚑ GOLD `status` AND GOLD `due_on` ARE DERIVED, NOT LABELS SOMEBODY TYPED. Both come out of
src/rulebook.py -- the same module src/prompt.py states to the model in words and evals/judge.py
re-runs over the model's own reply. The register's administrator note never feeds either.

⚑ THE THIRTEEN BUCKETS, AND WHY EACH ONE EXISTS. Every bucket is a reading a careless monitor gets
wrong, and the three at the top are the ones that make a queue get ignored:

  not_required_vacated   -- the role was vacated. Nothing is owed. A queue that equates "no form on
                            file" with "gap" chases somebody who has left the engagement.
  not_required_joiner    -- joined inside the new-joiner window; the first cycle has not opened.
                            Same false alarm, different cause.
  not_required_role      -- a role the rulebook puts no requirement on at all. Third false alarm.
  satisfied_alarming     -- filed AFTER the due date but inside the grace window, declaring a live
                            relationship. Looks late and looks encumbered. Is fine.
  satisfied_disposed_after -- declares a relationship the register records as DISPOSED -- on a date
                            AFTER the return was filed. The return was correct on the day it was
                            filed, which is the only day a return can be correct about.
  contradicted_disposed  -- the same shape with the two dates the other way round. Disposed BEFORE
                            the return was filed: the register contradicts itself.
  contradicted_two_returns -- two returns from one person that disagree. Filing a third does not
                            resolve it.
  stale_filed_late       -- filed past the due date plus grace. The person did attest, and not when
                            they were required to.
  stale_wrong_period     -- filed in time, covering a period that ends BEFORE the due date. A real
                            return, on time, about the previous cycle.
  missing_no_return      -- nothing on file and the due date has passed.
  not_determinable_no_cycle  -- no cycle-opened date, so no due date can be derived.
  not_determinable_no_period -- a return on file whose covered period the register does not state.
  satisfied_clean        -- the ordinary case, so the graders have a majority class to be wrong
                            about.

⚑ THE TRAP THAT IS RECORDED IN THE WRONG PLACE. `not_required_joiner` and
`not_determinable_no_cycle` print the SAME LINE in the roster section -- "cycle opened -- not
recorded on this register". The only thing that separates a person who owes nothing from a record
nobody can read is a line in a DIFFERENT SECTION, Roster Changes. A reader who works down the
roster and never scrolls gets one of them wrong every time.

⚑ THE PLANTED AMBIGUITY: the administrator's note in `Register Notes` is written in the register
that contradicts what the register's own facts say, on N_CONTRADICTING_NOTE of the files. It is a
field to copy. It decides nothing, in gold or in the rule.
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
N_RECORDS = 50

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER ROW -- the fix a sibling kit in this
# series had to make after its first generator asked for 40 pct ambiguity and delivered 51. A count
# 1.7 standard deviations off its own design is not a corpus property, it is sampling noise being
# published as one. So every bucket here is a fixed COUNT over the whole corpus, shuffled by the
# seeded RNG and then dealt into registers.
BUCKETS = [
    ("satisfied_clean", 84),
    ("satisfied_alarming", 22),
    ("satisfied_disposed_after", 12),
    ("missing_no_return", 30),
    ("stale_filed_late", 24),
    ("stale_wrong_period", 20),
    ("contradicted_disposed", 16),
    ("contradicted_two_returns", 14),
    ("not_required_vacated", 14),
    ("not_required_joiner", 14),
    ("not_required_role", 12),
    ("not_determinable_no_cycle", 8),
    ("not_determinable_no_period", 10),
]

# Register sizes, an exact multiset summing to the total row count above across N_RECORDS files.
REGISTER_SIZES = [4] * 8 + [5] * 14 + [6] * 18 + [7] * 10      # 280 rows over 50 registers

N_CONTRADICTING_NOTE = 20                          # 40 pct, exactly

EXPECTED_STATUS = {
    "satisfied_clean": "satisfied",
    "satisfied_alarming": "satisfied",
    "satisfied_disposed_after": "satisfied",
    "missing_no_return": "missing",
    "stale_filed_late": "stale",
    "stale_wrong_period": "stale",
    "contradicted_disposed": "contradicted",
    "contradicted_two_returns": "contradicted",
    "not_required_vacated": "not_required",
    "not_required_joiner": "not_required",
    "not_required_role": "not_required",
    "not_determinable_no_cycle": "not_determinable",
    "not_determinable_no_period": "not_determinable",
}

REQUIRED_ROLES = list(RB.ROLES_REQUIRING)
ADMIN_ROLE = RB.ROLES_NOT_REQUIRING[0]

# Invented relationship descriptions. Generic, no real company, sector body, fund or person.
RELATIONSHIPS = [
    "equity holding in a listed distribution group",
    "family member employed by a supplier of the client",
    "a non-executive seat on an unrelated mutual board",
    "a personal loan from a lender the client also uses",
    "a consultancy engagement with a former group company",
    "shares held indirectly through a managed portfolio",
    "a spouse's employment with a competitor of the client",
    "a beneficial interest in a property let to a group subsidiary",
]
NO_INTERESTS = "no interests to report"

# Notes whose register says "nothing is outstanding on this engagement". Used truthfully on a
# register with an empty worklist, and against type on one with a full worklist.
CALM_NOTES = [
    "Register reviewed at the planning meeting; the team is satisfied nothing is outstanding.",
    "Routine cycle for this engagement. Returns looked complete to me when I filed them.",
    "No concerns raised by anyone on the team. Happy for this to go forward as it stands.",
    "Standard rollover, nothing unusual about this engagement's declarations at all.",
]
# Notes whose register says "something on this register needs looking at". Used truthfully on a
# register with a worklist, and against type on one that is entirely clean.
WORRIED_NOTES = [
    "Flagged this register for a second pass before sign-off; the paperwork looks uneven to me.",
    "Not confident the roster here is current -- asked for it to be checked again.",
    "Something looked off when I reconciled the returns against the roster this week.",
    "Declarations on this engagement are under manual review; treat the register as provisional.",
]

# Invented engagement-reference stems. Nothing here names a client, a sector or a place.
ENG_LETTERS = "ABCDEFGHJKLMNPRSTVWXY"


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


def _d(base, days):
    return base + datetime.timedelta(days=days)


def _iso(d):
    return None if d is None else d.isoformat()


# --------------------------------------------------------------------------------------------
# One constructor per bucket. Each returns a person dict of EXTRACTABLE values only -- the status
# and the due date are derived from them afterwards by src/rulebook.py, never set here. Each is
# ASSERTED against the rule at build time: a constructor that quietly stops producing its own
# bucket is exactly the defect an exact composition exists to prevent.
# --------------------------------------------------------------------------------------------

def _base(rng, as_at, min_offset=5, max_offset=120, role=None):
    """A role, a due date in the past and the cycle-opened date that produces it.

    ⚑ EVERY REQUIRED ATTESTER'S DUE DATE HAS ALREADY PASSED AT THE REGISTER'S AS-AT DATE, BY
    CONSTRUCTION. That is a real limit on this corpus and it is named rather than hidden: a
    "not due yet" case is a seventh status this kit does not carry, so the corpus does not
    contain one. See data/SOURCES.md and the kit page's `breaks_on`.
    """
    role = role or rng.choice(REQUIRED_ROLES)
    offset = rng.randint(min_offset, max_offset)
    due = _d(as_at, -offset)
    opened = _d(due, -RB.CYCLE_DAYS[role])
    return role, due, opened


def _mk_satisfied_clean(rng, as_at):
    role, due, opened = _base(rng, as_at)
    filed = _d(due, -rng.randint(0, 80))
    covers = _d(due, rng.randint(0, 60))
    if rng.random() < 0.68:
        rel, disposed = NO_INTERESTS, None
    else:
        rel, disposed = rng.choice(RELATIONSHIPS), None
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": rel, "earlier_declared_relationship": None,
            "relationship_disposed_on": _iso(disposed)}


def _mk_satisfied_alarming(rng, as_at):
    """Filed AFTER the due date, inside the grace window, declaring a live relationship. It looks
    late and it looks encumbered, and it is fine. This is the false alarm a monitoring queue makes
    when it compares a filing date against a due date and stops there."""
    role, due, opened = _base(rng, as_at, min_offset=RB.GRACE_DAYS + 6)
    filed = _d(due, rng.randint(1, RB.GRACE_DAYS))
    covers = _d(due, rng.randint(0, 60))
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": None}


def _mk_satisfied_disposed_after(rng, as_at):
    """Declares a relationship the register records as DISPOSED -- after the return was filed."""
    role, due, opened = _base(rng, as_at, min_offset=10)
    filed = _d(due, -rng.randint(1, 60))
    covers = _d(due, rng.randint(0, 60))
    latest_possible = min(as_at, _d(filed, 90))
    span = (latest_possible - filed).days
    disposed = _d(filed, rng.randint(1, max(1, span)))
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": _iso(disposed)}


def _mk_missing_no_return(rng, as_at):
    role, _due, opened = _base(rng, as_at)
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": None, "return_covers_to": None,
            "declared_relationship": None, "earlier_declared_relationship": None,
            "relationship_disposed_on": None}


def _mk_stale_filed_late(rng, as_at):
    role, due, opened = _base(rng, as_at, min_offset=RB.GRACE_DAYS + 11)
    span = (as_at - _d(due, RB.GRACE_DAYS)).days
    filed = _d(due, RB.GRACE_DAYS + rng.randint(1, max(1, span)))
    covers = _d(due, rng.randint(0, 60))
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": NO_INTERESTS if rng.random() < 0.7
                                     else rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": None}


def _mk_stale_wrong_period(rng, as_at):
    """Filed in time. Covers a period that ends BEFORE the due date -- the previous cycle."""
    role, due, opened = _base(rng, as_at)
    filed = _d(due, -rng.randint(0, 70))
    covers = _d(due, -rng.randint(1, 110))
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": NO_INTERESTS if rng.random() < 0.7
                                     else rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": None}


def _mk_contradicted_disposed(rng, as_at):
    """Declares a relationship the register records as disposed BEFORE the return was filed."""
    role, due, opened = _base(rng, as_at, min_offset=10)
    filed = _d(due, -rng.randint(0, 50))
    covers = _d(due, rng.randint(0, 60))
    earliest = max(opened, _d(filed, -90))
    span = (filed - earliest).days
    disposed = _d(filed, -rng.randint(1, max(1, span)))
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": _iso(disposed)}


def _mk_contradicted_two_returns(rng, as_at):
    """Two returns from one person that disagree about what was declared."""
    role, due, opened = _base(rng, as_at, min_offset=10)
    filed = _d(due, -rng.randint(0, 50))
    covers = _d(due, rng.randint(0, 60))
    earliest = max(opened, _d(filed, -120))
    span = (filed - earliest).days
    earlier_filed = _d(filed, -rng.randint(1, max(1, span)))
    a = rng.choice(RELATIONSHIPS + [NO_INTERESTS])
    b = rng.choice([r for r in RELATIONSHIPS + [NO_INTERESTS] if r != a])
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(filed), "return_covers_to": _iso(covers),
            "declared_relationship": a, "earlier_declared_relationship": b,
            "relationship_disposed_on": None,
            "_earlier_filed_on": _iso(earlier_filed),
            "_earlier_covers_to": _iso(_d(covers, -rng.randint(30, 200)))}


def _mk_not_required_vacated(rng, as_at):
    role, due, opened = _base(rng, as_at)
    row = {"role": role, "roster_event": "role_vacated", "cycle_opened_on": _iso(opened),
           "return_filed_on": None, "return_covers_to": None,
           "declared_relationship": None, "earlier_declared_relationship": None,
           "relationship_disposed_on": None,
           "_vacated_on": _iso(_d(as_at, -rng.randint(1, 90)))}
    if rng.random() < 0.5:                          # half of them did file before they left
        filed = _d(due, -rng.randint(0, 60))
        row["return_filed_on"] = _iso(filed)
        row["return_covers_to"] = _iso(_d(due, rng.randint(0, 60)))
        row["declared_relationship"] = NO_INTERESTS
    return row


def _mk_not_required_joiner(rng, as_at):
    """Joined inside the new-joiner window. The cycle line reads exactly the same as the record
    nobody can read -- only Roster Changes says which this is."""
    role = rng.choice(REQUIRED_ROLES)
    return {"role": role, "roster_event": "joined_mid_cycle", "cycle_opened_on": None,
            "return_filed_on": None, "return_covers_to": None,
            "declared_relationship": None, "earlier_declared_relationship": None,
            "relationship_disposed_on": None,
            "_joined_on": _iso(_d(as_at, -rng.randint(2, 25)))}


def _mk_not_required_role(rng, as_at):
    """A role the rulebook puts no requirement on. The register lists it with a cycle anyway,
    because registers are uniform and rulebooks are not."""
    _role, _due, opened = _base(rng, as_at, role=rng.choice(REQUIRED_ROLES))
    return {"role": ADMIN_ROLE, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": None, "return_covers_to": None,
            "declared_relationship": None, "earlier_declared_relationship": None,
            "relationship_disposed_on": None}


def _mk_not_determinable_no_cycle(rng, as_at):
    """No cycle-opened date. Same roster line as the mid-cycle joiner, and nothing in Roster
    Changes to explain it -- so no due date can be derived and nothing can be said."""
    role = rng.choice(REQUIRED_ROLES)
    filed = _d(as_at, -rng.randint(10, 200))
    return {"role": role, "roster_event": "none", "cycle_opened_on": None,
            "return_filed_on": _iso(filed),
            "return_covers_to": _iso(_d(filed, rng.randint(10, 120))),
            "declared_relationship": NO_INTERESTS, "earlier_declared_relationship": None,
            "relationship_disposed_on": None}


def _mk_not_determinable_no_period(rng, as_at):
    """A return is on file and the register does not state what period it covers."""
    role, due, opened = _base(rng, as_at)
    return {"role": role, "roster_event": "none", "cycle_opened_on": _iso(opened),
            "return_filed_on": _iso(_d(due, -rng.randint(0, 60))), "return_covers_to": None,
            "declared_relationship": NO_INTERESTS if rng.random() < 0.6
                                     else rng.choice(RELATIONSHIPS),
            "earlier_declared_relationship": None, "relationship_disposed_on": None}


MAKERS = {
    "satisfied_clean": _mk_satisfied_clean,
    "satisfied_alarming": _mk_satisfied_alarming,
    "satisfied_disposed_after": _mk_satisfied_disposed_after,
    "missing_no_return": _mk_missing_no_return,
    "stale_filed_late": _mk_stale_filed_late,
    "stale_wrong_period": _mk_stale_wrong_period,
    "contradicted_disposed": _mk_contradicted_disposed,
    "contradicted_two_returns": _mk_contradicted_two_returns,
    "not_required_vacated": _mk_not_required_vacated,
    "not_required_joiner": _mk_not_required_joiner,
    "not_required_role": _mk_not_required_role,
    "not_determinable_no_cycle": _mk_not_determinable_no_cycle,
    "not_determinable_no_period": _mk_not_determinable_no_period,
}

FIELD_ORDER = ("person_ref", "role", "roster_event", "cycle_opened_on", "return_filed_on",
               "return_covers_to", "declared_relationship", "earlier_declared_relationship",
               "relationship_disposed_on", "due_on", "status")

NO_CYCLE_LINE = "cycle opened -- not recorded on this register"


def render(reg):
    """One register, as text. Underlined headings, so src/segment.py can cut it."""
    lines = [_underline("Engagement"), reg["engagement_ref"], "",
             _underline("Register As At"), reg["as_at_date"], "",
             _underline("Cycle Rulebook"),
             "%s -- illustrative, shipped with this kit; reproduces no real professional standard"
             % reg["rulebook_id"], "",
             _underline("Attesters On Record")]
    for p in reg["attesters"]:
        cyc = ("cycle opened %s" % p["cycle_opened_on"]) if p["cycle_opened_on"] else NO_CYCLE_LINE
        lines.append("%-8s %-24s %s" % (p["person_ref"], p["role"], cyc))
    lines += ["", _underline("Returns Filed")]
    if not reg["_return_lines"]:
        lines.append("no returns on file for this register")
    else:
        lines.extend(reg["_return_lines"])
    lines += ["", _underline("Holdings And Relationships On File")]
    if not reg["_holding_lines"]:
        lines.append("no holdings or relationships recorded on this register")
    else:
        lines.extend(reg["_holding_lines"])
    lines += ["", _underline("Roster Changes")]
    if not reg["_roster_lines"]:
        lines.append("no roster changes recorded in this cycle")
    else:
        lines.extend(reg["_roster_lines"])
    lines += ["", _underline("Register Notes"), reg["register_note"], "",
              _underline("Prepared By"),
              "engagement administration, register assembled %s" % reg["as_at_date"], ""]
    return "\n".join(lines) + "\n"


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    sizes = list(REGISTER_SIZES)
    if n != N_RECORDS:                       # a --n other than the design keeps the shape, roughly
        sizes = sizes[:n] if n < len(sizes) else sizes + [5] * (n - len(sizes))
        total = sum(sizes)
        scale = total / float(sum(c for _b, c in BUCKETS))
        spec = [(name, max(1, round(count * scale))) for name, count in BUCKETS]
    rng.shuffle(sizes)
    total_rows = sum(sizes)
    buckets = _deal(rng, total_rows, spec)

    stats = {"statuses": {}, "buckets": {name: 0 for name, _ in BUCKETS},
             "contradicting_note": 0, "owner_review": 0, "worklist_rows": 0,
             "rows": total_rows, "two_returns": 0, "disposed_before": 0, "disposed_after": 0}

    out = []
    cursor = 0
    for i in range(1, len(sizes) + 1):
        size = sizes[i - 1]
        my_buckets = buckets[cursor:cursor + size]
        cursor += size

        as_at = datetime.date(2026, 2, 2) + datetime.timedelta(days=rng.randint(0, 144))
        engagement_ref = "ENG-%04d-%s%s" % (rng.randint(1000, 9999),
                                            rng.choice(ENG_LETTERS), rng.choice(ENG_LETTERS))
        reg_id = "ATT-%04d" % i

        refs = rng.sample(range(1000, 9999), size)
        people, return_rows, holding_lines, roster_lines = [], [], [], []
        for j, bucket in enumerate(my_buckets):
            p = MAKERS[bucket](rng, as_at)
            p["person_ref"] = "P-%04d" % refs[j]
            p["_bucket"] = bucket
            people.append(p)

        # ⚑ THE RETURNS SECTION IS SHUFFLED, NOT GROUPED BY PERSON AND NOT SORTED BY DATE. A
        # person with two returns has two lines that can sit anywhere in the section, so "which of
        # these is the LATER filing" is work rather than a reading order.
        for p in people:
            if p["return_filed_on"]:
                return_rows.append((p["person_ref"], p["return_filed_on"], p["return_covers_to"],
                                    p["declared_relationship"]))
            if p.get("_earlier_filed_on"):
                return_rows.append((p["person_ref"], p["_earlier_filed_on"],
                                    p["_earlier_covers_to"],
                                    p["earlier_declared_relationship"]))
            if p["declared_relationship"] and p["declared_relationship"] != NO_INTERESTS:
                if p["relationship_disposed_on"]:
                    holding_lines.append("%-8s %s -- disposed %s"
                                         % (p["person_ref"], p["declared_relationship"],
                                            p["relationship_disposed_on"]))
                else:
                    holding_lines.append("%-8s %s -- current, no disposal recorded"
                                         % (p["person_ref"], p["declared_relationship"]))
            if p["roster_event"] == "role_vacated":
                roster_lines.append("%-8s role vacated %s -- the requirement no longer applies"
                                    % (p["person_ref"], p["_vacated_on"]))
            elif p["roster_event"] == "joined_mid_cycle":
                roster_lines.append("%-8s joined the engagement %s -- inside the new-joiner "
                                    "window, the first cycle has not opened"
                                    % (p["person_ref"], p["_joined_on"]))
        rng.shuffle(return_rows)
        rng.shuffle(holding_lines)
        return_lines = ["%-8s filed %s   covering the period to %s   declared: %s"
                        % (ref, filed, covers or "-- not stated on the filed return", rel)
                        for ref, filed, covers, rel in return_rows]

        # Gold's status and due date are DERIVED here by the shipped rule, over the same values
        # the register states -- never typed, and never read off the administrator's note.
        clean_people = []
        for p in people:
            d = RB.decide(p)
            assert d["status"] == EXPECTED_STATUS[p["_bucket"]], \
                "%s / %s produced %r, not %r" % (reg_id, p["_bucket"], d["status"],
                                                 EXPECTED_STATUS[p["_bucket"]])
            row = {k: (d["due_on"] if k == "due_on"
                       else d["status"] if k == "status" else p.get(k)) for k in FIELD_ORDER}
            clean_people.append(row)
            stats["statuses"][row["status"]] = stats["statuses"].get(row["status"], 0) + 1
            stats["buckets"][p["_bucket"]] += 1
            if row["status"] in RB.WORKLIST:
                stats["worklist_rows"] += 1
            if p.get("_earlier_filed_on"):
                stats["two_returns"] += 1
            if p["relationship_disposed_on"] and p["return_filed_on"]:
                if p["relationship_disposed_on"] < p["return_filed_on"]:
                    stats["disposed_before"] += 1
                else:
                    stats["disposed_after"] += 1

        reg = {
            "register_id": reg_id,
            "engagement_ref": engagement_ref,
            "as_at_date": as_at.isoformat(),
            "rulebook_id": RB.RB["id"],
            "register_note": None,
            "contradicting_note": None,
            "attesters": clean_people,
            "needs_owner_review": None,
            "_return_lines": return_lines,
            "_holding_lines": holding_lines,
            "_roster_lines": roster_lines,
        }
        reg["needs_owner_review"] = owner_review([p["status"] for p in clean_people])
        out.append(reg)

    # ⚑ THE NOTE REGISTER IS DEALT LAST, ACROSS THE WHOLE CORPUS, so the count is exact rather
    # than sampled. `contradicting` means the note's register disagrees with the register's own
    # facts: a settled-sounding note over a worklist, or an alarmed one over an empty one.
    contradicting = _deal(rng, len(out),
                          [(True, min(N_CONTRADICTING_NOTE, len(out))),
                           (False, max(0, len(out) - N_CONTRADICTING_NOTE))])
    for reg, contra in zip(out, contradicting):
        dirty = any(p["status"] in RB.WORKLIST for p in reg["attesters"]) or reg["needs_owner_review"]
        calm = (not dirty) if not contra else dirty
        reg["register_note"] = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)
        reg["contradicting_note"] = bool(contra)
        if contra:
            stats["contradicting_note"] += 1
        if reg["needs_owner_review"]:
            stats["owner_review"] += 1
    return out, stats


def owner_review(statuses):
    """PURE CODE, the register-level business condition. See src/extract.py::compute()."""
    if not statuses or any(s is None for s in statuses):
        return None
    return any(s in ("contradicted", "not_determinable") for s in statuses)


def _verify(rows):
    """Every gold value must be stated in the register it labels, every gold status must be that
    register's own rule output, and every null must be explained in the text. A corpus whose labels
    are not readable off its own text is not a corpus, it is a second opinion."""
    for reg, text in rows:
        for field in ("engagement_ref", "as_at_date", "rulebook_id", "register_note"):
            assert reg[field] in text, "%s: %s not stated" % (reg["register_id"], field)
        for p in reg["attesters"]:
            assert p["person_ref"] in text, "%s: %s not listed" % (reg["register_id"],
                                                                   p["person_ref"])
            assert p["role"] in text, "%s: role not stated" % reg["register_id"]
            if p["cycle_opened_on"] is None:
                assert NO_CYCLE_LINE in text, \
                    "%s: an unrecorded cycle is not explained in the text" % reg["register_id"]
            else:
                assert p["cycle_opened_on"] in text, \
                    "%s/%s: cycle_opened_on not stated" % (reg["register_id"], p["person_ref"])
            if p["return_filed_on"] is not None:
                assert "filed %s" % p["return_filed_on"] in text, \
                    "%s/%s: filing date not stated verbatim" % (reg["register_id"],
                                                                p["person_ref"])
                if p["return_covers_to"] is None:
                    assert "-- not stated on the filed return" in text, \
                        "%s: an unstated covered period is not explained" % reg["register_id"]
                else:
                    assert "covering the period to %s" % p["return_covers_to"] in text, \
                        "%s/%s: covered period not stated" % (reg["register_id"], p["person_ref"])
            if p["relationship_disposed_on"] is not None:
                assert "disposed %s" % p["relationship_disposed_on"] in text, \
                    "%s/%s: disposal date not stated" % (reg["register_id"], p["person_ref"])
            if p["roster_event"] == "role_vacated":
                assert "role vacated" in text, "%s: vacancy not stated" % reg["register_id"]
            if p["roster_event"] == "joined_mid_cycle":
                assert "joined the engagement" in text, \
                    "%s: mid-cycle join not stated" % reg["register_id"]

            want = RB.decide(p)
            assert p["status"] == want["status"], \
                "%s/%s: gold status %r disagrees with its own rule output (%r)" \
                % (reg["register_id"], p["person_ref"], p["status"], want["status"])
            assert p["due_on"] == want["due_on"], \
                "%s/%s: gold due_on %r disagrees with the derivation (%r)" \
                % (reg["register_id"], p["person_ref"], p["due_on"], want["due_on"])
        assert reg["needs_owner_review"] == owner_review([p["status"] for p in reg["attesters"]]), \
            "%s: owner-review flag disagrees with its own statuses" % reg["register_id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    regs, stats = build_all(rng, n=args.n)
    rows = [(reg, render(reg)) for reg in regs]

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for reg, text in rows:
        with open(os.path.join(CORPUS, "%s.txt" % reg["register_id"]), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for reg, _text in rows:
            gold = {k: v for k, v in reg.items() if not k.startswith("_")}
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _r, t in rows)
    print("registers: %d   attester rows: %d   bytes: %d" % (len(rows), stats["rows"], total))
    print("statuses: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["statuses"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d of %d attester rows are on the worklist (missing, stale or contradicted)"
          % (stats["worklist_rows"], stats["rows"]))
    print("%d register(s) need an OWNER rather than a reminder -- the pure-code routing flag"
          % stats["owner_review"])
    print("%d row(s) carry two returns from the same person" % stats["two_returns"])
    print("%d row(s) declare a relationship the register records as disposed BEFORE the return "
          "was filed; %d record the disposal AFTER it -- same shape, opposite answer"
          % (stats["disposed_before"], stats["disposed_after"]))
    print("%d (%.0f%%) carry an administrator's note whose register contradicts the register's "
          "own facts" % (stats["contradicting_note"],
                         100.0 * stats["contradicting_note"] / len(rows)))
    print("internal consistency check: PASSED (every gold value is stated in its own register, "
          "every status and due date is that register's own rule output, every null is explained "
          "in the text)")


if __name__ == "__main__":
    main()
