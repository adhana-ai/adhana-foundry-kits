"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `deposit_documented` HERE IS A DELIBERATE KEYWORD FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY
BY CONSTRUCTION. It marks a deposit documented whenever its description CONTAINS one of a fixed
list of words ("payroll", "direct deposit", "irs", "ssa", "social security", "pension", "wire
transfer") -- exactly the keyword-only shortcut the prompt's guardrail exists to forbid a model
from taking. It will call "Payroll Deposit" (no employer named) documented, and it will miss
"ACH CREDIT ACME LOGISTICS INC" (a real employer, no keyword) entirely. The gap between this
baseline and a model that actually reads the counterparty is the demonstration this kit exists to
run -- see data/SOURCES.md.
"""
import re

from src.extract import compute as _compute

DOC_KEYWORDS = ("payroll", "direct deposit", "irs", "ssa", "social security", "pension",
                 "wire transfer")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _num(s):
    if s is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", ""))
    return float(m.group(0)) if m else None


def extract_one(text, fields):
    holder = _section(text, "Statement Holder")
    institution = _section(text, "Institution")
    account_type = _section(text, "Account Type")
    period = _section(text, "Statement Period") or ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", period)
    period_start, period_end = (m.group(1), m.group(2)) if m else (None, None)

    beginning = _num(re.search(r"Beginning Balance:\s*\$([\d,.]+)", text).group(1)) \
        if re.search(r"Beginning Balance:\s*\$([\d,.]+)", text) else None
    ending = _num(re.search(r"Ending Balance:\s*\$([\d,.]+)", text).group(1)) \
        if re.search(r"Ending Balance:\s*\$([\d,.]+)", text) else None

    deposit_lines = re.findall(r"\d{4}-\d{2}-\d{2}\s+\$([\d,.]+)\s+(.+)", text)
    largest_amount = largest_desc = documented = None
    if deposit_lines:
        parsed = [(_num(amt), desc.strip()) for amt, desc in deposit_lines]
        largest_amount, largest_desc = max(parsed, key=lambda p: p[0])
        low = largest_desc.lower()
        documented = "yes" if any(k in low for k in DOC_KEYWORDS) else "no"

    values = {
        "account_holder": holder, "institution": institution, "account_type": account_type,
        "period_start": period_start, "period_end": period_end,
        "beginning_balance": beginning, "ending_balance": ending,
        "largest_deposit_amount": largest_amount, "largest_deposit_description": largest_desc,
        "deposit_documented": documented,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    reserve, flag = _compute(values)
    return {"fields": out, "computed_reserve_value": reserve, "large_deposit_flag": flag,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
