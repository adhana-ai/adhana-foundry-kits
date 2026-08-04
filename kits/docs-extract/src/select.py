"""Pick which sections plausibly carry each field. Pure code — the last deterministic step
before the model, and the counterpart of UC001's retriever.

WHY SELECT AT ALL, WHEN THESE DOCUMENTS FIT IN A CONTEXT WINDOW.
They do fit — the largest is a few thousand tokens — so passing the whole document would work and
would cost more. That is the real reason this node exists, and it is the same lesson UC001's
prompt-parts breakdown teaches from the other side: THE BILL IS DRIVEN BY THE CONTEXT, NOT BY THE
QUESTION. Sending 9 fields x the whole document is nine times the input tokens of sending each
field the two sections that could possibly contain it.

It is also the honest seam. `SECTION_HINTS` is a per-corpus mapping and a forker WILL have to
change it; keeping it in one small dict with no cleverness makes that a five-minute edit rather
than an archaeology exercise. When it does not match, `for_field` returns the whole document,
which is slower and more expensive and always correct — the failure mode is a bigger bill, never
a wrong answer.
"""

# Field -> the section names most likely to state it, best first. Names match the headings
# build_corpus.py writes. A field absent here gets the whole document.
SECTION_HINTS = {
    "nct_id": ["header"],
    "brief_title": ["header"],
    "condition": ["header"],
    "primary_outcome": ["Primary Outcome Measures"],
    "sex": ["Eligibility Criteria"],
    "minimum_age": ["Eligibility Criteria"],
    "allocation": ["Detailed Description", "Brief Summary"],
    "enrollment": ["Detailed Description", "Brief Summary"],
    "masking": ["Detailed Description", "Brief Summary"],
}


def for_field(secs, field):
    """The sections to send for one field, in document order. Never empty."""
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    hit = [s for s in secs if s["name"] in want]
    return hit or list(secs)


def plan(secs, fields):
    """{field: [section names]} — the whole selection, as data, so it can be printed, diffed and
    put in a run record instead of being an invisible decision inside the prompt builder."""
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
