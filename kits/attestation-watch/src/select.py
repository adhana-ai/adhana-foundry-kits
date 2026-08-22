"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model, and the last place a value's provenance is decided before anything is asked of anybody.

⚑ `Prepared By` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every register in this corpus
records who assembled it and on what date; no field asks for it, so the union of the mapped
sections leaves it out and it never leaves the machine. It is the one section a reader can point at
and say "that is what selection did" -- the rest of the saving is real and invisible, because the
sections that are sent would have been sent anyway.

⚑ THE SECOND JOB HERE IS SCOPING A SEARCH, NOT SAVING TOKENS, AND ON THIS CORPUS IT IS THE BIGGER
ONE. Four sections carry ISO dates and four carry person references. An unscoped document-wide
search for `2026-03-05` would happily cite the Returns Filed section for a cycle-opened date that
is genuinely correct, and cite a disposal date for a filing date. `src/extract.py::_locate` walks
the sections a field is MAPPED to first, and only then falls back to the whole register.

⚑ `status` IS MAPPED TO THE SECTIONS THE RULE ACTUALLY READS, AND NOT TO `Register Notes`. That is
a statement of the rule rather than a saving, and it is the map of this kit's one decoy: the
administrator's note is prose written by somebody who did not run the rulebook, and on 40 pct of
these registers it reads the opposite way from what the register's own facts say. The note still
reaches the model -- it is a field in its own right, and the union of every field's sections is
what gets sent -- so this mapping is not a filter that hides it. It is the map of where the answer
actually lives.

⚑ AND NOTE WHERE `roster_event` IS MAPPED. To `Roster Changes` ONLY. The roster line in
`Attesters On Record` cannot tell a person who joined last week from a record nobody wrote a cycle
date for: both print the same words. The thing that separates them is in a different section, and
this map says so.
"""

# Register-level fields, then per-attester fields. One flat table because a field name is unique
# across both sets, and two tables would be two things to keep in step.
SECTION_HINTS = {
    "engagement_ref": ["Engagement"],
    "as_at_date": ["Register As At"],
    "rulebook_id": ["Cycle Rulebook"],
    "register_note": ["Register Notes"],

    "person_ref": ["Attesters On Record"],
    "role": ["Attesters On Record"],
    "roster_event": ["Roster Changes"],
    "cycle_opened_on": ["Attesters On Record"],
    "return_filed_on": ["Returns Filed"],
    "return_covers_to": ["Returns Filed"],
    "declared_relationship": ["Returns Filed"],
    "earlier_declared_relationship": ["Returns Filed"],
    "relationship_disposed_on": ["Holdings And Relationships On File"],

    # Derived, and not spannable: no register states a due date, so there is nothing to locate.
    "due_on": ["Attesters On Record", "Cycle Rulebook"],
    "status": ["Attesters On Record", "Returns Filed",
               "Holdings And Relationships On File", "Roster Changes"],
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
