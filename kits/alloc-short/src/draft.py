"""SEAM 3 -- the AI layer. Loads one session, allocates and packs its flagged events, calls the
model once, parses the reply. This is the whole AI layer of the kit, deliberately short -- same
split gap-brief's src/brief.py and data-reconcile's src/reconcile.py both make.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

from src import allocate as A          # noqa: E402
from src import pack as PACK             # noqa: E402
from src import prompt as P                # noqa: E402


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def sessions():
    return _read_jsonl(os.path.join(DATA, "sessions.jsonl"))


def sessions_by_id():
    return {s["session_id"]: s for s in sessions()}


def notes_by_id():
    return {n["session_id"]: n["notes"] for n in _read_jsonl(os.path.join(DATA, "notes.jsonl"))}


def gold_by_id():
    """The gold event list, keyed by session_id. NEVER read by draft() -- passing it anywhere
    near the prompt would be the oldest mistake in evaluation."""
    return {g["session_id"]: g for g in _read_jsonl(os.path.join(DATA, "gold.jsonl"))}


def draft(cfg, session, notes, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """One session, one call (unless `complete` is supplied -- a stub for --stub/--dry-run).

    Returns the full record: the packed flagged-event list actually sent (with every allocated
    unit already final), the parsed per-event answers, the narrative, and what the call cost.
    Events that were not flagged are never seen here -- src/allocate.py already decided that
    before this function is called.
    """
    from src.adapters import complete as real_complete
    do_complete = complete or real_complete

    flagged = A.flagged_events(session)
    packed, pack_meta = PACK.pack(session, notes, flagged)
    messages, parts = P.build(packed, prompt=prompt)
    system, user = messages[0]["content"], messages[1]["content"]
    got = do_complete(cfg, system, user, max_tokens=P.MAX_TOKENS,
                      **({"thinking": thinking} if thinking is not None else {}))
    parsed = P.parse(got.get("text", ""))

    return {
        "session_id": session["session_id"],
        "packed": packed,
        "pack_meta": pack_meta,
        "events_flagged": len(flagged),
        "events_answered": len(parsed["events"]),
        "answer": parsed,
        "parts": parts,
        "prompt": user,
        "raw_text": got.get("text", ""),
        "finish_reason": got.get("finish_reason"),
        "input_tokens": got.get("input_tokens"),
        "output_tokens": got.get("output_tokens"),
        "reasoning_tokens": (got.get("token_details") or {}).get("reasoning_tokens"),
        "model": got.get("model"),
    }
