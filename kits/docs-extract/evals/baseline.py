"""A non-LLM extractor: rules and regexes, no model, no key, no cost.

⚑ WHY A KIT SHIPS THE THING THAT MIGHT BEAT IT.
Operator decision at UC002's Stop A: publish this even where it wins. Several of these fields are
stated in fixed shapes — "NCT Number: NCT01234567" sits under a heading this corpus writes itself —
and a regex will take them every time, for nothing, in microseconds. A kit that reported only its
model's accuracy would let a reader conclude the model earned all nine fields when it earned some
of them, and "the model earned its keep on N of 9 fields" is the more useful sentence.

It is also the honest floor for the refusal half. This baseline abstains wherever its pattern does
not match, so it posts a high refusal accuracy without understanding anything — which is precisely
why refusal accuracy is never reported alone, and why a model must beat this on EXTRACTION to have
justified its bill.

⚠︎ NOT A GRADER AND NOT A FALLBACK. Nothing in the live path calls this. It is a second extractor
run over the same corpus and scored by the same judge, so the two are comparable by construction.
"""
import re

_AGE = re.compile(r"\b(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+age|old)?\b", re.I)
_ENROLL = re.compile(r"\b(\d{2,5})\s+(?:patients?|participants?|subjects?|women|men)\b", re.I)


def _header(text, label):
    m = re.search(r"^%s:\s*(.+)$" % re.escape(label), text, re.M)
    return m.group(1).strip() or None if m else None


def _sex(text):
    t = text.lower()
    if re.search(r"\b(female|women)\s+only\b", t) or re.search(r"\bonly\s+(females?|women)\b", t):
        return "FEMALE"
    if re.search(r"\b(male|men)\s+only\b", t) or re.search(r"\bonly\s+(males?|men)\b", t):
        return "MALE"
    if re.search(r"\b(both sexes|male and female|men and women|either sex)\b", t):
        return "ALL"
    return None


def _masking(text):
    t = text.lower()
    for word, val in (("quadruple", "QUADRUPLE"), ("triple", "TRIPLE"), ("double", "DOUBLE"),
                      ("single", "SINGLE"), ("open-label", "NONE"), ("open label", "NONE")):
        if re.search(r"\b%s[- ]?(blind|masked|dummy)?\b" % re.escape(word), t):
            if word in ("open-label", "open label") or re.search(
                    r"\b%s[- ]?(blind|masked|dummy)\b" % re.escape(word), t):
                return val
    return None


def extract(doc_text, fields):
    """Same output shape as src.extract.extract()'s `fields`, so the judge cannot tell them apart."""
    v = {
        "nct_id": _header(doc_text, "NCT Number"),
        "brief_title": _header(doc_text, "Brief Title"),
        "condition": _header(doc_text, "Conditions"),
        "sex": _sex(doc_text),
        "masking": _masking(doc_text),
    }
    m = re.search(r"^Primary Outcome Measures\n-+\n\* (.+)$", doc_text, re.M)
    v["primary_outcome"] = m.group(1).strip() if m else None
    m = _AGE.search(doc_text)
    v["minimum_age"] = ("%s Years" % m.group(1)) if m else None
    m = _ENROLL.search(doc_text)
    v["enrollment"] = m.group(1) if m else None
    t = doc_text.lower()
    v["allocation"] = ("RANDOMIZED" if re.search(r"\brandomi[sz]ed\b", t) else
                       ("NON_RANDOMIZED" if re.search(r"\bnon-randomi[sz]ed\b", t) else None))

    # `spannable` is declared here too, and it must match src/extract.py exactly. The judge uses
    # it as the span-rate DENOMINATOR, so a baseline that omitted it would be scored over a
    # different set of cells than the model — two runs, one judge, incomparable figures. That is
    # the same defect this estate already shipped once, comparing two model tiers as if they were
    # one system.
    return {f["name"]: {"value": v.get(f["name"]),
                        "spannable": f.get("type") != "enum",
                        "span": None}                       # rules do not claim spans
            for f in fields}
