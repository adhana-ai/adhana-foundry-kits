"""Tidy a record the way any pipeline would, and stop there.

⚑ THE LINE THIS FILE DOES NOT CROSS IS THE WHOLE POINT OF THE KIT. Normalisation is allowed to know
things about WRITING: that case is noise, that "Rd" and "Road" are the same word, that a dot in an
email local part is not a difference. It is NOT allowed to know things about PEOPLE — that Kate is
short for Kathryn, that a hyphenated surname may be a married name, that 04-08 and 08-04 might be one
date typed by two people.

That distinction is the experiment. If the normaliser learned nicknames, the deterministic floor would
climb, the model's contribution would shrink, and the kit would report a smaller gap between free and
paid — not because the world changed but because we moved work across the line and did not say so. So
the nickname table lives in the corpus generator (as a trap) and in nobody's normaliser.

⚠︎ NOTHING HERE IS LOSSY IN A WAY THE UI CANNOT SHOW. `fields()` returns the normalised values
alongside the raw ones, because a reader looking at "why did these two match" needs to see what the
comparison actually compared, not what was typed.
"""
import re

SUFFIXES = {"rd": "road", "st": "street", "ave": "avenue", "av": "avenue", "ln": "lane",
            "cl": "close", "dr": "drive", "ct": "court", "pl": "place", "sq": "square",
            "apt": "apartment", "flat": "apartment", "no": "number"}

_PUNCT = re.compile(r"[^\w\s@.\-]+")
_SPACE = re.compile(r"\s+")


def text(value):
    """Case, punctuation and whitespace. The uncontroversial half."""
    v = (value or "").strip().lower()
    v = _PUNCT.sub(" ", v)
    return _SPACE.sub(" ", v).strip()


def address(value):
    """Street-type words expanded, so "88 Ferndale Rd" and "88 Ferndale Road" are one string."""
    words = [SUFFIXES.get(w, w) for w in text(value).split()]
    return " ".join(words)


def email(value):
    """Lowercased, and the local part stripped of dots and +tags — the two conventions every mail
    provider treats as the same mailbox. The DOMAIN is left alone: example.com and example.net are
    different mailboxes and pretending otherwise would invent a match."""
    v = text(value).replace(" ", "")
    if "@" not in v:
        return v
    local, _, domain = v.partition("@")
    local = local.split("+", 1)[0].replace(".", "")
    return "%s@%s" % (local, domain)


def dob(value):
    """Digits only, in the order written. ⚠︎ DELIBERATELY NOT REORDERED into a canonical date. A
    transposed day and month is one of the planted traps, and a normaliser that sorted the parts would
    silently solve it — turning a judgement the model is supposed to make into a string operation, and
    reporting the model as better than it is."""
    return re.sub(r"\D", "", value or "")


def name(value):
    """Case and punctuation only. Initials are NOT expanded and nicknames are NOT resolved."""
    return text(value)


def fields(record):
    """Raw and normalised, side by side, for the comparer and for the UI that has to explain it."""
    return {
        "name": {"raw": record.get("name", ""), "norm": name(record.get("name", ""))},
        "dob": {"raw": record.get("dob", ""), "norm": dob(record.get("dob", ""))},
        "address": {"raw": record.get("address", ""), "norm": address(record.get("address", ""))},
        "email": {"raw": record.get("email", ""), "norm": email(record.get("email", ""))},
    }
