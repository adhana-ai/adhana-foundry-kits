"""The zero-cost floor a redaction model has to beat. No model, no key, no cost.

⚑ FIVE OF SEVEN CATEGORIES HAVE A FIXED SURFACE SHAPE; TWO DO NOT, AND THIS FILE SAYS SO RATHER
THAN FAKING ONE. SSN, EMAIL, PHONE, CARD and (when cued by a nearby label) DOB all have a
recognisable pattern a regex can name in advance — the same reasoning docs-extract's rules
baseline uses for its four perfect header fields. NAME and ADDRESS do not: a person's name has no
shape a regex can distinguish from any other two or three capitalised words, and a street address
is prose with a ZIP code somewhere in it, not a fixed grammar. This baseline abstains on both
rather than shipping a NER model or a gazetteer dressed up as "zero-cost" — abstaining is the
honest floor, and it is exactly what src/redact.py's own judge counts a genuinely-missed category
as: a leak, the same failure direction a naive fork would have shipped by doing nothing.

⚠︎ WRITTEN FROM THE CATEGORY HINTS IN data/categories.json, NOT TUNED AGAINST THE CORPUS. Same
discipline as docs-route's and docs-redline's baselines: the patterns are what a person would guess
before seeing the data, and were not revised after being scored against results/eval-b000*.json.

⚠︎ NOT A GRADER AND NOT A FALLBACK. Nothing in the live path (src/detect.py, src/app.py) calls
this. It is a second detector run over the same corpus and scored by the same judge
(evals/judge.py), so the two are comparable by construction — same denominator, same code path.
"""
import re

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?:\+\d{1,2}\s*)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_MONTHS = (r"January|February|March|April|May|June|July|August|September|October|"
           r"November|December")
_DOB_DATE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|"
    r"\b\d{1,2}\s+(?:%s)\s+\d{4}\b|\b(?:%s)\s+\d{1,2},?\s+\d{4}\b" % (_MONTHS, _MONTHS))
# A date only counts as a DOB guess when a label sits within 20 characters before it — the same
# cue a person would use, and the reason this baseline does not simply flag every date in a
# document (an appointment date, an issue date) as someone's birthday.
_DOB_CUE = re.compile(r"\b(?:DOB|date of birth|born)\b[:\s]{0,20}", re.I)


def _find_all(pattern, text, category):
    return [{"text": m.group(0), "category": category} for m in pattern.finditer(text)]


def _find_dob(text):
    out = []
    for cue in _DOB_CUE.finditer(text):
        window = text[cue.end():cue.end() + 25]
        m = _DOB_DATE.search(window)
        if m:
            out.append({"text": m.group(0), "category": "DOB"})
    return out


def regex_detect(doc_text):
    """Same shape src/detect.py's `spans` list carries: [{"text","category"}, ...]. Scored by
    evals/judge.py exactly like a model reply — one code path, so the two are comparable."""
    text = doc_text or ""
    spans = []
    spans += _find_all(_SSN, text, "SSN")
    spans += _find_all(_EMAIL, text, "EMAIL")
    spans += _find_all(_PHONE, text, "PHONE")
    spans += _find_all(_CARD, text, "CARD")
    spans += _find_dob(text)
    # NAME and ADDRESS: no regex. Abstaining on both is the honest floor — see module docstring.
    return spans


BASELINES = {"regex": (regex_detect, "5 pattern families (SSN, EMAIL, PHONE, CARD, cued DOB); "
                       "abstains on NAME and ADDRESS, which have no fixed surface shape")}
