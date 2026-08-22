"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending ten fields x the
whole sheet is ten times the input tokens of sending each field the section that could possibly
state it.

⚑ `Terminal and Berth` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every pre-load check
sheet in this corpus states which terminal and berth the tank is sitting at; no field asks for it,
so the union of the mapped sections leaves it out and it is never sent. It is the one section a
reader can point at and say "that is what selection did" -- the rest of the saving is real but
invisible, because the sections that are sent would have been sent anyway.

⚑ `verdict` IS MAPPED TO THE FIVE FACTS THE RULE ACTUALLY USES, AND NOT TO `Wash Performed` AND
NOT TO `Inspector Notes`. That is a statement of the rule rather than a saving, and it is the map
of this kit's two decoys at once:

  - the INSPECTOR'S NOTE is prose written by a person who did not run the matrix, and on this
    corpus it often reads the opposite way from what the facts say;
  - the WASH PERFORMED line is the tank log's own claim about what was done. Only the CERTIFICATE
    counts. A sheet whose log says `caustic_wash` and whose certificate says `water_rinse` is a
    tank credited with a water rinse.

Both still reach the model -- each is a field in its own right, and the union of every field's
sections is what gets sent -- so this mapping is not a filter that hides either decoy. It is the
map of where the answer actually lives.
"""

SECTION_HINTS = {
    "tank_id": ["Tank"],
    "incoming_product": ["Incoming Product"],
    "incoming_grade": ["Incoming Grade"],
    "prior_cargo": ["Prior Cargo"],
    "two_back_cargo": ["Two-Back Cargo"],
    "wash_performed": ["Wash Performed"],
    "wash_certified_for": ["Cleaning Certificate"],
    "load_status": ["Load Status"],
    "inspector_notes": ["Inspector Notes"],
    "verdict": ["Incoming Product", "Incoming Grade", "Prior Cargo", "Two-Back Cargo",
                "Cleaning Certificate"],
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
