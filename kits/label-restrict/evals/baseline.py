"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `verdict` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the agronomist's note and nothing else: a note carrying one of a fixed list
of concerned-sounding phrases means `outside_label`, and anything else means `within_label`. That
is precisely the shortcut the prompt's rules forbid -- deciding a label question from prose instead
of from the label.

⚑ AND NOTE WHAT A TONE READ CANNOT REACH AT ALL. `wait_required` and `insufficient_information`
are the two verdicts that carry the actual work of a label check -- "this application may be fine
in nine days" and "nobody can say from this page" -- and no amount of reading a note produces
either. The floor is structurally incapable of them, which is the honest statement of what tone can
do: it can express alarm, and it cannot express a REQUIREMENT.

⚑ THE DECIDING RESTRICTION IS WHERE THE FLOOR RUNS OUT ENTIRELY, AND THAT IS THE POINT OF SCORING
IT. Tone can say "something is wrong here". It cannot say WHICH of eight restrictions is wrong,
because the note does not carry that and no keyword list can invent it. So the floor answers `none`
when it reads a calm note -- an honest answer that happens to be right on the calm cases that are
genuinely inside the label -- and null on every case it calls a problem. It is not crippled to make
a point; it has simply reached the edge of what prose can do, and that edge is the finding.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes every one of the twenty structured fields out of the page; calling
src.checks.decide() on them would score 100 pct and tell you nothing about the model. So the floor
is deliberately the SHORTCUT, not the walk, and the gap it opens is the gap between reading prose
and reading a label.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword that fired on
a negation inside a relaxed note and mis-registered four records for days. Every phrase here is
multi-word or a stem that appears in one register only, and evals/check_labels.py asserts that
property before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived verdict produces a
tone-derived hold flag: the floor reads application_status correctly by regex every time and the
verdict wrong on the planted cases, and the flag inherits the error. That is worth publishing
rather than hiding -- a business-condition guardrail is only ever as good as the field it reads.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any CALM note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("checked", "label", "records") would appear in
# both registers on this corpus and misfire either way.
WORRIED_KEYWORDS = ("not comfortable", "hold off", "looked off", "second read", "disputed",
                    "manual audit", "escalated", "complained about")

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _line(text, section, prefix):
    body = _section(text, section)
    if body is None:
        return None
    m = re.search(r"^%s\s*:\s*(.*)$" % re.escape(prefix), body, re.M | re.I)
    return m.group(1).strip() if m else None


def _num(raw):
    """The first number on a line, or None where the line says the value is not stated."""
    if raw is None:
        return None
    low = raw.lower()
    if low.startswith("not stated") or low.startswith("no application made"):
        return None
    m = _NUM.search(raw)
    if not m:
        return None
    v = float(m.group(0))
    return int(v) if abs(v - round(v)) < 1e-9 else v


def extract_one(text, fields):
    L = "Label Restrictions"
    P = "Proposed Application"
    values = {
        "field_id": _section(text, "Field"),
        "permitted_crops": _line(text, L, "permitted crops"),
        "max_rate_l_per_ha": _num(_line(text, L, "maximum rate per application")),
        "max_applications_per_season": _num(_line(text, L, "maximum applications per season")),
        "min_retreatment_interval_days": _num(_line(text, L, "minimum re-treatment interval")),
        "pre_harvest_interval_days": _num(_line(text, L, "pre-harvest interval")),
        "re_entry_interval_hours": _num(_line(text, L, "re-entry interval")),
        "buffer_to_water_m": _num(_line(text, L, "minimum buffer to surface water")),
        "tank_mix_prohibited_with": _line(text, L, "tank mix prohibited with"),
        "crop_proposed": _line(text, P, "crop"),
        "rate_proposed_l_per_ha": _num(_line(text, P, "rate")),
        "applications_made_this_season": _num(_line(text, P,
                                                    "applications already made this season")),
        "days_since_last_application": _num(_line(text, P, "days since the last application")),
        "days_to_harvest": _num(_line(text, P, "days to harvest")),
        "planned_re_entry_hours": _num(_line(text, P, "planned re-entry")),
        "distance_to_water_m": _num(_line(text, P, "distance to nearest surface water")),
        "tank_mix_partner": _line(text, P, "tank mix partner"),
        "previous_season_applications": _num(
            _line(text, "Season History", "applications made in the PREVIOUS season")),
        "application_status": _section(text, "Application Status"),
        "agronomist_note": _section(text, "Agronomist Notes"),
    }

    low = (values["agronomist_note"] or "").lower()
    worried = any(k in low for k in WORRIED_KEYWORDS)
    values["verdict"] = "outside_label" if worried else "within_label"
    # Tone can express alarm. It cannot name which of eight restrictions is the problem, so the
    # floor says `none` when it sees no alarm and nothing at all when it does.
    values["deciding_restriction"] = None if worried else "none"

    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_hold": _compute(values), "recomputed_verdict": None,
            "recomputed_restriction": None, "recomputed_reason": None, "recomputed_checks": [],
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
