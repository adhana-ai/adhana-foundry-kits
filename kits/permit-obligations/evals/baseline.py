"""A free, rules-and-regex reader. No model, no key, no spend -- scored by the same judge as a paid
run, so the two are directly comparable.

⚑ THE STATUS HERE IS A DELIBERATE SHORTCUT, WRITTEN TO FAIL THE PLANTED CONTRADICTION BY
CONSTRUCTION. The floor reads the SITE'S OWN `Register flag` and nothing else: `attention` means
overdue, `closed` means not_binding, `on track` means not_yet_due. That is exactly what the rulebook
forbids -- taking the compliance position from the party whose obligations are being checked,
instead of from the dates on the page. It is also, uncomfortably, what a great many real monitoring
spreadsheets actually do.

⚑ AND NOTE WHAT A FLAG READ CANNOT REACH AT ALL. `due_in_window` and `not_determinable` are the two
statuses that carry the actual work of a monitor -- "this falls due soon enough to arrange now" and
"nobody can tell from this record" -- and no amount of reading a three-valued flag produces either.
The floor is structurally incapable of them, which is the honest statement of what a self-assessment
can do: it can express concern, and it cannot express a DEADLINE. 68 of this corpus's 268
obligations have a status the floor cannot say.

⚑ IT CANNOT PRODUCE A DUE DATE EITHER, AND THAT IS THE POINT OF SCORING DATES SEPARATELY. A flag has
no arithmetic in it. The floor scores 0 of 172 on the derived-due-date grader while still getting a
sizeable share of the five-way statuses right, which is the clearest evidence on this page that
"which obligations need action" and "by when" are two different questions.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes every value the rulebook needs out of every condition block; calling
src.rulebook.decide() on them would score 100 pct and tell you nothing about the model. So the floor
is deliberately the SHORTCUT, not the lookup, and the gap it opens is the gap between believing a
register's own flag and running the rulebook over its dates.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::escalate_from() is run
over the floor's own statuses exactly as it is run over a model's, so a flag-derived status produces
a flag-derived escalation: the floor reads every register flag correctly by regex every time, and
the guardrail still collapses, because the condition it fires on is "overdue AND the flag is quiet"
and the floor has just defined overdue AS the flag. That is worth publishing rather than hiding -- a
business-condition guardrail is only ever as good as the field it reads.
"""
import re

from src import rulebook as RB
from src.extract import escalate_from

# The whole shortcut, in one dict. A three-valued self-assessment mapped onto three of the five
# statuses -- and it cannot reach the other two.
FLAG_STATUS = {
    "attention": "overdue",
    "closed": "not_binding",
    "on track": "not_yet_due",
}

_BLOCK = re.compile(r"^Condition (?P<cid>C-\d+\.\d+)\n-+\n(?P<body>.*?)(?=\n\nCondition |\Z)",
                    re.M | re.S)
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _section(text, name):
    m = re.search(r"^%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.M | re.S)
    return m.group(1).strip() if m else None


def _line(body, label):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(label), body, re.M)
    return m.group(1).strip() if m else None


def _date_or_none(raw):
    """A date line's date, or None where the line records that there is not one."""
    if raw is None:
        return None
    m = _DATE.match(raw)
    return m.group(1) if m else None


def _period(raw):
    """The four-digit reporting year on a 'Period credited' line, or None."""
    if raw is None:
        return None
    m = re.match(r"(\d{4})\s+reporting year", raw)
    return m.group(1) if m else None


def _trigger(raw):
    if raw is None:
        return None
    low = raw.lower()
    if low.startswith("occurred"):
        return "occurred"
    if low.startswith("not occurred"):
        return "not_occurred"
    if low.startswith("not recorded"):
        return "not_recorded"
    return "not_applicable"


def extract(text, fields, ob_fields):
    site = _section(text, "Site") or ""
    m = re.search(r"\((SITE-[A-Z]{2}-\d{4})\)", site)
    site_id = m.group(1) if m else None
    permit = _section(text, "Permit") or ""
    m = re.match(r"(MP-\d{4}-[A-Z])", permit)
    permit_no = m.group(1) if m else None
    register_date = _date_or_none(_section(text, "Register Date"))

    top = {"site_id": site_id, "permit_no": permit_no, "register_date": register_date}
    out_fields = {f["name"]: {"value": top.get(f["name"]), "spannable": f.get("type") != "enum",
                              "span": None} for f in fields}

    obligations = []
    for mb in _BLOCK.finditer(text):
        body = mb.group("body")
        state_line = _line(body, "Condition state") or ""
        values = {
            "condition_id": mb.group("cid"),
            "obligation_type": _line(body, "Obligation type"),
            "condition_state": state_line.split(" ")[0] or None,
            "last_done": _date_or_none(_line(body, "Last recorded as done")),
            "period_credited": _period(_line(body, "Period credited")),
            "stated_due": _date_or_none(_line(body, "Stated due date")),
            "trigger_state": _trigger(_line(body, "Trigger event")),
            "register_flag": _line(body, "Register flag"),
        }
        cells = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                             "span": None} for f in ob_fields}
        # ⚑ THE SHORTCUT, IN ONE LINE. Everything above this is a faithful read of the register;
        # this is the floor believing the site's own flag instead of the dates it just extracted.
        status = FLAG_STATUS.get(values["register_flag"])
        obligations.append({"condition_id": values["condition_id"], "cells": cells,
                            "values": values, "status": status, "reason": None,
                            "due_date": None, "days_to_due": None,
                            "undetermined_because": None})

    decided = [{"status": o["status"]} for o in obligations]
    return {
        "fields": out_fields,
        "obligations": obligations,
        "worklist": [o["condition_id"] for o in obligations if o["status"] in RB.ACTIONABLE],
        "escalate": escalate_from(decided, [o["values"] for o in obligations]),
        "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
        "parsed": True,
    }
