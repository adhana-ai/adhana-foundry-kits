"""SEAM 3 — the free floor: the rule engine almost every on-call rotation is actually running.

⚑ THIS IS NOT A STRAWMAN, AND THAT IS THE WHOLE POINT OF THE KIT. On most kits in this repo the
free baseline is a constant — answer the same thing every time — and it exists only to prove the
model is doing something. Here the free answer is a WORKING PAGER: a threshold on an error count,
plus a regex on the message, which between them are what a very large number of production alerting
setups amount to once you strip the dashboards off. So the question this kit asks is not "is the
model better than nothing", it is "is the model better than the thing you already have", and that
is the only version worth paying to answer.

⚠︎ WHICH MEANS THE FLOOR HAS TO BE BUILT TO WIN, NOT BUILT TO LOSE. A regex of `ERROR` would be a
strawman and would flatter the model by handicapping the thing it is compared against. The pattern
below is the sort a competent SRE writes: the words that genuinely mean "this is not routine" —
process death, storage exhaustion, a database refusing connections. It is allowed to be good. If it
turns out to be good enough, that is the finding and the report says so.

⚠︎ AND THE FLOOR IS SCORED THROUGH THE SAME SCORER AS THE MODEL. `src/decide.py`, same five
outcomes, same labels, same windows. A baseline with its own scorer is a second opinion, not a
floor.

── WHAT THE RULES CANNOT SEE, STRUCTURALLY ────────────────────────────────────────────────────────

Two of the six traps are invisible to anything in this file, and not because the patterns are bad:

    quiet-killer   one WARN line. No count threshold reacts to one line, and the text is ordinary
                   English about a certificate — there is no alarming word in it to match, because
                   nothing is on fire yet. It is a fuse, and it is lit.
    silence        ⚑ zero lines. Every rule here is written to match text that IS THERE. A regex
                   cannot match an absence and a count of errors cannot be alarmed by the number
                   zero. The gate in `window.py` can see it, by comparing against history; nothing
                   in this file can.

That is not a defect in the rules, it is the shape of rules. Writing it down here — beside the code
rather than in a report — is what stops the next person tuning the threshold for an hour trying to
catch a window that contains nothing to catch.
"""
import re

from . import decide, window

# ⚑ THE COUNT IS OVER ERROR AND FATAL LINES, WHICH IS WHAT A REAL THRESHOLD COUNTS. Not distinct
# messages — 47 repetitions of one broken probe is 47 errors to a rule engine, and giving the floor
# the benefit of deduplication would be handing it a discount it does not get in production.
DEFAULT_THRESHOLD = 20

# A real one. Each word earns its place by meaning "a process or a dependency has stopped", which
# is the class of event a pager is actually for.
KEYWORDS = re.compile(
    r"\b(FATAL|PANIC|segfault|OOMKilled|OutOfMemory|deadlock detected|"
    r"could not connect|connection refused|shutting down|no space|disk full|"
    r"corrupt|data loss|unrecoverable)\b", re.I)


def keyword_hits(win):
    """Every collapsed line whose text matches, with its count — the evidence, not a boolean."""
    out = []
    for row in window.collapse(win):
        if KEYWORDS.search(row["message"]) or KEYWORDS.search(row["level"]):
            out.append(row)
    return out


def decide_window(win, threshold=DEFAULT_THRESHOLD, use_count=True, use_keyword=True):
    """The floor's verdict on one window, and why. Returns (verdict, reasons)."""
    c = window.counts(win)
    reasons = []
    fires = False
    if use_count and c["loud"] >= threshold:
        reasons.append("%d error/fatal lines >= threshold %d" % (c["loud"], threshold))
        fires = True
    if use_keyword:
        hits = keyword_hits(win)
        if hits:
            reasons.append("keyword: %s" % hits[0]["message"][:60])
            fires = True
    if not fires:
        reasons.append("%d error/fatal lines < threshold %d, no keyword"
                       % (c["loud"], threshold if use_count else 0))
    return (decide.PAGE if fires else decide.HOLD), reasons


def score(windows, labels, threshold=DEFAULT_THRESHOLD, use_count=True, use_keyword=True):
    """The floor over a set of windows, through the shared scorer. Calls nothing, costs nothing."""
    by_id = {w["id"]: w for w in windows}
    rows = []
    for lab in labels:
        win = by_id[lab["id"]]
        verdict, reasons = decide_window(win, threshold, use_count, use_keyword)
        rows.append({"id": lab["id"], "label": lab["label"], "trap": lab["trap"],
                     "verdict": verdict, "replied": True, "reasons": reasons,
                     "loud": window.counts(win)["loud"],
                     "outcome": decide.outcome(lab["label"], verdict, True)})
    return rows
