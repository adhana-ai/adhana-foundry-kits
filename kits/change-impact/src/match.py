"""Extract the requested change from one message, match it to the record it modifies, and cost
the call. This is the whole AI layer of the kit, deliberately short -- the same split every
sibling kit's AI-layer file makes: the model does one job, and this file is small enough that you
can see exactly which one.

⚠︎ BLOCKING RUNS BEFORE THE MODEL EVER SEES THE MESSAGE. `candidates()` is pure code -- an explicit
record id, an explicit SKU code, or a substring match on the vendor's own product description. The
model is asked to choose among (or reject) whatever that step already narrowed things down to; it
never sees the whole corpus.

⚠︎ THE MODEL NEVER COMPUTES THE IMPACT. It returns a match and an extracted change; src/impact.py
turns that into a dollar figure and a date delta, deterministically, from the record already on
disk. See src/impact.py's own header for why that split exists.
"""
import json
import os

from . import adapters, block, impact as I, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as every sibling kit's MAX_TOKENS. A full
# reply is four fields (match, change_type, new_value, citation); short by the standard of
# data-match's SAME/DIFFERENT/UNSURE ceiling, which sits at 4096 because a reasoning model can
# spend the whole budget on reasoning before ever emitting the word. Set high enough that
# truncation is not the thing under measurement here either.
MAX_TOKENS = 2000


def load_vendors():
    with open(os.path.join(DATA, "vendors.json"), encoding="utf-8") as f:
        return json.load(f)


def vendors_by_id():
    return {v["id"]: v for v in load_vendors()}


def load_records():
    out = []
    with open(os.path.join(DATA, "records.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def records_by_id():
    return {r["record_id"]: r for r in load_records()}


def records_by_vendor_sku():
    out = {}
    for r in load_records():
        out.setdefault((r["vendor_id"], r["sku"]), []).append(r)
    return out


def load_messages():
    out = []
    with open(os.path.join(DATA, "messages.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold match/change/impact, keyed by message_id. NEVER read by check() — passing it
    anywhere near the prompt would be the oldest mistake in evaluation."""
    out = {}
    with open(os.path.join(DATA, "gold.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                g = json.loads(line)
                out[g["message_id"]] = g
    return out


def check(cfg, message, vendor, vsku_index, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one message: block, call, parse, compute impact, decide."""
    blocked = block.candidates(message, vendor, vsku_index)
    candidates = blocked["candidates"]

    msgs, parts = P.build(message, candidates, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    match = parsed["match"]
    computed_impact, decision = None, None
    if match and match not in ("NONE", "UNSURE"):
        rec = next((c for c in candidates if c["record_id"] == match), None)
        if rec is not None and parsed["change_type"]:
            computed_impact = I.compute(rec, parsed["change_type"], parsed["new_value"])
            decision = I.decide(computed_impact) if computed_impact is not None else "escalate"

    parsed_ok = bool((raw or "").strip()) and match is not None
    return {
        "message_id": message["message_id"], "vendor_id": message["vendor_id"],
        "candidates": [c["record_id"] for c in candidates],
        "match": match, "change_type": parsed["change_type"], "new_value": parsed["new_value"],
        "citation": parsed["citation"], "computed_impact": computed_impact, "decision": decision,
        "parsed": parsed_ok, "raw": raw, "parts": parts,
        "input_tokens": res.get("input_tokens"), "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"), "model": res.get("model"),
    }
