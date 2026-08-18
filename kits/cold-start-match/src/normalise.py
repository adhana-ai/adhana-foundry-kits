"""Tidy the categorical fields a request and a history item both carry, and stop there.

⚑ THE LINE THIS FILE DOES NOT CROSS. Lowercasing and trimming punctuation is allowed. Deciding
that two DIFFERENT channel codes describe the same shelf ("ecommerce_only" and "marketplace" are
both online-only) is NOT -- that equivalence is domain judgement, and it lives in
src/similarity.py and src/prompt.py's own rule text, never here. If the normaliser folded channel
families together, the free floor's real score would move for a reason nobody wrote down, exactly
the discipline data-match's normalise.py states about nicknames.
"""
import re

_SPACE = re.compile(r"\s+")


def text(value):
    v = (value or "").strip().lower()
    v = v.replace("-", "_").replace(" ", "_")
    return _SPACE.sub(" ", v).strip()


def fields(record):
    """Raw and normalised, side by side -- the UI and the comparer both read this."""
    keys = ("material", "price_tier", "channel", "season")
    return {k: {"raw": record.get(k, ""), "norm": text(record.get(k, ""))} for k in keys}
