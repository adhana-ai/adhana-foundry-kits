"""Tidy correspondence text the way any pipeline would, and stop there.

⚑ THE LINE THIS FILE DOES NOT CROSS IS THE SAME ONE data-match's normalise.py DRAWS. Lowercasing
and collapsing whitespace is allowed; understanding that "the split collars order" and "REC-00004"
might refer to the same record is NOT -- that is the matching judgement this kit measures, and if
the normaliser resolved it, the free floor's real score would move for a reason nobody wrote down.
"""
import re

_PUNCT = re.compile(r"[^\w\s\-$.]+")
_SPACE = re.compile(r"\s+")

RECID_RE = re.compile(r"\bREC-\d{5}\b")
SKU_RE = re.compile(r"\bSKU-\d{4}\b")


def text(value):
    v = (value or "").strip().lower()
    v = _PUNCT.sub(" ", v)
    return _SPACE.sub(" ", v).strip()


def find_recid(raw_text):
    m = RECID_RE.search(raw_text or "")
    return m.group(0) if m else None


def find_skus(raw_text):
    return SKU_RE.findall(raw_text or "")
