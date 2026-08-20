"""SEAM 2 -- Pack. Deterministic rendering of one variance event's transaction history into the
numbered lines the model actually sees. Pure code, no model -- same split gap-brief's own
src/pack.py makes between assembly and the one call that reads the assembly.

⚠︎ THE WHOLE LOG IS SENT, NEVER PRE-FILTERED. Unlike gap-brief's shared cycle-wide notes log,
this event's log is already scoped to exactly one item/location's own history -- there is nothing
to pre-select, because every line in it is a candidate. Pre-trimming to "the line that explains
it" would hand the model the answer.

⚠︎ INDICES ARE ASSIGNED HERE, ONCE, AND NEVER REORDERED. The model answers with a log line index,
`src/segment.py::line_supports_cause` checks that index against the same event object, and
`tools/build_corpus.py` writes gold citations as indices into this exact order -- so the log must
never be sorted, filtered or re-indexed anywhere else in the pipeline.
"""
MAX_LOG_LINES = 10          # the stated ceiling this corpus's 4-10 lines/event sits under


def pack(event):
    """Returns the packed dict the prompt is built from, plus how much of the stated ceiling it
    used -- so Cost can report packing as $0 and Architecture can show the seam actually ran."""
    log = event["log"][:MAX_LOG_LINES]
    packed = {
        "event_id": event["event_id"],
        "item_id": event["item_id"],
        "item_label": event["item_label"],
        "location_id": event["location_id"],
        "period": event["period"],
        "system_qty": event["system_qty"],
        "counted_qty": event["counted_qty"],
        "variance_qty": event["variance_qty"],
        "log": [
            {"idx": i, "ts": l["ts"], "type": l["type"], "note": l["note"]}
            for i, l in enumerate(log)
        ],
    }
    return packed, {
        "log_total": len(event["log"]), "log_packed": len(log),
        "truncated": len(log) < len(event["log"]),
    }
