"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `sanction_or_adverse_action_found` HERE IS A DELIBERATE SEVERE-KEYWORD FLOOR, WRITTEN TO FAIL
THE PLANTED AMBIGUITY BY CONSTRUCTION. It marks an adverse action found only when the PSV finding
contains one of a fixed list of unambiguously severe words ("revoked", "suspended", "excluded",
"disciplinary hearing") -- exactly the shortcut the prompt's guardrail exists to forbid a model
from taking. It will miss every mild-worded finding ("reprimand", "consent order", "letter of
concern") entirely. The gap between this baseline and a model that reads the whole finding is the
demonstration this kit exists to run -- see data/SOURCES.md.
"""
import re

from src.extract import compute as _compute

SEVERE_KEYWORDS = ("revoked", "suspended", "excluded", "disciplinary hearing")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def extract_one(text, fields):
    provider_name = _section(text, "Provider")
    npi = _section(text, "NPI")
    license_number = _section(text, "License Number")
    provider_type = _section(text, "Provider Type")
    license_expiration_date = _section(text, "License Expiration Date")
    credentialing_effective_date = _section(text, "Credentialing Effective Date")
    psv_check_date = _section(text, "PSV Check Date")
    psv_source = _section(text, "PSV Source")
    finding = _section(text, "PSV Finding")

    low = (finding or "").lower()
    adverse = "yes" if any(k in low for k in SEVERE_KEYWORDS) else "no"

    values = {
        "provider_name": provider_name, "npi": npi, "license_number": license_number,
        "provider_type": provider_type, "license_expiration_date": license_expiration_date,
        "credentialing_effective_date": credentialing_effective_date,
        "psv_check_date": psv_check_date, "psv_source": psv_source,
        "psv_raw_finding": finding, "sanction_or_adverse_action_found": adverse,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    needs_review, reasons = _compute(values)
    return {"fields": out, "needs_review": needs_review, "review_reasons": reasons,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
