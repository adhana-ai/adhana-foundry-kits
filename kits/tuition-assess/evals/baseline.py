"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `assessment_correct` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the bursar's own note and nothing else: a note carrying one of a fixed list
of concerned-sounding phrases means "no" (mis-assessed), and anything else means "yes" (correct).
That is precisely the shortcut the prompt's rules forbid -- deciding correctness from prose instead
of from four structured values and a four-step rate table.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
rate table is twelve lines of arithmetic, and the baseline already regexes residency_tier,
enrolled_credits, course_level, waiver_type and assessed_total_usd out of the document. A rules
baseline that ran the table would score 100 pct on this corpus and tell you nothing about the
model -- so the floor is deliberately the SHORTCUT, not the rule, and the gap it opens is the gap
between reading prose and doing the arithmetic.

⚑ AND `variance_reason` HERE IS AN HONEST CONSTANT, NOT A GUESS DRESSED UP. A floor that cannot
compute correctness cannot possibly know which step of the table was departed from, so it answers
the corpus's most common reason on every record it calls wrong. It is stated here rather than
hidden because a reader is owed the difference between "the floor got 8 of 27 reasons right" and
"the floor named the modal class 27 times and 8 of them happened to be it".

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword ("flagging")
that fired on a negation inside a breezy note, mis-registering four records for days before it was
caught. evals/check_labels.py here asserts the same register property this floor's own list must
satisfy, before any run may spend -- see the note there.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived
`assessment_correct` produces a tone-derived review flag: the floor gets bill_status right by regex
every time and the correctness verdict wrong on the planted records, and the flag inherits the
error. That is worth publishing rather than hiding -- a business-condition guardrail is only ever
as good as the field it reads, which is the honest half of shipping one.
"""
import re

from src.extract import compute as _compute

# Concerned-sounding phrases, chosen so none of them is a substring of any BREEZY note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word
# phrases are used deliberately where a single word ("review", "look") appears in BOTH registers on
# this corpus and would misfire either way.
WORRIED_KEYWORDS = ("escalat", "mis-assess", "manual audit", "not confident", "second look",
                    "looked off", "revisit", "disputed")

# The modal variance reason in this corpus. Stated as a constant so the floor's reason column is
# obviously a constant rather than an inference.
MODAL_REASON = "credit band"


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _units(s):
    """Split '16 credit hours' into 16, or '3520 USD' into 3520. None when the line states no
    number."""
    if s is None:
        return None
    m = re.match(r"\s*(-?\d+)\b", s)
    return int(m.group(1)) if m else None


def extract_one(text, fields):
    student_account_id = _section(text, "Student Account")
    term_code = _section(text, "Term")
    residency_tier = _section(text, "Residency Tier")
    enrolled_credits = _units(_section(text, "Enrolled Credits"))
    course_level = _section(text, "Course Level")
    waiver_type = _section(text, "Waiver")
    assessed_total_usd = _units(_section(text, "Assessed Total"))
    bill_status = _section(text, "Bill Status")
    residency_action = _section(text, "Residency Action")
    bursar_notes = _section(text, "Bursar Notes")

    low = (bursar_notes or "").lower()
    correct = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"

    values = {
        "student_account_id": student_account_id, "term_code": term_code,
        "residency_tier": residency_tier, "enrolled_credits": enrolled_credits,
        "course_level": course_level, "waiver_type": waiver_type,
        "assessed_total_usd": assessed_total_usd, "bill_status": bill_status,
        "residency_action": residency_action, "bursar_notes": bursar_notes,
        "assessment_correct": correct,
        "variance_reason": MODAL_REASON if correct == "no" else "none",
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values),
            "recomputed_assessment_correct": None, "recomputed_total_usd": None,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
