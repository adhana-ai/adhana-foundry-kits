"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as
a paid run, so the two are directly comparable.

⚑ `is_serious` HERE IS A DELIBERATE SEVERITY-REGISTER FLOOR, WRITTEN TO FAIL THE PLANTED
AMBIGUITY BY CONSTRUCTION. It answers one question -- does the report call the event "severe"? --
and returns that as the regulatory classification. That is exactly the shortcut the prompt's
guardrail exists to forbid, and it is not a straw man: reading the severity adjective is the
single most available signal in a case narrative and it is right about 60% of the time on this
corpus, which is precisely what makes it dangerous.

It will call a "mild" rash that led to a three-day admission not serious, and a "severe" headache
that resolved at home serious. The gap between this floor and a model that reads the narrative for
which seriousness criterion was actually met is the demonstration this kit exists to run -- see
data/SOURCES.md.

⚠︎ THE FLOOR IS NOT WEAK ON THE OTHER NINE FIELDS, AND SAYING SO IS THE POINT. A fixed record
layout is mostly regex work; a baseline that lost on the easy fields too would let a reader credit
the model for the wrong reason. Every structured field below is read straight off its heading.
"""
import re

from src.extract import compute as _compute

# The whole floor. One word.
SEVERE_REGISTER = ("severe",)
# The corpus's severity vocabulary. tools/build_corpus.py asserts no other register word, and no
# form of "serious", ever appears in a document -- so this list is exhaustive over the inputs.
ALL_REGISTER = ("severe", "moderate", "mild")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def extract_one(text, fields):
    low = text.lower()

    word = None
    for w in ALL_REGISTER:
        if re.search(r"\b%s\b" % w, low):
            word = w
            break

    is_serious = "yes" if any(re.search(r"\b%s\b" % w, low) for w in SEVERE_REGISTER) else "no"

    values = {
        "case_id": _section(text, "Case ID"),
        "patient_age_range": _section(text, "Patient Age Range"),
        "suspect_drug": _section(text, "Suspect Drug"),
        "event_description": _section(text, "Event Description"),
        "narrative_severity_word": word,
        "hospitalization": _section(text, "Hospitalization"),
        "event_outcome": _section(text, "Event Outcome"),
        "causality_assessment": _section(text, "Reporter Causality Assessment"),
        "reporter_type": _section(text, "Reporter Type"),
        "is_serious": is_serious,
    }
    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "needs_review": _compute(values),
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
