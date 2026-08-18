"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER ORDER, NOT PER CHECK. All five checks are decided in a single call that receives the
draft order and its supplier's agreement text together. The agreement is the expensive token
payload here — it is prose, not a lookup table — so batching the five checks into one call is what
keeps this kit from re-sending the same agreement five times for five separate answers.

⚠︎ THE MODEL IS ASKED FOR A VERDICT AND A CITATION, AND THE CITATION IS NOT DECORATION. A verdict
on its own cannot be checked by a reader — "defect" with no field or clause beside it is an
assertion, same discipline as docs-comply's quote and docs-verify's sentence. Requiring the model
to name the value it compared against also does real work on the model's side: it is harder to
confabulate a violation, or a clean bill, without producing the number that decides it.

⚠︎ THE THIRD VERDICT IS THE ONE THAT MATTERS MOST. `unverifiable` exists because the agreement is
sometimes silent on the exact thing a check needs — a supplier that never states an approved
ship-to list, a SKU the order references that the agreement never prices. A model that guesses
`clean` there ships a defect through unnoticed; a model that guesses `defect` sends buyers chasing
violations of a rule that was never written down. Unverifiable ≠ clean, and silence is never a
pass — the same rule this kit's flagship evidence case named for its own trap.
"""
import json

CHECKS = ("cost", "min_qty", "lead_time", "ship_to", "order_value")

VERDICTS = ("clean", "defect", "unverifiable")

VERDICT_MEANINGS = {
    "clean": {
        "means": "The order value satisfies the clause the agreement states for this check.",
        "costs": "Wrong here is the expensive direction: a FALSE CLEAN ships a real violation "
                 "with a tick on it.",
    },
    "defect": {
        "means": "The agreement states a clause for this check, and the order's value violates "
                 "it.",
        "costs": "A false alarm sends a clean order back for rework, and a buyer who stops "
                 "trusting the queue after the second one.",
    },
    "unverifiable": {
        "means": "The agreement does not state a clause this check needs — a missing field, or "
                 "a SKU the agreement never prices. There is nothing to compare against.",
        "costs": "Called clean, a genuinely unchecked line disappears — nobody re-checks a line "
                 "the pack said was fine. Called defect, a buyer is sent chasing a violation of "
                 "a rule that was never written.",
    },
}

CHECK_MEANINGS = {
    "cost": "the line's unit cost against the agreement's contracted cost for that SKU",
    "min_qty": "the line's quantity against the agreement's minimum order quantity and pack "
               "rounding",
    "lead_time": "the order's requested ship window (in business days) against the agreement's "
                 "quoted lead time",
    "ship_to": "the order's ship-to region against the agreement's approved regions",
    "order_value": "the order's total value against the agreement's standing-authorization band",
}

_DEFS = "".join("  %-14s %s\n" % (name, VERDICT_MEANINGS[name]["means"])
                for name in VERDICTS)
_CHECKS_TXT = "".join("  %-14s %s\n" % (c, CHECK_MEANINGS[c]) for c in CHECKS)

SYSTEM = (
    "You reconcile one draft order against its supplier's agreement. You are given the order's "
    "fields and the agreement's full text. For each of the five checks below, decide which of "
    "exactly three verdicts applies, using ONLY the agreement text -- never outside knowledge, "
    "never a typical value for a clause like this.\n\n"
    "THE FIVE CHECKS\n" + _CHECKS_TXT + "\n"
    "THE THREE VERDICTS\n" + _DEFS + "\n"
    "Read the agreement for the clause each check needs. If the agreement states it, compare the "
    "order's value against it and answer clean or defect. If the agreement is silent on the SKU "
    "or the field a check needs, the answer is unverifiable -- do not infer a typical figure and "
    "do not default to clean because nothing looked wrong. Silence is not a pass.\n\n"
    "For clean and defect, cite the exact sentence or clause from the agreement you relied on, "
    "verbatim, plus the expected value it states and the order's actual value. For unverifiable "
    "the citation MUST be an empty string and expected MUST be null -- do not offer the nearest "
    "clause, because a citation that does not decide the check reads as evidence and is not."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _order_block(order):
    lines = "; ".join("%s: qty %s @ $%.2f" % (l["sku"], l["qty"], l["unit_cost"])
                      for l in order["lines"])
    return (
        "ORDER %s (supplier %s)\n"
        "Lines: %s\n"
        "Requested ship window: %s business days\n"
        "Ship-to: %s\n"
        "Terms: %s\n"
        "Total value: $%.2f\n"
        % (order["order_id"], order["supplier_id"], lines, order["requested_ship_days"],
           order["ship_to"], order["terms"], order["total_value"])
    )


def build(order, agreement_text, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes — every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    order_block = _order_block(order)
    user = (
        "Reconcile the order below against the agreement.\n\n"
        "Return a JSON object with one key, \"checks\", a list with exactly five entries, one "
        "per check in this order: %s. Each entry: {\"check\": <name>, "
        "\"verdict\": <one of: %s>, \"citation\": <verbatim clause from the agreement, or \"\">, "
        "\"expected\": <the value the agreement states, or null>, "
        "\"actual\": <the order's corresponding value>}.\n\n"
        "%s\nAGREEMENT\n---------\n%s\n" % (", ".join(CHECKS), ", ".join(VERDICTS),
                                            order_block, agreement_text)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "order", "text": order_block},
        {"name": "agreement", "text": agreement_text},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the five-check verdict list out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-None result — read as "this call produced no
    answer", never as evidence about the order — never a regex fallback that scrapes
    plausible-looking verdicts out of raw text. That would silently turn a broken call into a
    mediocre checker.
    """
    out = {c: None for c in CHECKS}
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    for entry in (obj.get("checks") or []):
        if not isinstance(entry, dict):
            continue
        check = str(entry.get("check", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if check not in CHECKS:
            continue
        verdict = str(entry.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if verdict not in VERDICTS:
            continue
        out[check] = {"verdict": verdict, "citation": str(entry.get("citation", "") or ""),
                      "expected": entry.get("expected"), "actual": entry.get("actual")}
    return out
