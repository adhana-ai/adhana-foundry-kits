"""Assemble the register-reading prompt. One prompt per register, every condition block in it.

⚠︎ THE MODEL DOES NOT DECIDE ANYTHING HERE, AND THE PROMPT SAYS SO IN ITS FIRST LINE. It reports
what the register records; `src/rulebook.py::decide()` works out, in pure code, which obligations
need action and which cannot be determined. That is the shape of a monitor kit: the reading half is
a model's job and the deciding half is not, because a status that changes when the temperature does
is not a status anybody can put on a worklist.

So why send the rulebook at all? Because the FIELDS are only load-bearing if you know what they are
for. Three of them look like formalities and are not:

  1. `condition_state` OUTRANKS EVERY DATE ON THE BLOCK. A superseded or waived condition is still
     printed on the register and still carries a stale date that computes as overdue. Report the
     state as it stands; the code reads it before it reads any date.
  2. FOR AN ANNUAL REPORT, THE PERIOD IS THE ANSWER AND THE FILING DATE IS NOT. A report filed last
     month can be the report for a reporting year two years back, which leaves the year in between
     outstanding. `last_done` is recorded, is extracted, and never decides a report's status.
  3. `not_occurred` AND `not_recorded` ARE DIFFERENT FACTS. "The event has not happened" is a
     recorded fact and means nothing is due. "The register does not say" means nobody can tell.
     Merging them turns an unknown into a clearance, which on a monitoring queue is the failure
     that actually hurts.

⚑ ONE CALL PER REGISTER, NOT ONE PER CONDITION -- same reasoning as every sibling extraction kit
here, and it matters more on this shape: the conditions on one register share a register date and a
permit, and splitting them would pay for the fixed prefix once per row instead of once per site.

⚠︎ THE RULEBOOK IS ILLUSTRATIVE AND THE KIT WATCHES NOTHING. It reads one snapshot somebody else
assembled and proposes a worklist; it does not poll, subscribe, schedule, alert, escalate, file or
clear. The prompt says so, the UI says so and the kit's own pages say so.
"""
import json

from .rulebook import R

SYSTEM = (
    "You read a SITE PERMIT OBLIGATION REGISTER and report what it records. You return JSON and "
    "nothing else.\n"
    "\n"
    "YOU DO NOT DECIDE WHETHER ANYTHING IS OVERDUE, DUE SOON, OR CLEAR. A separate piece of code "
    "works that out from the values you report, against the rulebook shown below. Your job is to "
    "report the register faithfully, including the places where it records nothing.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the register does not state a field, return null for it. Do not infer it, do not carry "
    "a value across from another condition block, and do not use what you know about the world.\n"
    "2. RETURN ONE ENTRY PER CONDITION BLOCK, in the order the register prints them, including "
    "blocks that are superseded, waived, or plainly closed out. A register accretes; the rows "
    "nobody deleted are exactly the rows this reading is about.\n"
    "3. `condition_state` IS THE FIRST WORD OF THE 'Condition state' LINE AND NOTHING ELSE. A "
    "superseded or waived condition still carries dates, and those dates do not change the state. "
    "Report 'superseded' or 'waived' even where the rest of the block looks like ordinary work "
    "that is running late.\n"
    "4. `last_done` IS A DATE OR IT IS NULL. Where the line says the entry was logged with no date "
    "recorded, return null -- not today's date, not the amendment date further up the block, and "
    "not a date from another condition. Where the line says it does not apply to this condition, "
    "return null.\n"
    "5. FOR AN ANNUAL REPORT, `period_credited` IS THE REPORTING YEAR THE FILING WAS CREDITED TO, "
    "taken from the 'Period credited' line and never from the filing date above it. The two "
    "routinely disagree and the period is the one that counts.\n"
    "6. `trigger_state` DISTINGUISHES 'not_occurred' FROM 'not_recorded'. The first means the "
    "register says the event has NOT happened. The second means the register does not say either "
    "way. They are different answers.\n"
    "7. `register_flag` is the site's own self-assessment of the row. Copy it verbatim. It is "
    "frequently wrong and it is never evidence about anything.\n"
    "8. Copy identifiers verbatim. Write every date as YYYY-MM-DD, exactly as the register does.\n"
    "9. Use the exact allowed value for a field that lists them, and return every field named in "
    "the schema on every entry, even when the answer is null."
)


def rulebook_block(r=None):
    """The rulebook's operative table, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the intervals inside this module is a copy
    that drifts from the file the corpus generator and the scorer both read -- which would make the
    model's context and the gold labels disagree about the same rulebook, silently.

    ⚑ THE OPERATIVE TABLE ONLY, NOT THE WHOLE FILE. data/rulebook.json carries long explanatory
    notes for a human reader; sending them would pay for prose on every call to no measured end.
    What goes in the prompt is the intervals, the windows and the state meanings -- the part that
    tells the model why a field matters.
    """
    r = r or R
    t = r["obligation_types"]
    lines = ["HOW THE STATUS IS WORKED OUT AFTERWARDS (context for you; you do not compute it). "
             "This is an ILLUSTRATIVE rulebook shipped with this kit, not a real permit.", "",
             "OBLIGATION TYPES"]
    for name in sorted(t):
        spec = t[name]
        if spec["basis"] == "cycle":
            how = "due %d days after the last recorded date" % spec["interval_days"]
        elif spec["basis"] == "reporting_period":
            how = ("covers a %s; due %s of the year after the year it covers"
                   % (spec["period"], spec["deadline_month_day"]))
        else:
            how = "nothing is due until the trigger event occurs; then the stated due date governs"
        lines.append("  %-22s %s; action window %d days" % (name + ":", how, spec["window_days"]))
    lines += ["", "CONDITION STATES -- read before any date"]
    for name in ("active", "superseded", "waived"):
        lines.append("  %-14s %s" % (name + ":", r["condition_states"][name]))
    lines += ["", "TRIGGER STATES"]
    for name in ("occurred", "not_occurred", "not_recorded", "not_applicable"):
        lines.append("  %-16s %s" % (name + ":", r["trigger_states"][name]))
    lines += ["", "THE STATUS IS ONE OF: " + ", ".join(r["statuses"]),
              "`not_determinable` is a real answer. The register not carrying what the rule needs "
              "is a fact to report, not a gap to fill in."]
    return "\n".join(lines)


RULEBOOK_TEXT = rulebook_block()


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def schema_block(fields, ob_fields):
    top = field_schema(fields)
    rows = field_schema(ob_fields)
    return ("Extract these register-level fields:\n%s\n\n"
            "Then return `obligations`: a list with ONE ENTRY PER CONDITION BLOCK on the register, "
            "in the order printed, each entry carrying exactly these fields:\n%s" % (top, rows))


def build(doc_text, secs, fields, ob_fields, selector):
    names = [f["name"] for f in fields] + ["obligations"]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = schema_block(fields, ob_fields)
    user = ("%s\n\n"
            "%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the register does not state.\n\n"
            "PERMIT OBLIGATION REGISTER\n--------------------------\n%s\n"
            % (RULEBOOK_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "register sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields, ob_fields):
    """The reply into {top-level values} + [obligation dicts]. Fails closed to ({}, []).

    ⚠︎ A REPLY WITH NO `obligations` LIST IS NOT AN EMPTY REGISTER. It is a reply that did not
    answer, and the harness records it as a failed document rather than as a site with nothing due.
    Silently reading a missing list as "nothing needs action" is precisely the confident wrong
    clearance a monitoring kit must never produce.
    """
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}, None
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}, None
    if not isinstance(obj, dict):
        return {}, None
    top = {f["name"]: obj.get(f["name"]) for f in fields}
    raw_rows = obj.get("obligations")
    if not isinstance(raw_rows, list):
        return top, None
    rows = []
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        rows.append({f["name"]: r.get(f["name"]) for f in ob_fields})
    return top, rows
