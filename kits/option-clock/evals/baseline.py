"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ THIS IS THE SHORTCUT A RIGHTS DESK ACTUALLY TAKES, NOT A CRIPPLED VERSION OF THE REAL THING.
It reads the register's own STATUS COLUMN and escalates on a worried-sounding clerk note. That is
what a spreadsheet with a status column and a comments column gives you today, on any desk, for
free -- and it is precisely the shortcut this kit exists to measure against, because a status
column is a record of what somebody last typed and never of what the clock says.

⚑ AND NOTE THE TWO THINGS A STATUS COLUMN CANNOT DO AT ALL.

  1. IT HAS NO DUE DATE IN IT. The floor publishes `expiry_date` as null on every register, because
     there is nowhere on the page to read one from -- an expiry is a COUNT, not a field. Every
     "when" question this kit answers is structurally unavailable to the floor, and it scores 0 on
     the date grader for that reason and not because its regexes are weak.
  2. IT HAS TWO VALUES AND THE ANSWER HAS FOUR. `live` and `lapsed` cannot express "lapsing inside
     the window" and cannot express "the paperwork does not settle it". Those are 19 of this
     corpus's 50 registers, and no amount of reading a status column produces either.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes the as-of date, the grant date, the clock basis, the trigger, the term and
the extension length out of the register; calling src.rulebook.decide() on them would score very
highly and tell you nothing about the model. So the floor is deliberately the SHORTCUT, not the
count, and the gap it opens is the gap between reading a status column and doing the arithmetic.

⚑ WHERE ITS ONE STRUCTURED SHORTCUT LIVES: `extensions_perfected`. The floor believes the file --
it sets perfected equal to the number the register RECORDS as exercised, which is exactly what a
desk does when it reads "recorded: exercised" and moves on. That is a scored field error on the
registers where the act behind the entry never happened, and it is the single reading this kit is
built around.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a relaxed note, mis-registering four records for days before it was
caught. Every phrase here is multi-word or a stem that appears in one register only, and
evals/check_labels.py asserts that property before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own published status exactly as it is run over the count, so a column-derived status
produces a column-derived escalation flag. That is worth publishing rather than hiding -- a
business-condition guardrail is only ever as good as the answer it reads.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any CALM note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("looks", "file", "review") appears in BOTH
# registers on this corpus and would misfire either way.
WORRIED_KEYWORDS = ("looks tight", "not confident", "something is off", "escalated internally",
                    "flagged for review", "second pair of eyes", "chased the file",
                    "nobody has come back")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _first_int(raw):
    if raw is None:
        return None
    m = re.search(r"(\d+)\s*months", raw)
    return int(m.group(1)) if m else None


def _title(raw):
    if raw is None:
        return None
    m = re.match(r'"(.*?)"', raw)
    return m.group(1) if m else raw


def _granted(raw):
    """The grant date -- or None where two entries disagree about it.

    ⚑ THE FLOOR GETS THIS ONE RIGHT, AND IT SHOULD. Spotting that a section carries two dated
    entries is a regex, not a judgement. What the floor cannot do is anything with the fact.
    """
    if raw is None:
        return None
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", raw)
    if len(set(dates)) != 1:
        return None
    return dates[0]


def _trigger(basis_raw, trig_raw):
    if (basis_raw or "").startswith("grant_date"):
        return "not_applicable", None
    if trig_raw and "occurred: not yet" in trig_raw:
        return "not_occurred", None
    m = re.search(r"occurred:\s*(\d{4}-\d{2}-\d{2})", trig_raw or "")
    if m:
        return "occurred", m.group(1)
    return "not_applicable", None


def _extensions(text):
    """(recorded_taken, months_each). The floor's ONE structured shortcut is downstream of this:
    it believes every recorded exercise, and never asks whether the act behind it happened."""
    blocks = re.findall(r"Extension \w+\n-+\n(.*?)(?:\n\n|\Z)", text, re.S)
    recorded = sum(1 for b in blocks if "recorded: exercised" in b)
    months = None
    for b in blocks:
        m = re.search(r"(\d+) months, perfected by", b)
        if m:
            months = int(m.group(1))
            break
    return recorded, months


def extract_one(text, fields):
    register_id = _section(text, "Register")
    property_title = _title(_section(text, "Property"))
    rights_holder = _section(text, "Rights Holder")
    grantee = _section(text, "Grantee")
    register_as_of = _section(text, "Register As Of")
    option_granted_date = _granted(_section(text, "Option Granted"))
    basis_raw = _section(text, "Clock Basis")
    clock_basis = "grant_date" if (basis_raw or "").startswith("grant_date") else "triggering_event"
    trigger_status, trigger_date = _trigger(basis_raw, _section(text, "Triggering Event"))
    initial_term_months = _first_int(_section(text, "Initial Option Period"))
    recorded, months_each = _extensions(text)
    register_status = _section(text, "Register Status")
    clerk_note = _section(text, "Clerk Note")

    # THE SHORTCUT, IN TWO LINES. The status column, escalated by the note's tone -- and no count
    # anywhere, so no expiry date at all.
    low = (clerk_note or "").lower()
    worried = any(k in low for k in WORRIED_KEYWORDS)
    status = "lapsed" if (worried or register_status == "lapsed") else "live"
    expiry_date = None

    values = {
        "register_id": register_id, "property_title": property_title,
        "rights_holder": rights_holder, "grantee": grantee,
        "register_as_of": register_as_of, "option_granted_date": option_granted_date,
        "clock_basis": clock_basis, "trigger_status": trigger_status,
        "trigger_date": trigger_date, "initial_term_months": initial_term_months,
        "extension_months_each": months_each,
        "extensions_recorded_taken": recorded,
        # ⚑ BELIEVING THE FILE. The desk reads "recorded: exercised" and moves on; so does this.
        "extensions_perfected": recorded,
        "register_status": register_status, "clerk_note": clerk_note,
        "expiry_date": expiry_date, "status": status,
    }
    out = {f["name"]: {"value": values.get(f["name"]),
                       "spannable": (f.get("spannable") is not False
                                     and f.get("type") != "enum"),
                       "span": None} for f in fields}
    return {"fields": out,
            "published_status": status, "published_expiry_date": expiry_date,
            "escalate_now": _compute(status, register_status),
            "counted_status": None, "counted_expiry_date": None,
            "counted_clock_start_date": None, "counted_days_to_expiry": None,
            "counted_reason": None, "undetermined_because": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
