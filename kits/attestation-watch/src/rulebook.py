"""THE ATTESTATION RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. The decision this kit makes
is an applicability gate, a determinability gate and three date comparisons -- so the cycle
lengths, the grace window, the coverage test and the roles that carry a requirement at all have to
be a thing a reader can open, read, disagree with and replace. `data/rulebook.json` is that file.
Everything below is the arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no real professional standard, no standard-setter's rule, no regulator's requirement
and no firm's own independence policy -- none was consulted. It is not a substitute for the
standard your firm is actually bound by or for a person qualified to read it. See
data/SOURCES.md, and the same sentence is printed on the kit's own UI where a reader actually
reads the answer.

⚑ THIS KIT WATCHES NOTHING. It reads ONE snapshot of a register that somebody else assembled and
proposes a worklist. It does not poll, subscribe, schedule, alert, escalate, chase, file, sign off
or clear. Nothing in it runs unattended and nothing in it writes anywhere.

⚑ FIVE GATES, IN THIS ORDER, AND THE ORDER IS THE WHOLE DIFFICULTY:

  1. IS THIS PERSON REQUIRED TO ATTEST AT ALL? A role recorded as vacated, a person recorded as
     having joined inside the new-joiner window, and a role the rulebook does not put a
     requirement on are all `not_required`. This gate is FIRST because chasing somebody who owes
     nothing is the error that gets a monitoring queue ignored -- and it is the error a queue that
     only asks "is there a form on file" makes on every single one of them.
  2. CAN THE REGISTER BE READ ON THIS PERSON? No cycle-opened date means no due date can be
     derived. A return on file whose covered period the register does not state means the coverage
     test cannot be run. Both are `not_determinable`, which is a FIRST-CLASS ANSWER and not a
     failure to produce one: on a monitoring queue a confident wrong "fine" is the failure that
     actually hurts, and the honest answer to an unreadable record is that it is unreadable.
  3. IS THERE A RETURN AT ALL? None on file, and the due date has passed -> `missing`.
  4. DOES THE REGISTER CONTRADICT ITSELF ABOUT THIS PERSON? Two returns that disagree, or a
     declared relationship the register records as disposed of BEFORE the return was filed ->
     `contradicted`. This gate sits ABOVE staleness deliberately: filing again fixes a stale
     attestation and does not fix a contradiction.
  5. WAS THE RETURN IN TIME AND ABOUT THE RIGHT WINDOW? Filed later than the due date plus the
     grace window, or covering a period that ends before the due date -> `stale`.

  Anything that survives all five is `satisfied`.

⚑ THE DUE DATE IS DERIVED, NEVER READ. No register in this corpus states it. It is
`cycle_opened_on + cycle_days[role]`, and `stale_after` is that plus the grace window. The kit
publishes the CODE's date; the model is asked for its own and that number is measured beside it
and decides nothing -- which is what makes it a clean measurement of date arithmetic rather than a
measurement of whether the model can copy a date off a page.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")

STATUSES = ("satisfied", "missing", "stale", "contradicted", "not_required", "not_determinable")

# The three statuses that put a person on somebody's list today. `satisfied` and `not_required`
# both mean nothing needs doing; `not_determinable` means the REGISTER needs opening rather than
# the PERSON needing chasing, and it is deliberately not on the worklist for that reason.
WORKLIST = ("missing", "stale", "contradicted")

ROSTER_EVENTS = ("none", "joined_mid_cycle", "role_vacated")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


RB = load()

ROLES_REQUIRING = tuple(RB["roles_requiring_attestation"])
ROLES_NOT_REQUIRING = tuple(RB["roles_not_requiring_attestation"])
ROLES = tuple(list(ROLES_REQUIRING) + list(ROLES_NOT_REQUIRING))
CYCLE_DAYS = dict(RB["cycle_days"])
GRACE_DAYS = int(RB["grace_days"])


def parse_date(v):
    """An ISO date, or None. None is a real answer here and is never folded into 'probably fine'.

    ⚠︎ IT REFUSES ANYTHING THAT IS NOT EXACTLY yyyy-mm-dd. A tolerant date parser on a kit whose
    whole decision is a date comparison is a parser that turns a misread value into a confident
    wrong answer -- so a value it cannot read becomes None, and None reaches gate 2 and comes back
    as `not_determinable`.
    """
    if v in (None, ""):
        return None
    s = str(v).strip()
    try:
        return datetime.date(*(int(p) for p in s.split("-")))
    except (ValueError, TypeError):
        return None


def iso(d):
    return None if d is None else d.isoformat()


def cycle_days(role):
    """How many days this role's cycle runs for, or None when the rulebook does not carry the role."""
    if role in (None, ""):
        return None
    return CYCLE_DAYS.get(str(role).strip())


def requires_attestation(role):
    return str(role).strip() in ROLES_REQUIRING if role not in (None, "") else False


def due_on(cycle_opened_on, role):
    """The derived due date. `cycle_opened_on + cycle_days[role]`, or None when either is unknown.

    ⚑ THIS IS THE ONE PIECE OF ARITHMETIC IN THE KIT AND IT IS SCORED ON ITS OWN. An obligation
    found but mis-dated is a different failure from one missed: the first sends somebody to the
    wrong week, the second sends nobody at all.
    """
    d = parse_date(cycle_opened_on)
    n = cycle_days(role)
    if d is None or n is None:
        return None
    return d + datetime.timedelta(days=int(n))


def stale_after(cycle_opened_on, role):
    """The last day a return can be filed and still count as in time."""
    d = due_on(cycle_opened_on, role)
    return None if d is None else d + datetime.timedelta(days=GRACE_DAYS)


def _norm(v):
    if v in (None, ""):
        return None
    return " ".join(str(v).strip().lower().split()).strip(".,;:") or None


def decide(person, as_at_date=None):
    """THE RULE, in one place, returning one of STATUSES with its reasoning.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    values. They cannot drift about what a status means.

    ⚠︎ IT PROPOSES A WORKLIST. IT NEVER CHASES, FILES, SIGNS OFF OR CLEARS ANYTHING. The return
    value is a recommendation with a reason attached and a named list of what it could not
    determine; a qualified person decides what to do about it.

    `person` is a flat dict of the extracted values -- exactly the shape evals/judge.py hands it
    from a model reply, so the rule cannot be given anything the reply did not carry.
    """
    out = {"status": None, "reason": None, "due_on": None, "stale_after": None,
           "not_determinable_because": None}

    role = person.get("role")
    role = str(role).strip() if role not in (None, "") else None
    event = person.get("roster_event")
    event = str(event).strip() if event not in (None, "") else None

    # Derived dates first, so a `not_required` row still publishes the date arithmetic it can.
    out["due_on"] = iso(due_on(person.get("cycle_opened_on"), role))
    out["stale_after"] = iso(stale_after(person.get("cycle_opened_on"), role))

    # ---- GATE 1. APPLICABILITY. -------------------------------------------------------------
    # ⚑ FIRST, AND THE POSITION IS THE POINT. Every false alarm this kit is built to avoid lives
    # here: a role somebody has already left, a person who joined last week, and a role the
    # rulebook never put a requirement on. All three have no return on file, and a queue that
    # equates "no form" with "gap" chases all three.
    if event == "role_vacated":
        out["status"] = "not_required"
        out["reason"] = ("The register records this role as vacated, so the attestation "
                         "requirement no longer applies to this person on this engagement.")
        return out
    if event == "joined_mid_cycle":
        out["status"] = "not_required"
        out["reason"] = ("The register records this person as having joined inside the "
                         "new-joiner window, so their first cycle has not opened yet and nothing "
                         "is owed.")
        return out
    if role is not None and role in ROLES_NOT_REQUIRING:
        out["status"] = "not_required"
        out["reason"] = ("%s carries no attestation requirement under the shipped rulebook, "
                         "however the register lists it." % role)
        return out

    # ---- GATE 2. DETERMINABILITY. -----------------------------------------------------------
    # ⚑ A FIRST-CLASS ANSWER, NOT A FAILURE TO PRODUCE ONE. On a monitoring queue the expensive
    # mistake is a confident wrong "fine", so a record the register cannot answer is reported as
    # unanswerable and routed to somebody who can open the file.
    if role is None or cycle_days(role) is None:
        out["status"] = "not_determinable"
        out["not_determinable_because"] = ("the register does not record a role for this person, "
                                           "or records one the shipped rulebook does not carry")
        out["reason"] = out["not_determinable_because"]
        return out
    if parse_date(person.get("cycle_opened_on")) is None:
        out["status"] = "not_determinable"
        out["not_determinable_because"] = ("the register does not record when this person's cycle "
                                           "opened, so no due date can be derived")
        out["reason"] = ("No cycle-opened date is recorded for this person, so the due date this "
                         "rule works from cannot be derived. This is not a clearance.")
        return out

    filed = parse_date(person.get("return_filed_on"))
    covers = parse_date(person.get("return_covers_to"))

    # ---- GATE 3. IS THERE A RETURN AT ALL? --------------------------------------------------
    if filed is None:
        if covers is not None:
            out["status"] = "not_determinable"
            out["not_determinable_because"] = ("the register records a covered period for this "
                                               "person with no filing date beside it")
            out["reason"] = out["not_determinable_because"]
            return out
        out["status"] = "missing"
        out["reason"] = ("No return is on file for this person and the due date (%s) has passed. "
                         "This is a gap, not a clearance." % out["due_on"])
        return out

    if covers is None:
        out["status"] = "not_determinable"
        out["not_determinable_because"] = ("a return is on file and the register does not state "
                                           "what period it covers")
        out["reason"] = ("A return was filed on %s and the register does not state the period it "
                         "covers, so the coverage test cannot be run. The person has attested; "
                         "what they attested to cannot be read off this register."
                         % iso(filed))
        return out

    # ---- GATE 4. DOES THE REGISTER CONTRADICT ITSELF? ---------------------------------------
    # ⚑ ABOVE STALENESS ON PURPOSE. Filing again fixes a stale attestation. Nothing about filing
    # again resolves two returns that disagree, or a register that records a relationship as gone
    # on a date before the person declared it.
    latest = _norm(person.get("declared_relationship"))
    earlier = _norm(person.get("earlier_declared_relationship"))
    if earlier is not None and earlier != latest:
        out["status"] = "contradicted"
        out["reason"] = ("Two returns from the same person disagree: the earlier one declares "
                         "“%s” and the later one declares “%s”. The later "
                         "filing governs, and a disagreement between the two is not resolved by "
                         "filing a third."
                         % (person.get("earlier_declared_relationship"),
                            person.get("declared_relationship")))
        return out

    disposed = parse_date(person.get("relationship_disposed_on"))
    if latest is not None and disposed is not None and disposed < filed:
        out["status"] = "contradicted"
        out["reason"] = ("The return filed on %s declares “%s”, and the register records "
                         "that relationship as disposed of on %s — before the return was "
                         "filed. The register contradicts itself about this person."
                         % (iso(filed), person.get("declared_relationship"), iso(disposed)))
        return out

    # ---- GATE 5. IN TIME, AND ABOUT THE RIGHT WINDOW? ---------------------------------------
    due = due_on(person.get("cycle_opened_on"), role)
    limit = stale_after(person.get("cycle_opened_on"), role)
    if filed > limit:
        out["status"] = "stale"
        out["reason"] = ("The return was filed on %s. It was due on %s and the rulebook allows %d "
                         "days of grace, so anything filed after %s is late. The person did "
                         "attest, and not when they were required to."
                         % (iso(filed), iso(due), GRACE_DAYS, iso(limit)))
        return out
    if covers < due:
        out["status"] = "stale"
        out["reason"] = ("The return was filed in time, on %s, and covers a period ending %s — "
                         "before the due date of %s. It attests to the previous window, not this "
                         "one." % (iso(filed), iso(covers), iso(due)))
        return out

    out["status"] = "satisfied"
    out["reason"] = ("Filed %s, in time against a due date of %s with %d days of grace, covering a "
                     "period ending %s, and nothing on the register contradicts it."
                     % (iso(filed), iso(due), GRACE_DAYS, iso(covers)))
    return out


def status_of(person, as_at_date=None):
    """Just the status string, or None when the values are outside the rulebook's vocabulary."""
    s = decide(person, as_at_date)["status"]
    return s if s in STATUSES else None
