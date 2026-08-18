"""Match one new-item setup request against its blocked candidates, decide the like-item set, and
draft the starting forecast. This is the whole AI layer of the kit, deliberately short -- the
model does one job (per-candidate LIKE_ITEM / NOT_LIKE_ITEM / UNSURE), and everything downstream
of that is pure code in src/decide.py and src/forecast.py.
"""
import json
import os

from . import adapters, block, decide as D, forecast as F, prompt as P, similarity as SIM

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")


def load_history():
    out = []
    with open(os.path.join(DATA, "history.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def history_by_id():
    return {h["item_id"]: h for h in load_history()}


def load_requests():
    out = []
    with open(os.path.join(DATA, "requests.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """Pairwise gold, keyed by (request_id, item_id) -> 'like_item' | 'not_like_item'. NEVER read
    by check() -- passing it anywhere near the prompt would be the oldest mistake in evaluation."""
    out = {}
    with open(os.path.join(DATA, "gold.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                g = json.loads(line)
                out[(g["request_id"], g["item_id"])] = g["label"]
    return out


def check(cfg, request, history, complete=None, thinking=None):
    """Return the full record for one request: block, one call, parse, decide, draft the
    forecast."""
    candidates = block.candidates(request, history)
    cand_ids = [c["item_id"] for c in candidates]

    msgs, parts = P.build(request, candidates)
    call = complete or adapters.complete
    kw = {"max_tokens": P.MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    verdicts, reasons = P.parse(raw, cand_ids)

    per_candidate = []
    like_items = []
    for c in candidates:
        v = verdicts.get(c["item_id"])
        sim = SIM.score(request, c)
        merged = D.counts_as_like_item(sim, verdict=v) if v is not None else D.counts_as_like_item(sim)
        row = {"item_id": c["item_id"], "verdict": v, "reason": reasons.get(c["item_id"]),
               "similarity_score": sim, "counted": merged}
        per_candidate.append(row)
        if merged:
            like_items.append(c)

    draft = F.draft(like_items)
    parsed_ok = bool((raw or "").strip()) and any(v is not None for v in verdicts.values())

    return {
        "request_id": request["request_id"], "category": request["category"],
        "candidates": cand_ids, "per_candidate": per_candidate,
        "like_item_ids": [e["item_id"] for e in like_items], "draft": draft,
        "parsed": parsed_ok, "raw": raw, "parts": parts,
        "input_tokens": res.get("input_tokens"), "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"), "model": res.get("model"),
    }
