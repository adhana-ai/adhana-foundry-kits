"""Assemble the one prompt this kit sends per review batch, and parse the one reply it gets back.

ONE CALL PER BATCH, NOT PER ITEM. All of a batch's material exceptions are decided in a single
call that receives the packed exception list and the batch's merchant notes log together -- the
notes log is the shared, expensive payload; batching every item in the batch into one call is what
keeps this kit from re-sending the same notes once per item.

⚠︎ NO FIELD IN THIS SCHEMA CAN RECOMMEND ACCEPTING OR OVERRIDING THE STATISTICAL FORECAST. This is
a decision-free kit by the atlas row's own guardrail: the model assembles the evidence, tags a
probable cause and drafts a narrative -- never a verdict on whether the statistical forecast should
be kept or changed. There is no field to put one in, and the system prompt says so explicitly
rather than leaving it to be inferred.

⚠︎ 'unknown' IS SAFE TO SAY, AND SAYING SOMETHING ELSE WITHOUT REAL SUPPORT IS THE FAILURE MODE
THIS KIT MEASURES. The system prompt states this twice -- once as an instruction, once as the
literal cost of getting it wrong -- because a model asked to give a "no idea" answer only some of
the time defaults toward looking useful over being honest, and evals/scoring.py's fabrication
guardrail is built to catch exactly that.
"""
import json

from . import rubric as R

MAX_TOKENS = 2200

_CAUSES_TXT = "".join("  %-20s %s\n" % (c, R.CAUSE_MEANINGS[c]) for c in R.CAUSE_VOCAB)

SYSTEM = (
    "You are assembling the exception review packet for a statistical demand-forecast review "
    "meeting. You are given one review batch's MATERIAL exceptions -- item/location combinations "
    "where recent POS disagrees with the statistical forecast by enough to matter, or whose recent "
    "POS is flagged unreliable, already identified by code -- and that batch's own merchant notes "
    "log.\n\n"
    "For EACH exception in the list, decide which of these five causes applies, using ONLY the "
    "notes log and the evidence fields already on the item -- never outside knowledge, never a "
    "plausible-sounding guess:\n\n" + _CAUSES_TXT + "\n"
    "If the notes log supports a specific cause for that item, name it and cite the exact two "
    "notes lines (verbatim) that together support it. If the notes log does NOT support a specific "
    "cause for that item -- no line mentions it, or the lines that do mention it don't add up to "
    "one of the four named causes -- the cause is 'unknown' and the two citation fields must be "
    "empty strings. Do not cite a line that does not actually name or clearly concern that item "
    "just because it is the closest-sounding one available: an unsupported 'unknown' is the "
    "correct, honest answer and is graded as such; a cause with a citation that is not really "
    "about that item is graded as a fabrication, which is worse.\n\n"
    "Each exception also carries an unreliable_evidence field in the input, set to true when this "
    "item/location's recent POS could not be trusted this week (a data or register outage), or "
    "false when the actual figure is trustworthy. Echo that exact state back in your answer for "
    "that item.\n\n"
    "After the per-item entries, write a short narrative (3-6 sentences) for the review-meeting "
    "audience that ties the material exceptions together. Every number you state in the narrative "
    "-- a unit figure, a percentage, a count of exceptions -- must be a number that is actually "
    "present in the exception list you were given; do not compute, round, or restate a figure that "
    "changes its value.\n\n"
    "NEVER recommend whether to accept or override the statistical forecast, and never rank or "
    "suggest an action to take. That decision belongs to the demand planner in the meeting this "
    "packet is for -- your job is limited to itemizing, tagging a probable cause (or saying "
    "unknown), and describing what the exceptions are, never what should be done about them."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _item_block(packed):
    lines = []
    for it in packed["items"]:
        if it["unreliable_evidence"]:
            actual_txt = "recent POS unreliable this week"
        else:
            actual_txt = "actual=%s" % it["actual_pos_units"]
        lines.append(
            "- %s (%s @ %s): forecast=%s | %s | prior_year_analog=%s | spread %s (%s%%) | "
            "lost_sales_oos_flag=%s | promo_flag=%s | unreliable_evidence=%s"
            % (it["item_id"], it["item_label"], it["location"], it["forecast_units"], actual_txt,
               it["prior_year_analog_units"], it["delta_units"],
               it["delta_pct"] if it["delta_pct"] is not None else "n/a",
               it["lost_sales_oos_flag"], it["promo_flag"], it["unreliable_evidence"])
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
    header = ("Batch %s -- %s, %s\n" % (packed["batch_id"], packed["region"], packed["review_week"]))
    item_block = _item_block(packed)
    notes_block = _notes_block(packed)
    n_items = len(packed["items"])
    user = (
        header +
        "\nMATERIAL EXCEPTIONS (%d)\n------------------------\n%s\n\n"
        "MERCHANT NOTES LOG\n-------------------\n%s\n\n"
        "Return a JSON object with two keys: \"items\", a list with exactly %d entries, one per "
        "exception above in the same order, each {\"item_id\": <id>, \"cause\": <one of: %s>, "
        "\"citation_1\": <verbatim notes line, or \"\">, \"citation_2\": <verbatim notes line, or "
        "\"\">, \"unreliable_evidence\": <true or false>, \"note\": <one sentence>}; and "
        "\"narrative\", a string of 3-6 sentences.\n"
        "Answer with the JSON object only." % (n_items, item_block, notes_block, n_items,
                                               ", ".join(R.CAUSE_VOCAB))
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "items", "text": header + "\nMATERIAL EXCEPTIONS (%d)\n------------------------\n%s"
                                 % (n_items, item_block)},
        {"name": "notes", "text": "MERCHANT NOTES LOG\n-------------------\n%s" % notes_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the item list and narrative out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields {"items": [], "narrative": None} -- read as "this call
    produced no answer", never as evidence about the batch."""
    empty = {"items": [], "narrative": None}
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
    items = []
    for entry in (obj.get("items") or []):
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "")).strip()
        if not item_id:
            continue
        cause = str(entry.get("cause", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if cause not in R.CAUSE_VOCAB:
            cause = None
        ue = entry.get("unreliable_evidence")
        items.append({
            "item_id": item_id, "cause": cause,
            "citation_1": str(entry.get("citation_1", "") or ""),
            "citation_2": str(entry.get("citation_2", "") or ""),
            "unreliable_evidence": bool(ue) if isinstance(ue, bool) else None,
            "note": str(entry.get("note", "") or ""),
        })
    narrative = obj.get("narrative")
    narrative = str(narrative) if isinstance(narrative, str) and narrative.strip() else None
    return {"items": items, "narrative": narrative}
