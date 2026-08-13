"""What counts as right, and the five ways a tool-choosing run goes wrong.

⚑ THERE IS NO SINGLE ACCURACY NUMBER HERE, AND THAT IS DELIBERATE — the same reason UC012 refuses
one. The failures have different owners and different costs. Calling a tool you did not need is
latency and money; stopping a step early is a half answer that reads like a whole one; running a
query for a question nothing can answer is a confident wrong answer, which is the most expensive
kind. Averaging them into one percentage would let a decider trade the cheap failure for the
dangerous one and look better for it.

⚠︎ `no_verdict` IS ITS OWN STATE AND MUST NOT COLLAPSE INTO ANYTHING ELSE. A model that returns
nothing calls no tools — so on this kit an empty reply looks exactly like correct restraint on
every "needs no tool" request, and a totally broken run would score well on the restraint measure.
It is counted apart, excluded from every published rate, and `answered` ships beside them, because
UC011 published 100%/100% off one answered pair in 78 before that rule existed.

⚑ ORDER IS PART OF THE ANSWER. `shop_sql -> calc` and `calc -> shop_sql` are not the same run: the
second cannot work, because the arithmetic needs the number the query returns. Sequences are
compared as sequences, never as sets.
"""
from __future__ import annotations

OUTCOMES = ("correct", "wrong_tool", "stopped_early", "kept_going", "should_have_declined",
            "no_verdict")

MEANS = {
    "correct": "exactly the tools it needed, in order, and it stopped",
    "wrong_tool": "called a tool the request does not need — or asked for one that does not exist",
    "stopped_early": "a prefix of the right sequence: a half answer that reads like a whole one",
    "kept_going": "the right sequence plus calls that bought nothing — latency and money",
    "should_have_declined": "nothing here could answer it and it ran a tool anyway",
    "no_verdict": "nothing usable came back",
}


def outcome(req, got, replied=True):
    """One request's outcome. `got` is the tool sequence actually called, in order."""
    if not replied:
        return "no_verdict"
    truth = list(req["truth"])
    got = list(got)
    if req.get("decline"):
        # The only right move is to call nothing and say so. Calling anything is the failure this
        # trap exists to catch, and it is NOT "kept_going" — the distinction is between doing too
        # much and answering something unanswerable, which are different lessons.
        return "correct" if not got else "should_have_declined"
    if got == truth:
        return "correct"
    if truth and len(got) < len(truth) and got == truth[:len(got)]:
        return "stopped_early"
    if len(got) > len(truth) and got[:len(truth)] == truth:
        return "kept_going"
    if not truth and got:
        return "kept_going"
    return "wrong_tool"


def tally(rows):
    """Counts per outcome, plus the numbers this kit publishes — kept apart on purpose.

    `sequence_exact` is the headline: of the requests that were answered, how many got exactly the
    right tools in the right order. `calls_per_request` is the other half of the story and the one
    no earlier kit had: the model chooses how many calls to make, so the cost is a distribution
    rather than a constant.
    """
    c = {k: 0 for k in OUTCOMES}
    for r in rows:
        c[r["outcome"]] = c.get(r["outcome"], 0) + 1
    answered = len(rows) - c["no_verdict"]
    calls = [len(r["got"]) for r in rows if r["outcome"] != "no_verdict"]
    wasted = sum(max(0, len(r["got"]) - len(r["truth"])) for r in rows
                 if r["outcome"] != "no_verdict")
    return {
        "counts": c,
        "requests": len(rows),
        "answered": answered,
        "coverage": round(answered / len(rows), 4) if rows else None,
        "sequence_exact": round(c["correct"] / answered, 4) if answered else None,
        "calls_total": sum(calls),
        "calls_per_request_mean": round(sum(calls) / len(calls), 3) if calls else None,
        "calls_per_request_max": max(calls) if calls else None,
        "calls_wasted": wasted,
        "no_verdict": c["no_verdict"],
        "reconciles": sum(c.values()) == len(rows),
    }


def by_trap(rows):
    """Per-trap results, because one number hides WHICH kind of hard case it fails — and here the
    kinds have different owners. `two-step` failures are a stopping problem; `wrong-surface` is a
    reading problem; `unanswerable` is a refusal problem, and only the last one is dangerous."""
    out = {}
    for r in rows:
        t = out.setdefault(r["trap"], {"requests": 0, "wrong": 0, "outcomes": {}})
        t["requests"] += 1
        t["outcomes"][r["outcome"]] = t["outcomes"].get(r["outcome"], 0) + 1
        if r["outcome"] != "correct":
            t["wrong"] += 1
    return out


def traps_handled(rows):
    """Which trap KINDS came out completely clean.

    ⚑ RETURNS THE EVIDENCE, NOT THE SENTENCE. A trap counts as handled only when every request
    carrying it was correct; getting four of six right is not "handles two-step", it is a coin
    flip with a good day. The wireframe's claim that no floor setting gets them all is checked
    against this at every setting, and it is allowed to come out false — if some setting does,
    that is a finding and the report has to say so.
    """
    return {trap: t["wrong"] == 0 for trap, t in by_trap(rows).items()}
