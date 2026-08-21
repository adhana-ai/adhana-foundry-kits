"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `conforms_to_spec` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the analyst's disposition note and nothing else: a note carrying one of a
fixed list of worried-sounding words ("borderline", "hold", "re-test", "marginal", "flagged")
means "no", and anything else means "yes". That is precisely the shortcut the prompt's guardrail
forbids -- deciding conformance from prose instead of from the two limits and the measured value.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
comparison is four lines of arithmetic; the baseline already regexes all three numbers out of the
document. A rules baseline that did the arithmetic would score 100 pct on this corpus and tell you
nothing about the model -- so the floor is deliberately the SHORTCUT, not the rule, and the gap it
opens is the gap between reading prose and doing the comparison. src/extract.py::compute() is where
the arithmetic actually lives, and it runs over the MODEL's numbers, which is a different job.
"""
import re

from src.extract import compute as _compute

WORRIED_KEYWORDS = ("borderline", "hold", "re-test", "retest", "marginal", "flagged",
                    "not comfortable")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _measure(s):
    """Split '11.4 %' into (11.4, '%'). Returns (None, None) on a line stating no limit."""
    if s is None or "not specified" in s:
        return None, None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*(.*)$", s)
    if not m:
        return None, None
    raw = m.group(1)
    value = float(raw) if "." in raw else int(raw)
    return value, (m.group(2).strip() or None)


def extract_one(text, fields):
    batch_id = _section(text, "Batch")
    product_name = _section(text, "Product")
    test_parameter = _section(text, "Test Parameter")
    measured_value, unit = _measure(_section(text, "Measured Result"))
    spec_lower_limit, _lu = _measure(_section(text, "Specification Lower Limit"))
    spec_upper_limit, _uu = _measure(_section(text, "Specification Upper Limit"))
    test_date = _section(text, "Test Date")
    note = _section(text, "Analyst Disposition Note")

    low = (note or "").lower()
    conforms = "no" if any(k in low for k in WORRIED_KEYWORDS) else "yes"

    values = {
        "batch_id": batch_id, "product_name": product_name, "test_parameter": test_parameter,
        "measured_value": measured_value, "unit": unit,
        "spec_lower_limit": spec_lower_limit, "spec_upper_limit": spec_upper_limit,
        "analyst_disposition_note": note, "test_date": test_date,
        "conforms_to_spec": conforms,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    needs_review, recomputed = _compute(values)
    return {"fields": out, "needs_review": needs_review, "recomputed_conforms": recomputed,
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
