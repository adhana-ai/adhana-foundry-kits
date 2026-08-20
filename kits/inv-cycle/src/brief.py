"""SEAM 3 -- the AI layer. Loads one variance event, packs its transaction log, calls the model
once, parses the reply. This is the whole AI layer of the kit, deliberately short -- same split
gap-brief's src/brief.py and param-drift's src/triage.py both make.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

from src import pack as PACK              # noqa: E402
from src import prompt as P                 # noqa: E402


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def events():
    return _read_jsonl(os.path.join(DATA, "events.jsonl"))


def events_by_id():
    return {e["event_id"]: e for e in events()}


def gold_by_id():
    """The gold cause + citations, keyed by event_id. NEVER read by draft() -- passing it
    anywhere near the prompt would be the oldest mistake in evaluation."""
    return {g["event_id"]: g for g in _read_jsonl(os.path.join(DATA, "gold.jsonl"))}


def draft(cfg, event, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """One event, one call (unless `complete` is supplied -- a stub for --stub/--dry-run).

    Returns the full record: the packed log actually sent, the parsed cause/citations/narrative,
    and what the call cost. Gold is never seen here -- it is read only by evals/scoring.py.
    """
    from src.adapters import complete as real_complete
    do_complete = complete or real_complete

    packed, pack_meta = PACK.pack(event)
    messages, parts = P.build(packed, prompt=prompt)
    system, user = messages[0]["content"], messages[1]["content"]
    got = do_complete(cfg, system, user, max_tokens=P.MAX_TOKENS,
                      **({"thinking": thinking} if thinking is not None else {}))
    parsed = P.parse(got.get("text", ""))

    return {
        "event_id": event["event_id"],
        "packed": packed,
        "pack_meta": pack_meta,
        "answer": parsed,
        "replied": parsed["cause"] is not None,
        "parts": parts,
        "prompt": user,
        "raw_text": got.get("text", ""),
        "finish_reason": got.get("finish_reason"),
        "input_tokens": got.get("input_tokens"),
        "output_tokens": got.get("output_tokens"),
        "reasoning_tokens": (got.get("token_details") or {}).get("reasoning_tokens"),
        "model": got.get("model"),
    }
