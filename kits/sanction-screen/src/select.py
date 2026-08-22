"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending seventeen fields x the
whole alert sheet is more input tokens than sending each field the section that could possibly
state it.

⚑ `Screening List` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING -- AND IT IS ALSO AN
ARGUMENT. Every alert sheet in this corpus states which list the entry sits on, which programme it
was published under, when it was published, and THE SCREENING ENGINE'S OWN MATCH SCORE. No field
asks for any of it, so the union of the mapped sections leaves the whole section out and it never
reaches the model.

The engine's match score is the part worth pausing on. It is the number a human reader anchors to
first, it decides NOTHING in `data/rulebook.json`, and on this corpus it is deliberately misleading
often -- a 0.94 on two records with conflicting passport numbers, a 0.61 on two records carrying
the same one. Keeping it out of the call is the cleanest statement this kit makes about what the
adjudication is for: the answer lives in the identifiers, not in how alike two strings look.

⚑ `verdict` AND `deciding_identifier` ARE MAPPED TO THE TWO RECORDS AND TO NOTHING ELSE. That is a
statement of the rule rather than a saving, and it is the map of this kit's three decoys at once:

  - the ANALYST NOTE is prose written by somebody who triaged the alert before anybody compared
    the identifiers, and on this corpus it often reads the opposite way from what the file says;
  - the NATIONALITY PAIR is a weak field. A list record's nationality is routinely stale or
    secondary, so two records for one party disagree about it all the time;
  - the ENGINE MATCH SCORE, above, which the model never even sees.

The first two still reach the model -- each is a field in its own right, and the union of every
field's sections is what gets sent -- so this mapping is not a filter that hides them. It is the
map of where the answer actually lives.
"""

SECTION_HINTS = {
    "alert_id": ["Alert Reference"],
    "customer_name": ["Customer Record"],
    "listed_name": ["Watchlist Entry"],
    "customer_identifier_type": ["Customer Record"],
    "customer_identifier_value": ["Customer Record"],
    "listed_identifier_type": ["Watchlist Entry"],
    "listed_identifier_value": ["Watchlist Entry"],
    "customer_dob": ["Customer Record"],
    "listed_dob": ["Watchlist Entry"],
    "customer_place_of_birth": ["Customer Record"],
    "listed_place_of_birth": ["Watchlist Entry"],
    "customer_nationality": ["Customer Record"],
    "listed_nationality": ["Watchlist Entry"],
    "account_status": ["Account Status"],
    "analyst_note": ["Analyst Note"],
    "verdict": ["Customer Record", "Watchlist Entry"],
    "deciding_identifier": ["Customer Record", "Watchlist Entry"],
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
