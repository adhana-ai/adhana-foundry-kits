"""The zero-cost baseline a materiality model has to beat. No model, no key.

⚑ THE SIGNAL IS SURFACE, ON PURPOSE — same discipline as docs-route's keyword baseline: thirty
lines of regex over words and shapes the changed span already contains, written from what a
person would guess before seeing the data (a number changed -> probably material; a spelling was
fixed -> probably editorial), and not revised after scoring against any run.

⚠︎ THIS IS NOT THE PUBLISHED GOLD. Unlike docs-route, this kit has no publisher-assigned label to
lose to — see materiality.py. What this baseline gives the model to beat is a floor: if a keyword
baseline agrees with a model exactly as often as two independent models agree with each other,
the model is not adding judgment, it is adding cost. Whether that is true is what the kit measures.
"""
import re

from src import materiality as MT

# A number, a dollar amount, a date, a percentage, or a section/citation — the shapes that show up
# when a fix changes what a rule REQUIRES rather than how it reads.
_MATERIAL_SHAPE = re.compile(
    r"\$[\d,]+|\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:percent|%)?\b|\b\d{4}\b|"
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\s+\d{1,2}\b|"
    r"\bsection\s+\d|\b\d+\s*C\.?F\.?R\.?\b|\bsubpart\s+\w\b", re.I)

# Words the Federal Register itself uses when a correction is purely cosmetic.
_EDITORIAL_WORDS = re.compile(
    r"\btypographical\b|\bclerical\b|\bspelling\b|\bpunctuation\b|\bformatting\b|"
    r"\bcross[- ]reference\b|\bcaption\b|\bheading\b", re.I)


def regex_predict(span):
    """span: {"v1": str, "v2": str} from diff.primary(). Returns the same shape a model reply
    parses into, so evals/score.py scores every record source through one code path."""
    text = "%s %s" % (span.get("v1") or "", span.get("v2") or "")
    if _EDITORIAL_WORDS.search(text) and not _MATERIAL_SHAPE.search(text):
        return {"materiality": "editorial", "confidence": None, "state": "ok",
                "rule": "editorial wording, no material shape"}
    if _MATERIAL_SHAPE.search(text):
        return {"materiality": "material", "confidence": None, "state": "ok",
                "rule": "contains a number, date, amount or citation"}
    return {"materiality": None, "confidence": None, "state": "abstained",
            "rule": "no surface signal either way"}


BASELINES = {"regex": (regex_predict, "%d regex(es) over the changed span's surface shape"
                       % (_MATERIAL_SHAPE.pattern.count("|") + _EDITORIAL_WORDS.pattern.count("|")
                          + 2))}
