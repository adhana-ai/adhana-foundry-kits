"""A free, rules-and-regex monitor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `status` HERE IS A DELIBERATE BOX-TICK FLOOR, WRITTEN TO FAIL THE APPLICABILITY GATE BY
CONSTRUCTION. It reads one thing and one thing only: IS THERE A LINE IN `Returns Filed` FOR THIS
PERSON. A line means `satisfied`; no line means `missing`. That is precisely the shortcut the
rulebook forbids -- deciding an attestation status by whether a form exists instead of by who owed
one, when it was due, what window it covered and whether the register contradicts itself.

⚑ IT IS ALSO THE SHORTCUT A REAL MONITORING QUEUE ACTUALLY TAKES. "Everybody who has not filed" is
one join, it runs in a second, and it is what a spreadsheet does. This floor is not a straw man; it
is the incumbent.

⚑ AND NOTE WHAT A BOX-TICK CANNOT REACH AT ALL. `stale`, `contradicted`, `not_required` and
`not_determinable` are FOUR of the six statuses, and no amount of asking "is there a form" produces
any of them. The floor is structurally incapable of them. It can say a form is absent; it cannot
say a form was late, that a register disagrees with itself, that nothing was owed, or that the
record cannot be read.

⚑ THE FALSE ALARMS ARE THE POINT. Every person the register lists who owed nothing -- a vacated
role, a mid-cycle joiner, a role the rulebook puts no requirement on -- has no return on file, so
this floor puts every single one of them on the worklist. That is the error that gets a monitoring
queue ignored, it is measured here rather than asserted, and it is why `false_alarm_rate_pct` is in
this kit's headline.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS FLOOR PERFECT, AND THAT IS THE POINT OF NOT DOING IT. It
already regexes every value the rulebook needs -- the judge measures exactly that, as
`rule_over_own_values_accuracy_pct` -- so one call to src/rulebook.py::decide() would score 100 pct
and tell you nothing about the model. The floor is deliberately the SHORTCUT, not the rule, and the
gap it opens is the gap between reading a register and deciding from it.

⚠︎ THE DUE DATES ARE NOT SHORTCUT. The floor derives `due_on` with the same arithmetic the kit
publishes, because arithmetic is the one thing code is simply good at. A floor that got the dates
wrong would flatter the model on the date-arithmetic grader for no reason.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute

NO_CYCLE_LINE = "cycle opened -- not recorded on this register"


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _lines(text, name):
    body = _section(text, name)
    if not body:
        return []
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def _roster(text):
    """[(person_ref, role, cycle_opened_on_or_None)] in the order the register lists them."""
    out = []
    for ln in _lines(text, "Attesters On Record"):
        m = re.match(r"^(P-\d+)\s+(\S+)\s+(.*)$", ln)
        if not m:
            continue
        ref, role, cyc = m.group(1), m.group(2), m.group(3).strip()
        d = None if cyc == NO_CYCLE_LINE else (cyc.split()[-1] if cyc.startswith("cycle opened")
                                               else None)
        out.append((ref, role, d))
    return out


def _returns(text):
    """{person_ref: [(filed, covers_or_None, declared)]}, every line, unsorted."""
    out = {}
    for ln in _lines(text, "Returns Filed"):
        m = re.match(r"^(P-\d+)\s+filed\s+(\S+)\s+covering the period to\s+(.*?)\s+declared:\s+(.*)$",
                     ln)
        if not m:
            continue
        covers = m.group(3).strip()
        covers = None if covers.startswith("--") else covers
        out.setdefault(m.group(1), []).append((m.group(2), covers, m.group(4).strip()))
    return out


def _holdings(text):
    """{person_ref: disposal_date_or_None} for the relationships the register carries."""
    out = {}
    for ln in _lines(text, "Holdings And Relationships On File"):
        m = re.match(r"^(P-\d+)\s+(.*?)\s+--\s+(.*)$", ln)
        if not m:
            continue
        tail = m.group(3).strip()
        d = tail.split()[-1] if tail.startswith("disposed") else None
        out[m.group(1)] = d
    return out


def _roster_events(text):
    out = {}
    for ln in _lines(text, "Roster Changes"):
        m = re.match(r"^(P-\d+)\s+(.*)$", ln)
        if not m:
            continue
        tail = m.group(2)
        if tail.startswith("role vacated"):
            out[m.group(1)] = "role_vacated"
        elif tail.startswith("joined the engagement"):
            out[m.group(1)] = "joined_mid_cycle"
    return out


def _cells(names_values, att_fields):
    return {f["name"]: {"value": names_values.get(f["name"]),
                        "spannable": f.get("type") not in ("enum", "derived"),
                        "span": None}
            for f in att_fields}


def extract(text, fields):
    reg_vals = {
        "engagement_ref": _section(text, "Engagement"),
        "as_at_date": _section(text, "Register As At"),
        "rulebook_id": (_section(text, "Cycle Rulebook") or "").split(" --")[0].strip() or None,
        "register_note": _section(text, "Register Notes"),
    }
    register = {f["name"]: {"value": reg_vals.get(f["name"]),
                            "spannable": f.get("type") not in ("enum", "derived"),
                            "span": None}
                for f in fields["register"]}

    rets = _returns(text)
    holds = _holdings(text)
    events = _roster_events(text)

    attesters = []
    for ref, role, cyc in _roster(text):
        lines = sorted(rets.get(ref) or [])            # ISO dates sort correctly as strings
        latest = lines[-1] if lines else None
        earlier = lines[-2] if len(lines) > 1 else None
        vals = {
            "person_ref": ref,
            "role": role,
            "roster_event": events.get(ref, "none"),
            "cycle_opened_on": cyc,
            "return_filed_on": latest[0] if latest else None,
            "return_covers_to": latest[1] if latest else None,
            "declared_relationship": latest[2] if latest else None,
            "earlier_declared_relationship": earlier[2] if earlier else None,
            "relationship_disposed_on": holds.get(ref),
            "due_on": RB.iso(RB.due_on(cyc, role)),
        }
        # ⚑ THE WHOLE SHORTCUT, IN ONE LINE. Is there a form on file?
        vals["status"] = "satisfied" if latest else "missing"
        attesters.append({
            "person_ref": ref,
            "fields": _cells(vals, fields["attester"]),
            # The floor PUBLISHES its shortcut, exactly as the model path publishes the rule. A
            # floor scored on a different quantity from the run it is compared against is not a
            # floor, it is a second kit.
            "computed_status": vals["status"],
            "computed_reason": ("A return is on file for this person."
                                if latest else "No return is on file for this person."),
            "computed_due_on": vals["due_on"],
            "computed_stale_after": RB.iso(RB.stale_after(cyc, role)),
            "not_determinable_because": None,
        })

    statuses = [a["computed_status"] for a in attesters]
    return {
        "register": register,
        "attesters": attesters,
        "worklist": [a["person_ref"] for a in attesters if a["computed_status"] in RB.WORKLIST],
        "not_determinable": [],
        # Run over the floor's own statuses, exactly as it is run over a model's -- so a box-tick
        # status produces a box-tick routing flag. A register-level guardrail is only ever as good
        # as the statuses it reads, and this floor can never produce either status it looks for.
        "needs_owner_review": _compute(statuses),
        "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
        "parsed": True,
    }
