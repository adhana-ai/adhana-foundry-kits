"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step
before the model. Same reasoning as every sibling extraction kit here: sending eleven fields x
the whole package is eleven times the input tokens of sending each field the section that could
possibly state it.

⚑ `Prime Contractor` AND `Subcontract Reference` ARE MAPPED BY NOTHING, AND THAT IS THE VISIBLE
SAVING. Every package in this corpus names the general contractor holding the subcontract and the
subcontract number with its retainage percentage; no field asks for either, so the union of the
mapped sections leaves both out and neither is ever sent. They are the two sections a reader can
point at and say "that is what selection did" -- the rest of the saving is real but invisible,
because the sections that are sent would have been sent anyway.

⚑ THE THREE COVERAGE FIELDS ARE MAPPED TO THE THREE SECTIONS THE RULE ACTUALLY READS, AND NOT TO
THE COORDINATOR NOTE. That is a statement of the rule rather than a saving. Whether a party is
covered is arithmetic over the party block, the pay application's period-through date and whether
the prior payment has cleared; the payment coordinator's own note is evidence of nothing about
it. The note still reaches the model -- it is a field in its own right, and the union of every
field's sections is what gets sent -- so this mapping is not a filter that hides the decoy. It is
the map of where the answer actually lives.
"""

# The three sections the coverage rule reads: the party blocks, the period-through date the
# progress-waiver test compares against, and whether anything has cleared against a conditional
# waiver. Named once and reused, so the three coverage fields cannot drift apart.
COVERAGE_SECTIONS = ["Waiver Coverage", "Period Through", "Prior Payment Cleared"]

SECTION_HINTS = {
    "package_id": ["Package"],
    "project_name": ["Project"],
    "pay_app_number": ["Pay Application"],
    "period_through": ["Period Through"],
    "payment_amount_usd": ["Payment Amount"],
    "prior_payment_cleared": ["Prior Payment Cleared"],
    "release_status": ["Release Status"],
    "coordinator_note": ["Coordinator Note"],
    "parties_uncovered": COVERAGE_SECTIONS,
    "first_gap_party": COVERAGE_SECTIONS,
    "first_gap_reason": COVERAGE_SECTIONS,
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
