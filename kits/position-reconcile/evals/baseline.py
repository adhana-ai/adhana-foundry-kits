"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `is_true_break` HERE IS A DELIBERATE KEYWORD-REGISTER FLOOR, WRITTEN TO FAIL THE PLANTED
AMBIGUITY BY CONSTRUCTION. It marks a break explainable whenever the memo contains one of a fixed
list of benign-sounding words ("pending", "settlement", "corporate action", "dividend",
"timing") -- exactly the shortcut the prompt's guardrail exists to forbid a model from taking. It
will call a genuine break explainable because its stale memo still says "pending settlement," and
will call a fully-resolved item a true break because it opens with "URGENT" or "mismatch flagged."
The gap between this baseline and a model that reads the whole memo for what actually happened is
the demonstration this kit exists to run -- see data/SOURCES.md.
"""
import re

from src.extract import compute as _compute

BENIGN_KEYWORDS = ("pending", "settlement", "corporate action", "dividend", "timing")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _num(s):
    if s is None:
        return None
    m = re.search(r"-?\d+", s.replace(",", ""))
    return int(m.group(0)) if m else None


def extract_one(text, fields):
    account_id = _section(text, "Account")
    security = _section(text, "Security") or ""
    security_id = security_name = None
    if "--" in security:
        security_id, security_name = [p.strip() for p in security.split("--", 1)]
    as_of_date = _section(text, "As Of Date")
    internal_qty = _num(_section(text, "Internal Quantity"))
    custodian_qty = _num(_section(text, "Custodian Quantity"))
    break_age = _num(_section(text, "Break Age (Business Days)"))
    analyst = _section(text, "Assigned Analyst")
    memo = _section(text, "Reconciling Memo")

    low = (memo or "").lower()
    is_true = "no" if any(k in low for k in BENIGN_KEYWORDS) else "yes"

    values = {
        "account_id": account_id, "security_id": security_id, "security_name": security_name,
        "as_of_date": as_of_date, "internal_quantity": internal_qty,
        "custodian_quantity": custodian_qty, "break_age_days": break_age,
        "assigned_analyst": analyst, "reconciling_memo": memo, "is_true_break": is_true,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    needs_review, break_quantity = _compute(values)
    return {"fields": out, "needs_review": needs_review, "break_quantity": break_quantity,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
