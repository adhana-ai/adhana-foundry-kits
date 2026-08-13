"""The free floor: a keyword router, which is what most teams actually ship before a model.

⚑ THE FLOOR IS SCORED BEFORE ANY MODEL IS CALLED, AND IT IS THE ARGUMENT FOR THE KIT. If a
regular expression per tool gets close to what the model gets, the model is not buying much and
the honest thing is to say so on the page. UC012's floor BEAT its model; that possibility is why
this file exists and why it is written first.

⚠︎ ORDER IS PART OF THE FLOOR, NOT AN IMPLEMENTATION DETAIL. A request matching two rules gets
them in RULE order, which has nothing to do with the order the tools actually need to run in.
That is not a bug to fix — it is the structural thing a keyword router cannot do, and flattening
it would make the floor look better than any keyword router really is.

⚑ THE CAP IS A CONTROL, NOT A CONSTANT. `sweep()` scores every setting from 1 to 4 so the page can
show what tuning buys, and the answer is "one step, then nothing" — above 2 no request in the set
matches a third rule, so the router's ceiling is its rules and not its budget.
"""
from __future__ import annotations

import re

# One rule per tool, tried in this order. Written to be a fair, ordinary keyword router — the sort
# somebody writes in an afternoon — not a straw man and not one tuned against the labels.
RULES = [
    ("today", r"\btoday\b|\bcurrent\b|\bdate\b"),
    ("doc_search", r"\bpolicy\b|\bpolicies\b|\brule\b|\ballowed\b|\bterms\b|\breturns?\b"
                   r"|\bwarranty\b|\bshipping\b|\bloyalty\b|\brefunds?\b|\bcancel"),
    ("calc", r"\bpercent|%|\baverage\b|\bmultiplied\b|\bdifference\b"),
    ("shop_sql", r"\border|\bcustomer|\brevenue\b|\bhow many\b|\btotal\b|\bspent\b|\bspend\b"
                 r"|\bsales\b|\bfile\b"),
]

DEFAULT_CAP = 1


def route(text, cap=DEFAULT_CAP):
    """Every rule whose pattern matches, in rule order, truncated to `cap` calls."""
    hits = [name for name, pat in RULES if re.search(pat, text, re.I)]
    return hits[:cap]


def score(requests, cap=DEFAULT_CAP):
    """Score the floor over the whole set at one setting. Returns rows in the shape score.py wants
    so the floor and the model are graded by the SAME code — a floor with its own scorer is a floor
    nobody can compare against."""
    from . import score as S
    rows = []
    for req in requests:
        got = route(req["text"], cap)
        rows.append({"id": req["id"], "trap": req["trap"], "text": req["text"],
                     "truth": list(req["truth"]), "decline": req.get("decline", False),
                     "got": got, "outcome": S.outcome(req, got)})
    return rows


def sweep(requests, caps=(1, 2, 3, 4)):
    """Every setting, so "no setting gets them all" is measured rather than asserted."""
    from . import score as S
    out = []
    for cap in caps:
        rows = score(requests, cap)
        s = S.tally(rows)
        out.append({"cap": cap, "summary": s, "traps_handled": S.traps_handled(rows),
                    "by_trap": S.by_trap(rows)})
    return out
