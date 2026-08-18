"""SEAM 3 -- the AI layer. Loads one review batch, segments and packs its material exceptions,
calls the model once, parses the reply. This is the whole AI layer of the kit, deliberately short
-- same split gap-brief's src/brief.py and param-drift's src/triage.py both make.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

from src import segment as SEG          # noqa: E402
from src import pack as PACK              # noqa: E402
from src import prompt as P                # noqa: E402


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def batches():
    return _read_jsonl(os.path.join(DATA, "batches.jsonl"))


def batches_by_id():
    return {b["batch_id"]: b for b in batches()}


def notes_by_id():
    return {n["batch_id"]: n["notes"] for n in _read_jsonl(os.path.join(DATA, "notes.jsonl"))}


def gold_by_id():
    """The gold exception list, keyed by batch_id. NEVER read by draft() -- passing it anywhere
    near the prompt would be the oldest mistake in evaluation."""
    return {g["batch_id"]: g for g in _read_jsonl(os.path.join(DATA, "gold.jsonl"))}


def draft(cfg, batch, notes, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """One review batch, one call (unless `complete` is supplied -- a stub for --stub/--dry-run).

    Returns the full record: the packed material-exception list actually sent, the parsed per-item
    answers, the narrative, and what the call cost. Items that were not material are never seen
    here -- src/segment.py already decided that before this function is called.
    """
    from src.adapters import complete as real_complete
    do_complete = complete or real_complete

    exceptions = SEG.material_exceptions(batch)
    packed, pack_meta = PACK.pack(batch, notes, exceptions)
    messages, parts = P.build(packed, prompt=prompt)
    system, user = messages[0]["content"], messages[1]["content"]
    got = do_complete(cfg, system, user, max_tokens=P.MAX_TOKENS,
                      **({"thinking": thinking} if thinking is not None else {}))
    parsed = P.parse(got.get("text", ""))

    return {
        "batch_id": batch["batch_id"],
        "packed": packed,
        "pack_meta": pack_meta,
        "items_material": len(exceptions),
        "items_answered": len(parsed["items"]),
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
