"""Reconcile one draft order against its supplier's agreement: load both, one model call, check
the citations, done.

This is the whole AI layer of the kit, deliberately short — the same split docs-comply's comply.py,
docs-redact's detect.py and docs-verify's verify.py all make: the model does one job, and this file
is small enough that you can see exactly which one.

⚠︎ THIS IS A TWO-SOURCE CHECK, NOT A ONE-DOCUMENT-AGAINST-A-FIXED-RULEBOOK CHECK, which is why it
needed its own shape rather than reusing docs-comply's flow node-for-node:

  · docs-comply runs a FIXED rulebook -> many documents. Every document is checked against the
    same rules.
  · This kit runs one draft order -> its OWN governing agreement, resolved per order by
    supplier_id. Two orders from two suppliers are checked against two different agreements, and
    an order can reference a SKU or a field its own supplier's agreement never states — the
    unverifiable verdict this kit exists to get right.

The cost of that shape is stated on the page rather than hidden: nothing here is cached across
orders from the same supplier, so re-checking ten orders against one supplier sends that supplier's
agreement text ten times. See Cost.cost_drivers once a run has priced it.
"""
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGREEMENTS = os.path.join(HERE, "data", "agreements")
ORDERS = os.path.join(HERE, "data", "orders.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as every sibling kit's MAX_TOKENS. A full
# reply is five checks, each with a verdict, a citation and two values: short by the standard of
# docs-comply's 41-rule reply, so this starts well under it. A guess, not a measurement, until a
# real run's finish_reason says otherwise.
MAX_TOKENS = 1500


def load_agreement(supplier_id):
    with open(os.path.join(AGREEMENTS, "%s.txt" % supplier_id), encoding="utf-8") as f:
        return f.read()


def orders():
    import json
    out = []
    with open(ORDERS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold verdicts, keyed by order_id. NEVER read by check() — passing them anywhere near
    the prompt would be the oldest mistake in evaluation."""
    import json
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["order_id"]] = r
    return rows


def _citation_is_real(citation, agreement_text):
    """Is the model's cited clause actually in the agreement, or did it write one? Pure code, so
    it costs nothing per run. Whitespace is normalised so a model reflowing a line it copied
    correctly is not scored as a fabrication."""
    if not citation:
        return None
    norm = " ".join(citation.split()).lower()
    hay = " ".join(agreement_text.split()).lower()
    return norm in hay


def check(cfg, order, agreement_text, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one order: a verdict per check, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the same code
    path.
    """
    msgs, parts = P.build(order, agreement_text, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    rows = []
    for c in P.CHECKS:
        got = parsed[c]
        citation = (got or {}).get("citation", "")
        rows.append({
            "check": c,
            "verdict": (got or {}).get("verdict"),          # None = never answered
            "citation": citation,
            "expected": (got or {}).get("expected"),
            "actual": (got or {}).get("actual"),
            "citation_in_agreement": _citation_is_real(citation, agreement_text),
        })

    answered = sum(1 for r in rows if r["verdict"] is not None)
    parsed_ok = bool((raw or "").strip()) and answered > 0
    return {
        "order_id": order["order_id"],
        "supplier_id": order["supplier_id"],
        "checks": rows,
        "answered": answered,
        "asked": len(P.CHECKS),
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


def summary(record):
    """The four numbers the app panel shows, computed in one place. clean + defect + unverifiable
    + no_verdict == checked, always — the same identity docs-comply's summary() asserts, for the
    same reason: folding a silent model's non-answers into any one verdict would award it a score
    it did not earn."""
    rows = record["checks"]
    out = {"checked": len(rows), "clean": 0, "defect": 0, "unverifiable": 0, "no_verdict": 0}
    for r in rows:
        if r["verdict"] is None:
            out["no_verdict"] += 1
        else:
            out[r["verdict"]] += 1
    assert out["clean"] + out["defect"] + out["unverifiable"] + out["no_verdict"] == out["checked"]
    return out
