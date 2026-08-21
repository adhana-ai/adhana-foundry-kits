"""Extract one break record's fields: segment, select, prompt, one model call, then a pure-code
review-routing computation downstream. This is the whole AI layer of the kit -- everything above
it (segment, select) and below it (the routing decision) is pure code.

MAX_TOKENS -- a ten-field JSON record; the sibling extraction kits in this series needed 3000-4000
for the same shape of task. Set here on that evidence rather than guessed at from zero.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 4000

# Kit-declared policy, not a real firm's documented SLA -- see README/SOURCES.md.
AGING_THRESHOLD_DAYS = 3


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold. Mirrors this kit's own
    facet sheet guardrail: no adjusting entry posts without the named operations supervisor's
    approval -- the routing decision is a fixed, non-configurable rule, never a judgment call
    the model gets to make on top of its own classification.

    Returns (needs_review, break_quantity). needs_review is True only when BOTH the model
    classified the break as true AND the stated age exceeds AGING_THRESHOLD_DAYS. Returns
    (None, None) when the inputs needed to compute at all are missing.
    """
    is_true = values.get("is_true_break")
    age = values.get("break_age_days")
    internal = values.get("internal_quantity")
    custodian = values.get("custodian_quantity")

    break_quantity = None
    if isinstance(internal, (int, float)) and isinstance(custodian, (int, float)):
        break_quantity = round(custodian - internal, 4)

    if is_true not in ("yes", "no") or not isinstance(age, (int, float)):
        return None, break_quantity

    needs_review = (is_true == "yes") and (age > AGING_THRESHOLD_DAYS)
    return needs_review, break_quantity


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one break. `complete` is injectable so the eval harness, the
    app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    parsed_ok = bool(values) and any(v is not None for v in values.values())

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):
            v = None
        spannable = f.get("type") != "enum"
        span = segment.locate(doc_text, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review, break_quantity = compute(flat)

    return {
        "fields": out,
        "needs_review": needs_review,
        "break_quantity": break_quantity,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
