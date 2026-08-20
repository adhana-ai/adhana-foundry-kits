"""Assemble the one prompt this kit sends per variance event, and parse the one reply it gets
back.

ONE CALL PER EVENT, NEVER BATCHED. Each variance event carries its own item/location's own
transaction history -- there is no shared, expensive payload to amortise across events the way
gap-brief amortises one cycle's notes log across its material gaps. One call per event keeps the
citation grounded in exactly the log the model was actually shown.

⚠︎ NO FIELD IN THIS SCHEMA CAN POST OR CLOSE ANYTHING. This is a decision-free kit by the use
case's own guardrail: the model drafts a likely cause for inventory control to confirm and
correct, never an adjustment, never a closure. There is no field to put one in.

⚠︎ 'unresolved' IS SAFE TO SAY, AND SAYING SOMETHING ELSE WITHOUT REAL SUPPORT IS THE FAILURE MODE
THIS KIT MEASURES. Stated twice in the system prompt -- once as instruction, once as the literal
cost of getting it wrong -- same discipline gap-brief's own prompt.py uses for 'unknown'.

⚑ 2500, NOT TIGHTER. A gap-brief-sized reply (cause + one or two citation indices + a short
narrative) does not need much text, but a tighter ceiling risks provider-side reasoning eating the
budget before the visible reply is written -- exactly what broke a sibling kit's first real run
tonight. This was not tightened from stub/baseline numbers, which never exercise real reasoning
consumption.
"""
import json

from . import rubric as R

# ⚑ THIS KIT'S REASONING BUDGET IS HEAVY-TAILED, AND THAT IS THE MEASUREMENT, NOT A GUESS.
# Four real runs to find the ceiling: 2500 -> 17 of 36 truncated; 4096 -> 14 of 36; 8192 -> 5 of
# 36. At 8192 the completed calls ran 382..8089 output tokens -- median 1447, p90 5619, and one
# call at 8089 hugging the wall, with reasoning alone reaching 8008 on a single event. The
# distribution is not tight around its median the way a fixed-shape reply is; a hard variance case
# reasons an order of magnitude longer than an easy one. Sized here to roughly 2x the largest
# COMPLETED call rather than just past it, because the five still-truncated events are by
# definition the ones whose true length was never observed.
# Every truncated run scored like a real finding and was not one: at 2500 this kit reported
# "53.1% FABRICATED CAUSE", at 8192 it reports 18.5%, and the difference is finish_reason, not
# the model. A truncated run prints a clean-looking summary -- always check finish_reason across
# every record before trusting any number here.
MAX_TOKENS = 16384

_CAUSES_TXT = "".join("  %-22s %s\n" % (c, R.CAUSE_MEANINGS[c]) for c in R.CAUSE_VOCAB)

SYSTEM = (
    "You are drafting the likely cause of ONE inventory cycle-count variance, for inventory "
    "control to confirm and correct. You never post an inventory adjustment and never close the "
    "variance yourself -- your job ends at a drafted cause, a citation and a short note for the "
    "human who does that work.\n\n"
    "You are given one item/location's own transaction history log for the relevant window, and "
    "the variance itself: system quantity minus physical count, signed. Decide which of these "
    "five causes the log actually supports, using ONLY this log -- never outside knowledge, "
    "never a plausible-sounding guess:\n\n" + _CAUSES_TXT + "\n"
    "A variance that divides evenly by a common case-pack size is suggestive but NOT sufficient "
    "by itself for uom_error -- only draft uom_error when a specific log line actually shows a "
    "unit-of-measure or case/each mismatch for this item. If instead the log points to activity "
    "at another location that was never logged here as a transfer, prefer unrecorded_transfer. "
    "Checking which the log actually supports, rather than pattern-matching the arithmetic alone, "
    "is the whole job.\n\n"
    "If the log supports a specific cause, cite the exact log line index (or two, for "
    "unscanned_movement, when more than one scan line is relevant) that supports it. If the log "
    "does not clearly support one of the four named causes -- no line addresses it, or the lines "
    "that do don't add up to one of them -- the cause is unresolved and citations must be an "
    "empty list. Do not cite a line just because it is the closest-sounding one available: an "
    "unsupported unresolved is the correct, honest answer and is graded as such; a specific cause "
    "with a citation that doesn't actually support it is graded as a fabrication, which is worse.\n\n"
    "After the cause and citation, write a short narrative (1-2 sentences) for inventory control "
    "that states the drafted cause and grounds it only in what the citation actually shows -- do "
    "not restate a quantity or a location that the cited line doesn't contain."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _log_block(packed):
    lines = []
    for l in packed["log"]:
        lines.append("%d: [%s] %s" % (l["idx"], l["type"], l["note"]))
    return "\n".join(lines)


def build(packed, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    header = ("Event %s -- item %s (%s), location %s, period %s\n"
             % (packed["event_id"], packed["item_id"], packed["item_label"],
                packed["location_id"], packed["period"]))
    variance_line = ("system %d, counted %d, variance_qty %+d (system minus counted)\n"
                     % (packed["system_qty"], packed["counted_qty"], packed["variance_qty"]))
    log_block = _log_block(packed)
    user = (
        header + variance_line +
        "\nTRANSACTION HISTORY LOG\n------------------------\n%s\n\n" % log_block +
        "Return a JSON object with three keys: \"cause\" (one of: %s); \"citations\" (a list of "
        "integer log line indices -- empty for unresolved); and \"narrative\" (a string of 1-2 "
        "sentences).\nAnswer with the JSON object only." % ", ".join(R.CAUSE_VOCAB)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "event", "text": header + variance_line},
        {"name": "log", "text": "TRANSACTION HISTORY LOG\n------------------------\n%s" % log_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the cause, citations and narrative out of a model reply, tolerantly but never
    creatively.

    A reply that does not parse yields {"cause": None, "citations": [], "narrative": None} --
    read as "this call produced no answer", never as evidence about the event."""
    empty = {"cause": None, "citations": [], "narrative": None}
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

    cause = str(obj.get("cause", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if cause not in R.CAUSE_VOCAB:
        cause = None

    citations = []
    for c in (obj.get("citations") or []):
        try:
            citations.append(int(c))
        except (TypeError, ValueError):
            continue

    narrative = obj.get("narrative")
    narrative = str(narrative) if isinstance(narrative, str) and narrative.strip() else None

    return {"cause": cause, "citations": citations, "narrative": narrative}
