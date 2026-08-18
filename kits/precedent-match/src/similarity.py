"""The free floor: a weighted exact-match score per (request, candidate) pair, scored BEFORE any
model is called. No key, no dependency, no network.

⚑ THIS IS A REAL BASELINE, NOT A STRAWMAN, AND IT MATTERS TO EVERY NUMBER THIS KIT PUBLISHES. Four
fields, checked for literal equality, each worth a quarter of the score -- exactly what a quick
script would do with no domain briefing at all: "does this candidate say the same mechanic, price
band, ad placement and season as the request." It is used only after src/block.py has already
narrowed the field to one category.

⚠︎ WHAT IT CANNOT DO, BY CONSTRUCTION. The true ANALOG rule (src/prompt.py's RULES, and the same
rule data/gold was labelled against) allows an ADJACENT price band and treats the two circular
placements as one family. A field-equality score has no notion of "adjacent" or "family" -- it can
only ever say identical or not. Every pair that needs one of those two allowances is a pair this
floor gets wrong, and that gap is the reason the model is asked to look at these pairs at all.
"""
FIELDS = ("mechanic", "price_band", "ad_placement", "season")
WEIGHT = 0.25


def field_score(a, b):
    if not a or not b:
        return 0.0
    return 1.0 if a == b else 0.0


def compare(request, event):
    detail, total = {}, 0.0
    for f in FIELDS:
        a, b = request.get(f, ""), event.get(f, "")
        s = field_score(a, b)
        detail[f] = {"score": s, "a": a, "b": b, "exact": s == 1.0}
        total += s * WEIGHT
    return {"score": round(total, 4), "fields": detail,
            "agreed": sorted(k for k, v in detail.items() if v["exact"])}


def score(request, event):
    return compare(request, event)["score"]
