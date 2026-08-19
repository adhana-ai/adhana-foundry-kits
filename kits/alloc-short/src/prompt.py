"""Assemble the one prompt this kit sends per session, and parse the one reply it gets back.

ONE CALL PER SESSION, NOT PER EVENT. All of a session's flagged events are decided in a single
call that receives the packed event list and the session's notes log together -- the notes log
is the shared, expensive payload; batching every event in the session into one call is what
keeps this kit from re-sending the same notes once per event. Same discipline gap-brief's
src/prompt.py states for its own cycles.

⚠︎ NO FIELD IN THIS SCHEMA CAN CHANGE AN ALLOCATED UNIT. This is a decision-free kit by the atlas
row's own guardrail: every number in every event was already computed by src/allocate.py before
this prompt is even built. The model tags a probable cause and drafts a narrative describing the
split it was handed -- it never proposes a different number and there is no field to put one in.

⚠︎ 'unknown' IS SAFE TO SAY, AND SAYING SOMETHING ELSE WITHOUT REAL SUPPORT IS THE FAILURE MODE
THIS KIT MEASURES. The system prompt states this twice, because a model asked for a 'no idea'
answer only some of the time defaults toward looking useful over being honest, and
evals/scoring.py's fabrication guardrail is built to catch exactly that.
"""
import json

from . import rubric as R

# ⚑ RAISED FROM 2200 AFTER READING debug1's OWN RESULT, NOT BEFORE -- same discipline
# change-impact's src/adapters raised its own cap only after a real run reported finish_reason
# 'length'. A session can batch up to 6 flagged events, each carrying two citation sentences
# noticeably longer than gap-brief's own notes lines (a SKU name plus a specific unit count),
# and 2200 truncated a real reply mid-JSON on the very first live call: finish_reason='length' at
# exactly 2200/2200 tokens, no closing brace, unparseable. 3600 gives six full event entries plus
# a 3-6 sentence narrative comfortable headroom without inviting a reasoning pass nobody asked for.
MAX_TOKENS = 3600

_CAUSES_TXT = "".join("  %-22s %s\n" % (c, R.CAUSE_MEANINGS[c]) for c in R.CAUSE_VOCAB)

SYSTEM = (
    "You are drafting the allocation review brief for a supply-constrained-events review meeting. "
    "You are given one week's FLAGGED shortage events for a region -- SKUs where the written "
    "allocation policy (protect promo commitments, protect customer commitments, then fair-share "
    "the rest by trailing velocity, then check a 40% equity floor per store) could not be fully "
    "honored, already identified and split by code -- and that week's own merchant notes log.\n\n"
    "The per-store unit counts you are given (allocated_units, ask_units, available_units) are "
    "FINAL. You never propose a different number for any store. Your job is limited to two "
    "things, for EACH flagged event in the list:\n\n"
    "1. Decide which of these five causes explains why this event could not be cleanly resolved, "
    "using ONLY the notes log -- never outside knowledge, never a plausible-sounding guess:\n\n"
    + _CAUSES_TXT + "\n"
    "If the notes log supports a specific cause for that event's SKU, name it and cite the exact "
    "two notes lines (verbatim) that together support it. If the notes log does NOT support a "
    "specific cause for that SKU -- no line mentions it, or the lines that do mention it don't "
    "add up to one of the four named causes -- the cause is 'unknown' and both citation fields "
    "must be empty strings. Do not cite a line that does not actually name or clearly concern "
    "that SKU just because it is the closest-sounding one available: an unsupported 'unknown' is "
    "the correct, honest answer and is graded as such; a cause with a citation that is not really "
    "about that SKU is graded as a fabrication, which is worse.\n\n"
    "2. State which protections held: echo back promo_protected and customer_protected exactly "
    "as given in the input for that event (true or false), and whether any store is at or below "
    "the equity floor (floor_breach_stores is non-empty in the input).\n\n"
    "After the per-event entries, write a short narrative (3-6 sentences) for the meeting "
    "audience that ties the flagged events together. Every number you state in the narrative -- a "
    "unit count, a store count, a percentage -- must be a number that is actually present in the "
    "event list you were given; do not compute, round, or restate a figure that changes its "
    "value.\n\n"
    "NEVER propose a different allocation for any store, and never rank or recommend which event "
    "should be resolved first. That decision belongs to the humans in the meeting this brief is "
    "for -- your job is limited to itemizing, tagging a probable cause (or saying unknown), and "
    "describing what happened, never what should be done about it."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _event_block(packed):
    lines = []
    for e in packed["events"]:
        stores_txt = ", ".join(
            "%s: ask=%d alloc=%d" % (p["store_id"], p["ask_units"], p["allocated_units"])
            for p in e["per_store"]
        )
        lines.append(
            "- %s (%s): available=%d total_ask=%d | promo_protected=%s customer_protected=%s | "
            "floor_breach_stores=%s | %s"
            % (e["event_id"], e["sku"], e["available_units"], e["total_ask"],
               e["promo_protected"], e["customer_protected"],
               e["floor_breach_stores"] or "[]", stores_txt)
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
    header = "Session %s -- %s, %s\n" % (packed["session_id"], packed["region"], packed["week"])
    event_block = _event_block(packed)
    notes_block = _notes_block(packed)
    n_events = len(packed["events"])
    user = (
        header +
        "\nFLAGGED EVENTS (%d)\n--------------------\n%s\n\n"
        "MERCHANT NOTES LOG\n-------------------\n%s\n\n"
        "Return a JSON object with two keys: \"events\", a list with exactly %d entries, one per "
        "event above in the same order, each {\"event_id\": <id>, \"cause\": <one of: %s>, "
        "\"citation_1\": <verbatim notes line, or \"\">, \"citation_2\": <verbatim notes line, or "
        "\"\">, \"promo_protected\": <true or false>, \"customer_protected\": <true or false>, "
        "\"note\": <one sentence>}; and \"narrative\", a string of 3-6 sentences.\n"
        "Answer with the JSON object only." % (n_events, event_block, notes_block, n_events,
                                               ", ".join(R.CAUSE_VOCAB))
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "events", "text": header + "\nFLAGGED EVENTS (%d)\n--------------------\n%s"
                                   % (n_events, event_block)},
        {"name": "notes", "text": "MERCHANT NOTES LOG\n-------------------\n%s" % notes_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the event list and narrative out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields {"events": [], "narrative": None} -- read as "this call
    produced no answer", never as evidence about the session."""
    empty = {"events": [], "narrative": None}
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
    events = []
    for entry in (obj.get("events") or []):
        if not isinstance(entry, dict):
            continue
        event_id = str(entry.get("event_id", "")).strip()
        if not event_id:
            continue
        cause = str(entry.get("cause", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if cause not in R.CAUSE_VOCAB:
            cause = None
        pp, cp = entry.get("promo_protected"), entry.get("customer_protected")
        events.append({
            "event_id": event_id, "cause": cause,
            "citation_1": str(entry.get("citation_1", "") or ""),
            "citation_2": str(entry.get("citation_2", "") or ""),
            "promo_protected": bool(pp) if isinstance(pp, bool) else None,
            "customer_protected": bool(cp) if isinstance(cp, bool) else None,
            "note": str(entry.get("note", "") or ""),
        })
    narrative = obj.get("narrative")
    narrative = str(narrative) if isinstance(narrative, str) and narrative.strip() else None
    return {"events": events, "narrative": narrative}
