"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model. Same reasoning as every sibling extraction kit here: sending twenty-two fields x the
whole case is far more input tokens than sending each field the section that could possibly state
it.

⚑ `Product and Registration` IS MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every case in
this corpus names the product, its registration number and its active substance; no field asks for
any of them, so the union of the mapped sections leaves that section out and it never reaches the
provider at all. It is the one section a reader can point at and say "that is what selection did" --
the rest of the saving is real but invisible, because the sections that are sent would have been
sent anyway.

⚠︎ AND IT IS ALSO WHERE THIS CORPUS'S INVENTED CHEMISTRY LIVES. Every product name, registration
number and active substance in this kit is coined. Keeping them in the one section nothing asks for
means the model is never shown a made-up active substance and asked to reason about it, which is a
question it could only answer wrongly.

⚑ `verdict` AND `deciding_restriction` ARE MAPPED TO THE TWO SECTIONS THE CHECKS ACTUALLY READ,
AND TO NEITHER DECOY. That is a statement of the rule rather than a saving, and it is the map of
this kit's two decoys at once:

  - the AGRONOMIST'S NOTE is prose written by somebody who did not walk the check set, and on this
    corpus it often reads the opposite way from what the label and the proposal say;
  - the PREVIOUS SEASON'S application count is a real number about a real season and it is not part
    of any check, because the label maximum is per season. A reader who adds it to this season's
    count refuses applications that are inside the label.

Both still reach the model -- each is a field in its own right, and the union of every field's
sections is what gets sent -- so this mapping is not a filter that hides either decoy. It is the
map of where the answer actually lives.
"""

SECTION_HINTS = {
    "field_id": ["Field"],

    "permitted_crops": ["Label Restrictions"],
    "max_rate_l_per_ha": ["Label Restrictions"],
    "max_applications_per_season": ["Label Restrictions"],
    "min_retreatment_interval_days": ["Label Restrictions"],
    "pre_harvest_interval_days": ["Label Restrictions"],
    "re_entry_interval_hours": ["Label Restrictions"],
    "buffer_to_water_m": ["Label Restrictions"],
    "tank_mix_prohibited_with": ["Label Restrictions"],

    "crop_proposed": ["Proposed Application"],
    "rate_proposed_l_per_ha": ["Proposed Application"],
    "applications_made_this_season": ["Proposed Application"],
    "days_since_last_application": ["Proposed Application"],
    "days_to_harvest": ["Proposed Application"],
    "planned_re_entry_hours": ["Proposed Application"],
    "distance_to_water_m": ["Proposed Application"],
    "tank_mix_partner": ["Proposed Application"],

    "previous_season_applications": ["Season History"],
    "application_status": ["Application Status"],
    "agronomist_note": ["Agronomist Notes"],

    "verdict": ["Label Restrictions", "Proposed Application"],
    "deciding_restriction": ["Label Restrictions", "Proposed Application"],
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
