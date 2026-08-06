"""The AI layer: one document in, one routing decision out. The whole model surface of this kit.

It is short for the same reason UC003's is short — everything above it is pure code and everything
below it is arithmetic. What makes this kit different from the three before it is that the thing
below it is arithmetic AT ALL: a routing decision has a gold answer somebody else wrote, so the
verdict is `==` rather than a judge or a person.

⚑ THE GUARDRAIL LIVES HERE, NOT IN THE EVAL. `decide()` applies the confidence floor and converts
a low-confidence answer into an escalation before anything downstream sees it. Putting that in the
scorer would measure a system nobody runs: in production the floor is part of the router, so the
number the kit publishes has to come from the same code path the app uses. UC001 learned this the
other way round and had to port a ranker to JS to keep one behaviour in two places.
"""
import json
import os

from . import adapters, prompt as P, taxonomy as TX

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ THE OUTPUT CEILING. A routing decision is a queue key, a number and one short sentence.
#
# ⚠︎ 400 WAS TOO LOW AND RUN r001 PAID 120 CALLS TO FIND OUT — 2026-08-06, and it is the SAME
# defect UC003 paid 42 calls for the day before. 6 of 120 documents came back with no content at
# all, and the split is exactly the ceiling: every one of the six reports 400 output tokens, where
# the 114 that parsed have a median of 82 and a maximum of 373. The reasoning pass is enabled by
# default on this model family, it consumed the whole allowance, and the message content arrived
# empty — which `prompt.parse` correctly reports as `unparsed`, a format fault.
#
# ⚑ SO THE FAILURE LOOKED LIKE A MODEL THAT CANNOT FOLLOW A JSON INSTRUCTION, AND IT WAS A NUMBER
# IN THIS FILE. That is why the kit records `output_tokens` per document and why the parse states
# distinguish `unparsed` from `offmenu`: without both, the only visible symptom is six documents
# the router "failed to classify", and the obvious next move is to rewrite the prompt.
#
# 1200 is three times the largest reply that has ever parsed here. It is a ceiling, not a quota,
# so it costs nothing on the replies that finish early — which is 114 of 120.
#
# ⚠︎ r001 WAS NOT RE-RUN AT THIS CEILING. The daily call budget was spent on the second model the
# kit standard requires, so the published r001 is the run WITH the defect, stated rather than
# quietly re-run. Its 5.0% withheld rate is six ceiling failures, not six escalations.
MAX_TOKENS = 1200

# ⚑ THE CONFIDENCE FLOOR, AND WHY IT IS A CONSTANT RATHER THAN A TUNED VALUE.
# 0.6 is a starting position, not a finding. Tuning it against this eval set and then publishing
# the tuned number would be reporting a threshold fitted to the same 120 documents it is scored
# on — the oldest way to make a router look better than it is.
#
# ⚠︎ AND ON RUN r001 IT NEVER FIRED ONCE, WHICH IS THIS KIT'S MOST IMPORTANT FINDING SO FAR.
# Measured over the 114 documents that produced a parseable answer:
#
#     every single one reported confidence >= 0.95
#     the 107 CORRECT answers   median 1.00, minimum 0.95
#     the   7 WRONG answers     median 0.95, minimum 0.95
#
# A floor of 0.6 escalates nothing. A floor of 0.95 escalates nothing. The first floor that
# catches anything is 0.99, and it escalates 49 of 114 documents — 43% of the traffic — to catch
# 6 of the 7 errors. That is not a guardrail, it is a coin flip with extra steps.
#
# ⚑ SO THE HONEST STATEMENT IS: SELF-REPORTED CONFIDENCE IS NOT CALIBRATED HERE, AND A THRESHOLD
# ON IT IS NOT A CONTROL. The mechanism is kept, unchanged and switched on, because the mechanism
# is right — a router needs somewhere to put what it should not have guessed at — and because
# deleting it would hide the finding. What is published is the floor sweep, not a chosen number.
# The next question is where a usable signal comes from instead: agreement between two models,
# disagreement with the keyword router, or a rubric the model has to fill before answering. None
# of those has been run, and none is claimed.
CONFIDENCE_FLOOR = 0.6


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def load_doc(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def decide(cfg, doc_text, complete=None, floor=CONFIDENCE_FLOOR):
    """Return the full record for one document: the decision, why, and what it cost.

    `complete` is injectable so the eval harness, the app and the stub drive the SAME path.
    """
    system, user = P.build(doc_text)
    call = complete or adapters.complete
    reply = call(cfg, system, user, max_tokens=MAX_TOKENS)
    parsed = P.parse(reply.get("text"))

    # The guardrail. A confident-enough answer is routed; anything else becomes an escalation,
    # and the record keeps BOTH — what the model said and what the system did with it — because a
    # floor that silently overwrote the model's answer would make its own effect unmeasurable.
    routed, escalated = parsed["queue"], False
    if parsed["state"] == "ok" and floor is not None:
        if parsed["confidence"] is None or parsed["confidence"] < floor:
            routed, escalated = None, True

    return {
        "model_queue": parsed["queue"],
        "routed_to": routed,
        "escalated": escalated,
        "state": parsed["state"],
        "confidence": parsed["confidence"],
        "why": parsed["why"],
        "floor": floor,
        "offered": parsed.get("offered"),
        "raw_text": parsed.get("raw", ""),
        "input_tokens": reply.get("input_tokens"),
        "output_tokens": reply.get("output_tokens"),
    }


def outcome(rec):
    """One word for what happened to a document, for the app and the run log.

    ⚠︎ `escalated` IS NOT A FAILURE AND IS NOT A SUCCESS. It is the third outcome this kit exists
    to make visible, and collapsing it into either column is how a router gets reported as 94%
    accurate while sending a third of its traffic to a human.
    """
    if rec["escalated"]:
        return "escalated"
    if rec["state"] == "abstained":
        return "abstained"
    if rec["state"] in ("offmenu", "unparsed"):
        return rec["state"]
    return "routed"


def summary_line(doc_id, rec):
    label = TX.label_of(rec["routed_to"]) if rec["routed_to"] else "—"
    conf = "%.2f" % rec["confidence"] if rec["confidence"] is not None else " n/a"
    return "%-14s %-10s %-12s conf %s" % (doc_id, outcome(rec), label, conf)


def as_json(rec):
    return json.dumps(rec, ensure_ascii=False)
