"""A free, rules-and-regex reconciler. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ THIS FLOOR IS THE TAG SHORTCUT, WRITTEN TO FAIL BY CONSTRUCTION. It reads the figures printed on
the component's own tag and treats them as the accumulated life since new. It never reconstructs
the record trail, so it never sums anything, never notices an overhaul line, and never notices that
a period of records is missing. That is precisely the shortcut a rushed records review takes -- the
tag says 14,820 hours, the limit is 20,000, the pack is fine -- and it is precisely what the kit
exists to refuse.

⚠︎ IT WOULD BE STRAIGHTFORWARD TO MAKE THIS BASELINE MUCH BETTER, AND THAT IS THE POINT OF NOT
DOING IT. Every `accrued N hours / M cycles` line in the trail is one regex away, and summing them
is two more lines. A rules baseline that did the arithmetic would score very well on this corpus
and tell you nothing about the model -- so the floor is deliberately the SHORTCUT, not the method,
and the gap it opens is the gap between reading the tag and reconstructing the trail.

⚠︎ WHAT IT GETS RIGHT MATTERS AS MUCH AS WHAT IT GETS WRONG. The floor is exact on every field the
pack states in one place -- the identifiers, both published limits, both tag figures, the declared
gap, the requested disposition and the reviewer's note. Its failures are concentrated in exactly
the four fields nobody can regex: the two reconstructed totals, the tag comparison and the life
status. A page that reported only a headline gap would hide that, and the honest reading is that
most of this task is not the hard part.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tag-derived life status produces a
tag-derived escalation: the floor reads the requested disposition correctly by regex every time and
still mis-escalates, because the flag inherits the fields it reads. That is worth publishing rather
than hiding -- a business-condition guardrail is only ever as good as the field it reads, which is
the honest half of shipping one.
"""
import re

from src.extract import compute as _compute
from src.extract import life_status as _life
from src.extract import spannable as _spannable

# The floor's whole worldview, in one place: the tag is the record. It is stated as a constant so
# the shortcut is a named assumption a reader can argue with, not a line buried in a function.
TAG_IS_THE_RECORD = True


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _pair(s):
    """Split '20000 hours / 15000 cycles since new' into (20000, 15000). Returns (None, None)
    when the line does not state a pair."""
    if s is None:
        return None, None
    m = re.match(r"\s*(\d+)\s*hours?\s*/\s*(\d+)\s*cycles?", s)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def extract_one(text, fields):
    component_id = _section(text, "Component")
    part_reference = _section(text, "Part Reference")
    limit_h, limit_c = _pair(_section(text, "Published Life Limit"))
    tag_h, tag_c = _pair(_section(text, "Component Tag Figures"))
    gap_line = _section(text, "Records Gap")
    record_gap = "no" if (gap_line or "").lower().startswith("none declared") else "yes"
    disposition = _section(text, "Disposition Requested")
    reviewer_note = _section(text, "Reviewer Note")

    # ⚑ THE SHORTCUT, IN THREE LINES. The tag becomes the reconstructed total; the tag therefore
    # agrees with itself; and the life status is computed off the tag with the declared gap
    # ignored, because a floor that believes the tag is complete has no reason to care that a
    # period of records is missing.
    trail_h, trail_c = tag_h, tag_c
    tag_agrees = "yes"
    status = _life(trail_h, trail_c, limit_h, limit_c, "no")

    values = {
        "component_id": component_id, "part_reference": part_reference,
        "life_limit_hours": limit_h, "life_limit_cycles": limit_c,
        "tag_hours": tag_h, "tag_cycles": tag_c,
        "trail_hours": trail_h, "trail_cycles": trail_c,
        "record_gap": record_gap, "disposition_requested": disposition,
        "reviewer_note": reviewer_note, "tag_agrees": tag_agrees, "life_status": status,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": _spannable(f), "span": None}
           for f in fields}
    return {"fields": out, "escalate": _compute(values), "recomputed_life_status": None,
            "recomputed_tag_agrees": None, "sections_used": [], "prompt_parts": [],
            "input_tokens": 0, "output_tokens": 0, "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
