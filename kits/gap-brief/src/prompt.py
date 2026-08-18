"""Assemble the one prompt this kit sends per cycle, and parse the one reply it gets back.

ONE CALL PER CYCLE, NOT PER GAP. All of a cycle's material gaps are decided in a single call that
receives the packed gap list and the cycle's notes log together -- the notes log is the shared,
expensive payload; batching every gap in the cycle into one call is what keeps this kit from
re-sending the same notes once per gap.

⚠︎ NO FIELD IN THIS SCHEMA CAN RANK OR RECOMMEND. This is a decision-free kit by the atlas row's
own guardrail: the model tags a probable cause and drafts a narrative, never a preference between
the three plan views and never a recommended action. There is no field to put one in, and the
system prompt says so explicitly rather than leaving it to be inferred.

⚠︎ 'unknown' IS SAFE TO SAY, AND SAYING SOMETHING ELSE WITHOUT REAL SUPPORT IS THE FAILURE MODE
THIS KIT MEASURES. The system prompt states this twice -- once as an instruction, once as the
literal cost of getting it wrong -- because a model asked to give a "no idea" answer only 12% of
the time defaults toward looking useful over being honest, and evals/scoring.py's fabrication
guardrail is built to catch exactly that.
"""
import json

from . import rubric as R

MAX_TOKENS = 2200

_CAUSES_TXT = "".join("  %-20s %s\n" % (c, R.CAUSE_MEANINGS[c]) for c in R.CAUSE_VOCAB)

SYSTEM = (
    "You are drafting the gap brief for a plan-reconciliation review meeting. You are given one "
    "planning cycle's MATERIAL gaps -- line items where three independently-maintained plan views "
    "(demand, supply, financial) disagree by enough to matter, already identified by code -- and "
    "that cycle's own planning notes log.\n\n"
    "For EACH gap in the list, decide which of these five causes applies, using ONLY the notes "
    "log -- never outside knowledge, never a plausible-sounding guess:\n\n" + _CAUSES_TXT + "\n"
    "If the notes log supports a specific cause for that item, name it and cite the exact two "
    "notes lines (verbatim) that together support it. If the notes log does NOT support a "
    "specific cause for that item -- no line mentions it, or the lines that do mention it don't "
    "add up to one of the four named causes -- the cause is 'unknown' and the two citation "
    "fields must be empty strings. Do not cite a line that does not actually name or clearly "
    "concern that item just because it is the closest-sounding one available: an unsupported "
    "'unknown' is the correct, honest answer and is graded as such; a cause with a citation that "
    "is not really about that item is graded as a fabrication, which is worse.\n\n"
    "Each gap also carries a missing_view field in the input, set to a view name when that view "
    "was never submitted this cycle, or null when all three views are present. Echo that exact "
    "state back in your answer for that gap -- true if a view is missing, false if not.\n\n"
    "After the per-gap entries, write a short narrative (3-6 sentences) for the meeting audience "
    "that ties the material gaps together. Every number you state in the narrative -- a dollar "
    "figure, a percentage, a count of gaps -- must be a number that is actually present in the "
    "gap list you were given; do not compute, round, or restate a figure that changes its value.\n\n"
    "NEVER recommend which plan view is correct, and never rank or suggest an action to take. "
    "That decision belongs to the humans in the meeting this brief is for -- your job is limited "
    "to itemizing, tagging a probable cause (or saying unknown), and describing what the gaps "
    "are, never what should be done about them."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _gap_block(packed):
    lines = []
    for g in packed["gaps"]:
        v = g["views"]
        vtxt = ", ".join(
            "%s=%s" % (k.replace("_plan_usd", ""), ("$%.2f" % val) if val is not None else "not submitted")
            for k, val in v.items()
        )
        lines.append(
            "- %s (%s): %s | spread $%.2f (%s%%) | missing_view=%s"
            % (g["item_id"], g["item_label"], vtxt, g["delta_usd"],
               g["delta_pct"] if g["delta_pct"] is not None else "n/a", g["missing_view"])
        )
    return "\n".join(lines)


def _notes_block(packed):
    return "\n".join("- %s" % n for n in packed["notes"])


def build(packed, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    header = ("Cycle %s -- %s, %s\n" % (packed["cycle_id"], packed["business_unit"], packed["period"]))
    gap_block = _gap_block(packed)
    notes_block = _notes_block(packed)
    n_gaps = len(packed["gaps"])
    user = (
        header +
        "\nMATERIAL GAPS (%d)\n------------------\n%s\n\n"
        "PLANNING NOTES LOG\n-------------------\n%s\n\n"
        "Return a JSON object with two keys: \"gaps\", a list with exactly %d entries, one per "
        "gap above in the same order, each {\"item_id\": <id>, \"cause\": <one of: %s>, "
        "\"citation_1\": <verbatim notes line, or \"\">, \"citation_2\": <verbatim notes line, or "
        "\"\">, \"missing_view\": <true or false>, \"note\": <one sentence>}; and \"narrative\", "
        "a string of 3-6 sentences.\n"
        "Answer with the JSON object only." % (n_gaps, gap_block, notes_block, n_gaps,
                                               ", ".join(R.CAUSE_VOCAB))
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "gaps", "text": header + "\nMATERIAL GAPS (%d)\n------------------\n%s"
                                 % (n_gaps, gap_block)},
        {"name": "notes", "text": "PLANNING NOTES LOG\n-------------------\n%s" % notes_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the gap list and narrative out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields {"gaps": [], "narrative": None} -- read as "this call
    produced no answer", never as evidence about the cycle."""
    empty = {"gaps": [], "narrative": None}
    if not raw:
        return empty
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return empty
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return empty
    gaps = []
    for entry in (obj.get("gaps") or []):
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "")).strip()
        if not item_id:
            continue
        cause = str(entry.get("cause", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if cause not in R.CAUSE_VOCAB:
            cause = None
        mv = entry.get("missing_view")
        gaps.append({
            "item_id": item_id, "cause": cause,
            "citation_1": str(entry.get("citation_1", "") or ""),
            "citation_2": str(entry.get("citation_2", "") or ""),
            "missing_view": bool(mv) if isinstance(mv, bool) else None,
            "note": str(entry.get("note", "") or ""),
        })
    narrative = obj.get("narrative")
    narrative = str(narrative) if isinstance(narrative, str) and narrative.strip() else None
    return {"gaps": gaps, "narrative": narrative}
