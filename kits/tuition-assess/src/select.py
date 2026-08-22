"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending twelve fields x the whole
record is twelve times the input tokens of sending each field the section that could possibly state
it.

⚑ `Campus` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every student account record in
this corpus states which campus the enrolment sits on; no field asks for it, so the union of the
mapped sections leaves it out and it is never sent. It is the one section a reader can point at and
say "that is what selection did" -- the rest of the saving is real but invisible, because the
sections that are sent would have been sent anyway.

⚑ `assessment_correct` AND `variance_reason` ARE MAPPED TO THE FIVE FACTS THE ARITHMETIC ACTUALLY
USES, AND TO NEITHER DECOY. That is a statement of the rule rather than a saving. A correct
assessment is a number computed from a residency tier, a credit load, a course level and a waiver
type, and compared against the total the bursar system already wrote down; the residency ACTION and
the bursar's own note are evidence of nothing about it.

⚠︎ THIS IS NOT A FILTER THAT HIDES THE DECOYS. Both of them are fields in their own right, and the
union of every field's sections is what gets sent -- so the model reads the reclassification line
and the bursar's note on every single record. This mapping is the map of where the ANSWER lives,
not a fence around the question. A kit that scored well by never showing the model the trap would
have measured nothing.
"""

SECTION_HINTS = {
    "student_account_id": ["Student Account"],
    "term_code": ["Term"],
    "residency_tier": ["Residency Tier"],
    "enrolled_credits": ["Enrolled Credits"],
    "course_level": ["Course Level"],
    "waiver_type": ["Waiver"],
    "assessed_total_usd": ["Assessed Total"],
    "bill_status": ["Bill Status"],
    "residency_action": ["Residency Action"],
    "bursar_notes": ["Bursar Notes"],
    "assessment_correct": ["Residency Tier", "Enrolled Credits", "Course Level", "Waiver",
                           "Assessed Total"],
    "variance_reason": ["Residency Tier", "Enrolled Credits", "Course Level", "Waiver",
                        "Assessed Total"],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if s["name"] in want]
    return hit or list(secs)


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
