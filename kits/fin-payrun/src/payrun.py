"""Trace one invoice through match, approval, run inclusion and remittance, and draft a reply to
the vendor's payment-status inquiry: load the record, one model call, done.

This is the whole AI layer of the kit, deliberately short -- the same split fin-close's close.py,
docs-comply's comply.py and docs-verify's verify.py all make: the model does one job, and this file
is small enough that you can see exactly which one.

⚠︎ THIS KIT NEVER RELEASES A PAYMENT, CHANGES A REMITTANCE DETAIL, OR COMMITS TO A DATE BEYOND THE
SCHEDULED RUN. `check()` below returns a traced stage, a review flag and a drafted reply and
nothing else -- there is no function anywhere in this file, or in src/app.py, that writes a payment
as released or a remittance detail as changed. Every reply with an open exception still requires a
named AP reviewer before it goes to the vendor, exactly as the guardrail states. See the module
docstring in src/prompt.py for where that boundary is worded to the model itself.

⚠︎ THE OPEN ASSUMPTION THIS KIT DOES NOT SOLVE. This kit assumes match, approval and run-inclusion
status all live in systems it can query directly -- every field on every invoice below is always
present, whatever its state. A manually tracked approval step (an email sign-off that never made it
into the approval system) has no trace to follow, and this kit has no way to notice that the trail
it is reading is incomplete rather than merely unfavourable. See data/SOURCES.md.
"""
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVOICES = os.path.join(HERE, "data", "invoices.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ SIZED GENEROUSLY FROM THE START, NOT GUESSED LOW -- same discipline every sibling kit's
# MAX_TOKENS states, learned the hard way on an earlier kit tonight: a reply shape this small (a
# five-way classification, a boolean, a short date, a one-or-two-sentence reply) still ran into a
# ceiling on a real provider because provider-side reasoning ate most of the budget before the JSON
# answer even started. This is a safety margin, not a computed number -- only a live run's
# finish_reason and reasoning_tokens can say whether it was needed, and only the operator can fire
# that run.
MAX_TOKENS = 3000


def invoices():
    import json
    out = []
    with open(INVOICES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold verdicts, keyed by invoice_id. NEVER read by check() -- passing them anywhere near
    the prompt would be the oldest mistake in evaluation."""
    import json
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["invoice_id"]] = r
    return rows


def check(cfg, inv, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one vendor inquiry: the traced stage, the review flag, the
    stated date, the drafted reply, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the same code
    path.
    """
    msgs, parts = P.build(inv, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    parsed_ok = bool((raw or "").strip()) and parsed["current_stage"] is not None
    return {
        "invoice_id": inv["invoice_id"],
        "current_stage": parsed["current_stage"],
        "requires_ap_review": parsed["requires_ap_review"],
        "stated_date": parsed["stated_date"],
        "reply": parsed["reply"],
        "parsed": parsed_ok,
        "raw": raw,
        "parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"),
        "model": res.get("model"),
    }
