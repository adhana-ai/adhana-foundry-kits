"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending every field crossed with the
whole register is many times the input tokens of sending each field the section that could possibly
state it.

⚑ `Register Note` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every register in this
corpus carries the site's own summary self-assessment -- "nothing expected to fall due before the
next cycle" -- and no field asks for it, so the union of the mapped sections leaves it out and it
never reaches the provider at all. It is the one section a reader can point at and say "that is what
selection did"; the rest of the saving is real but invisible, because the sections that are sent
would have been sent anyway.

⚠︎ AND IT IS NOT ONLY A SAVING. That note is the site's own view of its compliance position, it is
written by the party whose obligations are being checked, and on this corpus it is routinely
contradicted by the worklist the rulebook computes. A monitor that reads it has read an opinion. It
is left out of every call for the same reason the per-row `register_flag` is extracted but never
used: the register says what it says, and the rulebook decides.

⚑ THE OBLIGATION BLOCKS ARE MATCHED BY PREFIX, NOT BY NAME. Every register has a different set of
condition identifiers, so `Condition C-7.3` cannot be a key in a fixed dict. `SECTION_PREFIXES` is
how a field says "every block of this kind", and it is the one thing here that is not a lookup.
"""

# Document-level fields -> the exact section names that state them.
SECTION_HINTS = {
    "site_id": ["Site"],
    "permit_no": ["Permit"],
    "register_date": ["Register Date"],
}

# Fields whose sections are matched on a heading PREFIX. `obligations` is the whole per-condition
# half of the record, so it maps to every Condition block and to nothing else.
SECTION_PREFIXES = {
    "obligations": ["Condition "],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if want:
        hit = [s for s in secs if s["name"] in want]
        return hit or list(secs)
    prefixes = SECTION_PREFIXES.get(field)
    if prefixes:
        hit = [s for s in secs if any(s["name"].startswith(p) for p in prefixes)]
        return hit or list(secs)
    return list(secs)


def for_condition(secs, condition_id):
    """The one block a named condition's values must be read from.

    ⚠︎ SCOPED, AND ON THIS CORPUS IT MATTERS MORE THAN ON MOST. Every register carries several
    condition blocks with the SAME nine line labels and dates drawn from the same few months, so an
    unscoped document-wide search would happily cite condition C-3.1's block for a date that
    genuinely belongs to C-8.4. Scoping costs nothing and closes the whole class.
    """
    if not condition_id:
        return []
    name = "Condition %s" % str(condition_id).strip()
    return [s for s in secs if s["name"] == name]


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
