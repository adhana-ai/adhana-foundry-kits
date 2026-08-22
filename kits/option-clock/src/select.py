"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending seventeen fields x the whole
register is many times the input tokens of sending each field the section that could possibly state
it.

⚑ `Filing History` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every register in this
corpus carries a filing-history block -- when the file was opened, when it was last reindexed, what
class of rights it holds. No field asks for any of it, so the union of the mapped sections leaves it
out and it never reaches the provider. It is the one section a reader can point at and say "that is
what selection did"; the rest of the saving is real but invisible, because the sections that are
sent would have been sent anyway.

⚑ `expiry_date` AND `status` ARE MAPPED TO THE FACTS THE COUNT ACTUALLY READS, AND NOT TO
`Register Status` AND NOT TO `Clerk Note`. That is a statement of the rule rather than a saving, and
it is the map of this kit's two decoys at once:

  - the REGISTER STATUS line is what somebody last typed into a two-value column. It has no word
    for "lapsing inside the window" and no word for "the paperwork does not settle it", so even
    when it is honest it cannot carry the answer this kit computes;
  - the CLERK NOTE is one person's remark on the file. A relaxed note does not add a day to a term
    and a worried one does not remove one.

Both still reach the model -- each is a field in its own right, and the union of every field's
sections is what gets sent -- so this mapping is not a filter that hides either decoy. It is the map
of where the answer actually lives.

⚑ `Rights Holder` IS ON THE `status` MAP AND IT LOOKS LIKE IT SHOULD NOT BE. It is there because a
notice-controlled extension is only perfected by notice served on the GRANTOR OF RECORD, and the
only place the register names that party is the Rights Holder section. Whether an extension stacks
therefore depends on a section three headings above it -- which is exactly the reading the
`ext_wrong_party` sheets are built to test.
"""

SECTION_HINTS = {
    "register_id": ["Register"],
    "property_title": ["Property"],
    "rights_holder": ["Rights Holder"],
    "grantee": ["Grantee"],
    "register_as_of": ["Register As Of"],
    "option_granted_date": ["Option Granted"],
    "clock_basis": ["Clock Basis"],
    "trigger_status": ["Clock Basis", "Triggering Event"],
    "trigger_date": ["Triggering Event"],
    "initial_term_months": ["Initial Option Period"],
    "extension_months_each": ["Extension One", "Extension Two"],
    "extensions_recorded_taken": ["Extension One", "Extension Two"],
    "extensions_perfected": ["Rights Holder", "Extension One", "Extension Two"],
    "register_status": ["Register Status"],
    "clerk_note": ["Clerk Note"],
    "expiry_date": ["Rights Holder", "Register As Of", "Option Granted", "Clock Basis",
                    "Triggering Event", "Initial Option Period", "Extension One", "Extension Two"],
    "status": ["Rights Holder", "Register As Of", "Option Granted", "Clock Basis",
               "Triggering Event", "Initial Option Period", "Extension One", "Extension Two"],
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
