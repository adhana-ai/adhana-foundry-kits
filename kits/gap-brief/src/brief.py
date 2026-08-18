"""SEAM 3 -- the AI layer. Loads one cycle, segments and packs its material gaps, calls the model
once, parses the reply. This is the whole AI layer of the kit, deliberately short -- same split
param-drift's src/triage.py and data-reconcile's src/reconcile.py both make.
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


def cycles():
    return _read_jsonl(os.path.join(DATA, "cycles.jsonl"))


def cycles_by_id():
    return {c["cycle_id"]: c for c in cycles()}


def notes_by_id():
    return {n["cycle_id"]: n["notes"] for n in _read_jsonl(os.path.join(DATA, "notes.jsonl"))}


def gold_by_id():
    """The gold gap list, keyed by cycle_id. NEVER read by draft() -- passing it anywhere near
    the prompt would be the oldest mistake in evaluation."""
    return {g["cycle_id"]: g for g in _read_jsonl(os.path.join(DATA, "gold.jsonl"))}


def draft(cfg, cycle, notes, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """One cycle, one call (unless `complete` is supplied -- a stub for --stub/--dry-run).

    Returns the full record: the packed material-gap list actually sent, the parsed per-gap
    answers, the narrative, and what the call cost. Gaps that were not material are never seen
    here -- src/segment.py already decided that before this function is called.
    """
    from src.adapters import complete as real_complete
    do_complete = complete or real_complete

    gaps = SEG.material_gaps(cycle)
    packed, pack_meta = PACK.pack(cycle, notes, gaps)
    messages, parts = P.build(packed, prompt=prompt)
    system, user = messages[0]["content"], messages[1]["content"]
    got = do_complete(cfg, system, user, max_tokens=P.MAX_TOKENS,
                      **({"thinking": thinking} if thinking is not None else {}))
    parsed = P.parse(got.get("text", ""))

    return {
        "cycle_id": cycle["cycle_id"],
        "packed": packed,
        "pack_meta": pack_meta,
        "gaps_material": len(gaps),
        "gaps_answered": len(parsed["gaps"]),
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
