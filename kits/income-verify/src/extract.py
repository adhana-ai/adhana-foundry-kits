"""Extract one stub's fields: segment, select, prompt, one model call, then a pure-code
qualifying-income computation downstream. This is the whole AI layer of the kit -- everything
above it (segment, select) and below it (the income arithmetic) is pure code.

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

# Kit-declared policy, not a real loan program's published guideline -- see README/SOURCES.md.
OT_CONTINUANCE_THRESHOLD = 0.75
LARGE_BONUS_THRESHOLD_USD = 1000.0


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _months_elapsed(pay_period_end):
    """Extract the month number from an ISO date string; None if it does not parse."""
    if not pay_period_end or not isinstance(pay_period_end, str):
        return None
    try:
        return int(pay_period_end.split("-")[1])
    except (IndexError, ValueError):
        return None


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold. Mirrors the corpus's own
    facet sheet guardrail: calculated qualifying income is a proposal for underwriter sign-off,
    never an auto-approval input, and the continuance thresholds are non-configurable constants,
    not a judgment call the model gets to make.

    Returns (qualifying_monthly_income, needs_review). Either input missing means that component
    contributes 0, not a fabricated estimate; a missing months_elapsed makes the whole figure
    None, since nothing can be monthly-averaged without it.
    """
    months = _months_elapsed(values.get("pay_period_end"))
    base = values.get("ytd_base_pay")
    if months is None or not isinstance(base, (int, float)) or months <= 0:
        return None, None

    monthly_base = round(base / months, 2)

    ot_pay = values.get("ytd_overtime_pay")
    ot_paid = values.get("overtime_periods_paid")
    ot_total = values.get("overtime_periods_total")
    monthly_ot = 0.0
    if (isinstance(ot_pay, (int, float)) and isinstance(ot_paid, (int, float))
            and isinstance(ot_total, (int, float)) and ot_total > 0):
        if (ot_paid / ot_total) >= OT_CONTINUANCE_THRESHOLD:
            monthly_ot = round(ot_pay / months, 2)

    bonus_pay = values.get("ytd_bonus_pay")
    recurring = values.get("bonus_recurring")
    monthly_bonus = 0.0
    needs_review = False
    if isinstance(bonus_pay, (int, float)):
        if recurring == "yes":
            monthly_bonus = round(bonus_pay / months, 2)
        elif bonus_pay >= LARGE_BONUS_THRESHOLD_USD:
            needs_review = True

    qualifying_monthly_income = round(monthly_base + monthly_ot + monthly_bonus, 2)
    return qualifying_monthly_income, needs_review


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one stub. `complete` is injectable so the eval harness, the
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
    qualifying_monthly_income, needs_review = compute(flat)

    return {
        "fields": out,
        "qualifying_monthly_income": qualifying_monthly_income,
        "needs_review": needs_review,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
