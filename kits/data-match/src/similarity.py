"""The free matcher. A weighted string-similarity score per pair, and no model anywhere near it.

⚑ THIS IS A REAL BASELINE, NOT A STRAWMAN, AND THAT MATTERS TO EVERY NUMBER THIS KIT PUBLISHES. A
weighted field comparison with a threshold is what a great many production dedupe systems actually
run — often the whole system. So it is not here to lose; it is here to be the number the model has to
beat, and if the model does not beat it, that IS the finding and it gets published as one.

⚠︎ IT IS SCORED BY THE SAME SCORER THE MODEL'S ANSWERS GO THROUGH (`evals/run.py::score_pair`). A
baseline with its own scorer is a second opinion, not a floor.

HOW IT SCORES. Per field, `difflib.SequenceMatcher` over the normalised values — stdlib, no install,
and its behaviour is inspectable by anyone reading this file. The fields are weighted because they are
not equally diagnostic: an email is nearly an identifier, a date of birth is strong, a name is weak
(common names collide) and an address is weak (families and flatmates share them). Those weights are a
JUDGEMENT and they are written down here rather than tuned against the labels, because tuning weights
on the eval set is how a floor quietly becomes a fitted model with no test set left.

⚠︎ WHAT IT CANNOT DO, BY CONSTRUCTION. It cannot know Kate is Kathryn, it cannot know a surname
changed, and it cannot tell a father from a son whose fields all agree. Those are the four traps in the
corpus, and it will fail them in both directions — which is exactly the gap the model is being asked
to close, and the reason its per-trap results are reported separately.
"""
import difflib

from src import normalise

# field: (weight, why this weight)
WEIGHTS = {
    "email": (0.35, "closest thing to an identifier a customer list has, and the least often shared"),
    "dob": (0.30, "strong, and cheap to get wrong by one transposition"),
    "name": (0.20, "weak on its own — common names collide, nicknames diverge"),
    "address": (0.15, "weakest — families, flatmates and previous tenants all share one"),
}


def field_score(a, b):
    """0..1 for one normalised pair. Two empty strings are not evidence of anything, so they score 0
    rather than 1 — a missing field on both sides must never read as agreement."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def compare(rec_a, rec_b):
    """The pair's score, plus the per-field detail the UI needs to explain it."""
    fa, fb = normalise.fields(rec_a), normalise.fields(rec_b)
    detail, total = {}, 0.0
    for key, (weight, _why) in WEIGHTS.items():
        s = field_score(fa[key]["norm"], fb[key]["norm"])
        detail[key] = {"score": round(s, 4), "weight": weight,
                       "exact": bool(fa[key]["norm"]) and fa[key]["norm"] == fb[key]["norm"],
                       "a": fa[key]["raw"], "b": fb[key]["raw"],
                       "a_norm": fa[key]["norm"], "b_norm": fb[key]["norm"]}
        total += s * weight
    return {"score": round(total, 4), "fields": detail,
            "agreed": sorted(k for k, v in detail.items() if v["exact"])}


def score(rec_a, rec_b):
    """Just the number, for callers that do not need the breakdown."""
    return compare(rec_a, rec_b)["score"]
