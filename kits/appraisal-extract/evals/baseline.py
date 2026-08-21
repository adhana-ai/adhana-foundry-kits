"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `extraordinary_assumption_present` HERE IS A DELIBERATE HEADING-ONLY FLOOR, WRITTEN TO FAIL THE
PLANTED AMBIGUITY BY CONSTRUCTION. It checks ONLY for a section literally titled "Extraordinary
Assumptions" and answers 'no' whenever that heading is absent -- exactly the shortcut the prompt's
guardrail exists to forbid a model from taking. It will miss every embedded assumption sitting in
Scope of Work or Comments prose with no heading of its own. The gap between this baseline and a
model that actually reads the whole report is the demonstration this kit exists to run -- see
data/SOURCES.md.
"""
import re

from src.extract import compute as _compute


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def extract_one(text, fields):
    address = _section(text, "Subject Property")
    appraiser = _section(text, "Appraiser")
    effective_date = _section(text, "Effective Date")
    report_date = _section(text, "Report Date")
    approach = _section(text, "Valuation Approach")
    approach = approach.replace(" ", "_") if approach else None

    improvements = _section(text, "Improvements") or ""
    m = re.search(r"Gross living area:\s*(\d+)", improvements)
    gla = int(m.group(1)) if m else None
    m = re.search(r"Comparable sales used:\s*(\d+)", improvements)
    comp_count = int(m.group(1)) if m else None

    m = re.search(r"Reconciled value opinion:\s*\$([\d,]+)", text)
    reconciled_value = float(m.group(1).replace(",", "")) if m else None

    ea_text = _section(text, "Extraordinary Assumptions")
    present = "yes" if ea_text else "no"

    values = {
        "property_address": address, "appraiser_name": appraiser,
        "effective_date": effective_date, "report_date": report_date,
        "approach_used": approach, "reconciled_value": reconciled_value,
        "gross_living_area_sqft": gla, "comparable_count": comp_count,
        "extraordinary_assumption_present": present,
        "extraordinary_assumption_text": ea_text,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    needs_review = _compute(values)
    return {"fields": out, "needs_review": needs_review, "sections_used": [],
            "prompt_parts": [], "input_tokens": 0, "output_tokens": 0, "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
