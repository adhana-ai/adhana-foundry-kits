"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `bonus_recurring` HERE IS A DELIBERATE KEYWORD FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It marks a bonus recurring whenever its history note contains one of a fixed list of
words ("annual", "recurring", "each year", "quarterly", "consistently") -- exactly the
keyword-only shortcut the prompt's guardrail exists to forbid a model from taking. It will call
"Annual performance bonus" (no payment history stated) recurring, and it will miss "Bonus paid in
both the 2024 and 2025 performance cycles" (a real two-year history, no keyword) entirely. The gap
between this baseline and a model that actually reads for a stated history is the demonstration
this kit exists to run -- see data/SOURCES.md.
"""
import re

from src.extract import compute as _compute

RECURRING_KEYWORDS = ("annual", "recurring", "each year", "quarterly", "consistently")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _num(s):
    if s is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", ""))
    return float(m.group(0)) if m else None


def extract_one(text, fields):
    name = _section(text, "Employee")
    employer = _section(text, "Employer")
    freq = _section(text, "Pay Frequency")
    period_end = _section(text, "Pay Period End")

    m = re.search(r"Base pay YTD:\s*\$([\d,.]+)", text)
    ytd_base = _num(m.group(1)) if m else None

    ytd_ot = ot_paid = ot_total = None
    m = re.search(r"Overtime pay YTD:\s*\$([\d,.]+)\s*\(paid in (\d+) of (\d+) pay periods",
                  text)
    if m:
        ytd_ot, ot_paid, ot_total = _num(m.group(1)), int(m.group(2)), int(m.group(3))

    ytd_bonus = bonus_recurring = None
    m = re.search(r"Bonus pay YTD:\s*\$([\d,.]+)", text)
    if m:
        ytd_bonus = _num(m.group(1))
        history = _section(text, "Bonus History") or ""
        low = history.lower()
        bonus_recurring = "yes" if any(k in low for k in RECURRING_KEYWORDS) else "no"

    values = {
        "employee_name": name, "employer_name": employer, "pay_frequency": freq,
        "pay_period_end": period_end, "ytd_base_pay": ytd_base, "ytd_overtime_pay": ytd_ot,
        "overtime_periods_paid": ot_paid, "overtime_periods_total": ot_total,
        "ytd_bonus_pay": ytd_bonus, "bonus_recurring": bonus_recurring,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    income, needs_review = _compute(values)
    return {"fields": out, "qualifying_monthly_income": income, "needs_review": needs_review,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
