"""Two free, rules-and-regex extractors. No model, no key, no spend -- scored by the same judge as
a paid run, so all three are directly comparable.

    python -m evals.run --run-id b000-holds --baseline holds
    python -m evals.run --run-id b001-notes --baseline notes

⚑ WHY TWO FLOORS AND NOT ONE. The sibling kits in this series ship a single tone floor, because
tone was the only shortcut their corpus offered. This corpus offers two, and they fail in OPPOSITE
DIRECTIONS, which is the whole finding:

  `holds`  -- THE OVER-CAUTIOUS CLERK. Any hold on file at all means "not eligible". This is the
              real failure mode of a records programme: nothing is ever destroyed, retention
              schedules stop meaning anything, and the storage bill is the only thing that moves.
              It is right about every series a hold genuinely freezes and wrong about every series
              whose registry entry is about a different category, a different project or a
              different decade -- and it is BLIND to the two ways a series is frozen with no hold
              on file at all (a live overlapping series, and a retention that has not elapsed).

  `notes`  -- THE TONE READER. It classifies eligibility by how the records officer's own note
              reads: a note carrying one of a fixed list of concerned-sounding phrases means "not
              eligible", anything else means "eligible". That is precisely the shortcut the
              prompt's rules forbid -- deciding from prose instead of from the registry and the
              two expiry dates.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THE `holds` FLOOR PERFECT, AND THAT IS THE POINT OF NOT DOING IT.
The registry lines in THIS corpus are machine-written in a fixed four-column format, so a regex
could parse the scope prose back into its structured pieces and re-run the coverage test exactly.
It would score 100 pct here and tell you nothing, because a real hold registry is prose in a
case-management system with no fixed line format at all. The floor is deliberately the SHORTCUT,
not the rule, and the gap it opens is the gap between seeing a hold and reading one.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword
("flagging") that fired on a negation inside a breezy note ("nothing worth flagging"),
mis-registering four records for days before it was caught. evals/check_labels.py here asserts the
same register property this floor's own list must satisfy, before any run may spend.

⚠︎ AND NOTE WHAT BOTH FLOORS DO TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
each floor's own output exactly as it is run over a model's, so a wrong eligibility verdict
produces a wrong review flag. Both floors read queue_status correctly by regex every time and
still fail the flag, because a business-condition guardrail is only ever as good as the field it
reads -- which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any BREEZY note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("review", "flag") appears in BOTH registers
# on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("escalat", "second look", "not confident", "manual audit", "disputed",
                    "looked off", "hold conflict")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _first_line(s):
    return s.splitlines()[0].strip() if s else None


def _code(s):
    """'GS-30-01, 7 years' -> 'GS-30-01'. The schedule line states a code and a period; only the
    code is a field."""
    if not s:
        return None
    return s.split(",", 1)[0].strip()


def _overlap_expires(s):
    """The expiry on the Overlapping Series line, or None when it reads 'none on file'."""
    if not s or "none on file" in s:
        return None
    m = re.search(r"expires\s+(\d{4}-\d{2})", s)
    return m.group(1) if m else None


def _hold_ids(s):
    if not s or "none on file" in s:
        return []
    return re.findall(r"^([A-Z]{2}-\d{4}-\d{3})\s*\|", s, re.M)


def extract_one(text, fields, floor):
    series_id = _first_line(_section(text, "Record Series"))
    series_title = _first_line(_section(text, "Series Title"))
    record_category = _first_line(_section(text, "Record Category"))
    related_project = _first_line(_section(text, "Related Project"))
    record_closed = _first_line(_section(text, "Record Closed"))
    retention_code = _code(_first_line(_section(text, "Retention Schedule")))
    retention_expires = _first_line(_section(text, "Retention Expires"))
    overlapping_expires = _overlap_expires(_section(text, "Overlapping Series"))
    queue_status = _first_line(_section(text, "Disposition Queue"))
    officer_notes = _section(text, "Officer Notes")

    registry = _section(text, "Hold Registry")
    ids = _hold_ids(registry)

    if floor == "holds":
        # THE OVER-CAUTIOUS CLERK. A hold is on file, so nothing moves -- and the id it names is
        # simply the first line of the registry, whatever that line's status or scope says.
        binding = ids[0] if ids else None
        eligible = "no" if ids else "yes"
    elif floor == "notes":
        # THE TONE READER. It never looks at the registry at all, which is why binding_hold_id is
        # left null: a floor that decides from prose has no basis for naming a hold.
        low = (officer_notes or "").lower()
        binding = None
        eligible = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"
    else:
        raise ValueError("unknown baseline floor %r -- known: holds, notes" % floor)

    values = {
        "series_id": series_id, "series_title": series_title,
        "record_category": record_category, "related_project": related_project,
        "record_closed": record_closed, "retention_code": retention_code,
        "retention_expires": retention_expires, "overlapping_expires": overlapping_expires,
        "binding_hold_id": binding, "queue_status": queue_status,
        "officer_notes": officer_notes, "disposition_eligible": eligible,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values),
            "recomputed_disposition_eligible": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields, floor="holds"):
    return extract_one(text, fields, floor)
