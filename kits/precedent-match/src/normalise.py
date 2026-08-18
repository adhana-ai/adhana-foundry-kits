"""Tidy the categorical fields a request and a history event both carry, and stop there.

⚑ THE LINE THIS FILE DOES NOT CROSS. Lowercasing and trimming punctuation is allowed. Deciding that
two DIFFERENT ad-placement codes describe the same physical placement ("circular_front" and
"circular_inside" are both a paper circular) is NOT -- that equivalence is domain judgement, and it
lives in src/similarity.py and src/prompt.py's own rule text, never here. If the normaliser folded
placement families together, the free floor's real score would move for a reason nobody wrote down,
exactly the discipline data-match's normalise.py states about nicknames.
"""
import re

_SPACE = re.compile(r"\s+")


def text(value):
    v = (value or "").strip().lower()
    v = v.replace("-", "_").replace(" ", "_")
    return _SPACE.sub(" ", v).strip()


def fields(record):
    """Raw and normalised, side by side -- the UI and the comparer both read this."""
    keys = ("mechanic", "price_band", "ad_placement", "season")
    return {k: {"raw": record.get(k, ""), "norm": text(record.get(k, ""))} for k in keys}
