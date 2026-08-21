"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole report is ten times the input tokens of sending each field the section that could possibly
state it.

⚠︎ TWO FIELDS DELIBERATELY GET TWO SECTIONS. `narrative_severity_word` and `is_serious` are the
pair this kit exists to keep apart -- the colloquial wording and the regulatory classification --
and each can only be answered by seeing both the Event Description (where the wording lives) and
the Case Narrative (where what actually happened lives). Narrowing either to one section would
hand the model exactly the half-view that produces the mistake being measured.
"""

SECTION_HINTS = {
    "case_id": ["Case ID"],
    "patient_age_range": ["Patient Age Range"],
    "suspect_drug": ["Suspect Drug"],
    "event_description": ["Event Description"],
    "narrative_severity_word": ["Event Description", "Case Narrative"],
    "hospitalization": ["Hospitalization"],
    "event_outcome": ["Event Outcome"],
    "causality_assessment": ["Reporter Causality Assessment"],
    "reporter_type": ["Reporter Type"],
    "is_serious": ["Event Description", "Hospitalization", "Event Outcome", "Case Narrative"],
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
