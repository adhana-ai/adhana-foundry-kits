"""Build one receiving-discrepancy case file and propose a probable liable party: load the case,
one model call, done.

This is the whole AI layer of the kit, deliberately short -- the same split data-reconcile's
reconcile.py, fin-payrun's payrun.py and fin-invval's invval.py all make: the model does one job,
and this file is small enough that you can see exactly which one.

⚠︎ THIS IS A PER-CASE RESOLVED-EVIDENCE CHECK, THE SAME SHAPE AS data-reconcile'S, NOT A
FIXED-RULEBOOK-AGAINST-MANY-DOCUMENTS CHECK LIKE docs-comply'S. Every case carries its OWN
documentary evidence -- its own PO/BOL/receiving quantities, its own carrier exception note (or
lack of one) -- and the liable party is resolved from THAT case's evidence alone. Two cases are
never compared against a shared rulebook the way docs-comply checks many documents against one
fixed set of rules; each case is its own small, self-contained evidentiary record. See
data-reconcile's reconcile.py module docstring for the fuller version of this distinction.

⚠︎ THIS KIT NEVER ISSUES A CHARGEBACK OR A CREDIT, AND IT NEVER MAKES THE FINAL LIABILITY
DETERMINATION. `check()` below returns a proposed liable party, its documentary basis and a
drafted notice for receiving/AP to review -- there is no function anywhere in this file, or in
src/app.py, that issues a chargeback, posts a credit, or records a final liability decision. Every
case still requires a named human (receiving/AP) to confirm the call before anything is issued,
exactly as the guardrail states, and that boundary is non-configurable -- there is no flag anywhere
in this kit that turns it off.

⚠︎ THE OPEN ASSUMPTION THIS KIT DOES NOT SOLVE. Every case assumes its documentary evidence (BOL,
receiving scan, carrier exception) is complete -- a document a real deployment failed to capture
looks, to this kit, identical to a document that was never generated. A missing document weakens
the liability call in a way this kit has no way to notice. It also applies ONE fixed
liability-attribution rule to every case; a real vendor/carrier relationship's actual agreement
terms can vary case by case, and this kit does not attempt to look one up. See data/SOURCES.md.
"""
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(HERE, "data", "cases.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ SIZED GENEROUSLY FROM THE START, NOT TIGHTENED FROM A STUB/BASELINE NUMBER -- same discipline
# every sibling kit's MAX_TOKENS states tonight. Neither the stub nor the free baseline exercises
# real provider-side reasoning-token consumption, which is what actually blew the ceiling on an
# earlier kit tonight; oversizing here costs nothing but ceiling headroom, and only a live run's
# finish_reason and reasoning_tokens can say whether it was needed.
MAX_TOKENS = 3000


def cases():
    import json
    out = []
    with open(CASES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold determinations, keyed by case_id. NEVER read by check() -- passing them anywhere
    near the prompt would be the oldest mistake in evaluation."""
    import json
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["case_id"]] = r
    return rows


def check(cfg, case, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one case: the proposed liable party, its documentary basis, the
    drafted notice, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the same code
    path.
    """
    msgs, parts = P.build(case, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    parsed_ok = bool((raw or "").strip()) and parsed["liable_party"] is not None
    return {
        "case_id": case["case_id"],
        "liable_party": parsed["liable_party"],
        "discrepant_sku": parsed["discrepant_sku"],
        "doc_a": parsed["doc_a"], "doc_b": parsed["doc_b"],
        "qty_a": parsed["qty_a"], "qty_b": parsed["qty_b"],
        "delta": parsed["delta"],
        "notice_text": parsed["notice_text"],
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
