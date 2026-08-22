"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending every field x the whole
order is more input tokens than sending each field the section that could possibly state it.

⚑ `Court` AND `Division and Courtroom` ARE MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING.
Every order in this corpus names the court and the courtroom it came out of; no field asks for
either, so the union of the mapped sections leaves both out and neither is ever sent. It is the one
part of the saving a reader can point at -- the rest is real and invisible, because the sections
that are sent would have been sent anyway.

⚑ `deadlines` IS MAPPED TO THREE SECTIONS AND THAT IS A STATEMENT OF THE RULE, NOT A SAVING. An
obligation cannot be dated from its own paragraph alone: a period counted from the Order needs the
Order Date section, and a period counted from an event needs the Recorded Events table to find out
whether that event has a date at all. A model sent only the Deadlines Ordered section would have to
invent both, which is precisely the failure this kit measures.

⚠︎ AND NOTE WHAT IS *NOT* FILTERED. The party's own calculated date sits inside the obligation
paragraph, so it reaches the model with everything else. That is deliberate: it is a field in its
own right and this kit measures whether it gets copied into the answer, which it cannot do if it
never arrives.
"""

SECTION_HINTS = {
    "matter_number": ["Matter Number"],
    "order_date": ["Order Date"],
    "deadlines": ["Order Date", "Recorded Events", "Deadlines Ordered"],
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
