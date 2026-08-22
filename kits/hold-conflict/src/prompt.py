"""Assemble the extraction prompt. One prompt per records-disposition review, all twelve fields
in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `binding_hold_id` AND `disposition_eligible`, AND THE FIRST
DECIDES THE SECOND. Eligibility is a three-condition derivation with a priority order, and the
first condition is a PROSE JUDGEMENT: does any active hold's scope, written the way a hold notice
is written, actually cover this series?

⚠︎ WHAT THIS ASKS FOR IS A PROPOSAL, NOT AN ACTION. "Eligible" means "may be put in front of a
records officer for release", never "destroy it". The prompt says so, because a model that thinks
it is authorising a deletion answers a different, more anxious question than the one being asked.

Five things are spelled out that a model left to its own reading gets wrong:

  1. THE REVIEW DATE IS FIXED at 2026-08. "Has the retention elapsed" is unanswerable without one,
     and a model that reaches for its own idea of today answers a different question every time.
  2. SCOPE COVERAGE IS THREE TESTS, ALL OF WHICH MUST PASS -- category, project, date range. Two
     of three passing is the commonest wrong answer in this corpus and it looks like a match.
  3. A `released` HOLD DOES NOT FREEZE ANYTHING BY ITSELF. But an ACTIVE line that continues its
     scope by reference does, and its own scope text is the released hold's. Reading the released
     line and stopping is wrong; so is treating every released line as a successor case.
  4. AN OVERLAPPING SERIES OUTLIVES THE ITEM'S OWN SCHEDULE. A series past its own retention is
     still frozen if a longer-retention series that also captures it has not expired.
  5. THE OFFICER NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds concerned does not mean
     something is holding the series, and a note that sounds routine does not mean nothing is.

⚑ ONE CALL PER REVIEW, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.
"""
import json

AS_OF = "2026-08"

SYSTEM = (
    "You extract structured fields from a records-disposition review for one record series, and "
    "you decide whether that series may be PROPOSED for destruction. You return JSON and nothing "
    "else.\n"
    "\n"
    "You are not destroying, deleting or disposing of anything. A records officer reviews and "
    "releases; your answer is the proposal they review.\n"
    "\n"
    "THE REVIEW DATE IS " + AS_OF + ". Every 'has this elapsed yet' question below is asked "
    "against that date and against no other.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `binding_hold_id` is the id of the ONE hold in the Hold Registry that freezes this "
    "series, or null when none does. A hold freezes this series only when BOTH of these hold:\n"
    "   a. its status is `active`; and\n"
    "   b. its scope covers this series, which is THREE separate tests and ALL THREE must pass:\n"
    "      - CATEGORY: the record's Record Category is one of the categories the scope names.\n"
    "      - PROJECT: the scope names this record's Related Project, or names any project.\n"
    "      - DATES: the year in Record Closed falls inside the scope's stated span. 'YYYY "
    "onward' has no end. 'YYYY to YYYY' is inclusive at both ends.\n"
    "   Two of the three passing is NOT a match. If the scope is about a different category, a "
    "different project, or a span that does not contain the closed year, that hold does not "
    "freeze this series, however serious it sounds.\n"
    "3. A hold whose status is `released` NEVER freezes a series on its own -- not even when its "
    "scope covers it exactly. But a registry line whose scope reads 'continues the scope of "
    "<id>' takes its scope from that other hold: if that continuing line is `active` and the "
    "scope it inherits covers this series, IT is the binding hold and you return ITS id. Check "
    "every registry line before answering null.\n"
    "4. `disposition_eligible` is decided in this order, and the first condition that fires "
    "decides it:\n"
    "   a. If `binding_hold_id` is not null, the answer is 'no'.\n"
    "   b. Otherwise, if the Overlapping Series line states an expiry LATER than " + AS_OF + ", "
    "the answer is 'no' -- a longer-retention series that also captures this record still holds "
    "it, even though the series' own retention has run out. 'none on file' means there is no "
    "overlapping series and this condition does not fire.\n"
    "   c. Otherwise, if Retention Expires is LATER than " + AS_OF + ", the answer is 'no' -- the "
    "series' own retention period has not elapsed yet.\n"
    "   d. Otherwise the answer is 'yes'.\n"
    "5. THE OFFICER NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT ELIGIBILITY. A note that sounds "
    "concerned or mentions an escalation does NOT mean something is holding this series, and a "
    "note that sounds routine does NOT mean nothing is. The registry, the two expiry dates and "
    "the record's own metadata decide; the note is the records officer's own remark and may "
    "disagree with all of them.\n"
    "6. Copy values verbatim from the record wherever possible. Dates are 'YYYY-MM' exactly as "
    "written. `overlapping_expires` is null when the Overlapping Series line reads 'none on "
    "file' -- return null rather than a guess or an empty string.\n"
    "7. Use the exact allowed value for a field that lists them.\n"
    "8. Return every field named in the schema, even when the answer is null."
)


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the record does not state.\n\n"
            "RECORDS DISPOSITION REVIEW\n--------------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "review sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
