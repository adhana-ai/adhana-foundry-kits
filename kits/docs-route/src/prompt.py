"""Build the one message pair that asks for a routing decision. Pure code, no model.

⚑ THE PROMPT IS GENERATED FROM `taxonomy.py`, NEVER TYPED OUT HERE. Three copies of a class list —
one in the prompt, one in the scorer, one in the baseline — is three chances for a kit to grade a
model against options it was never offered. That failure is invisible: the model answers something
reasonable, the scorer calls it wrong, and the confusion matrix looks like a model problem.

⚑ IT ASKS FOR A CONFIDENCE AND AN ABSTENTION, WHICH IS THE WHOLE DIFFERENCE BETWEEN A CLASSIFIER
AND A ROUTER. A classifier's job is to be right. A router's job is to be right OR to get out of the
way, because the cost of the two mistakes is not the same: a proposed rule filed as a notice
forfeits the comment window silently, and a notice escalated to the legal queue costs somebody an
hour. So the model is given a way to say it will not choose, and `evals/score.py` reports what it
declined separately from what it got wrong. A kit that only reported accuracy would be unable to
tell "wrong" from "sensibly unsure", and those have opposite fixes.

⚠︎ AND THE ABSTENTION IS NOT FREE — see score.py. Abstaining on everything scores zero accuracy,
so the option cannot be used to dodge the measurement; it can only move a document from the wrong
column into a column that says a person must look.
"""
import json

from . import taxonomy as TX

SYSTEM = (
    "You are a routing desk for incoming regulatory documents. You read one document and send it "
    "to exactly one queue. You do not summarise it, you do not advise on it, and you do not "
    "explain the regulation — a downstream reader does that. Your only job is the queue."
)


def _queue_block():
    """The options, with what each one commits the organisation to. The MEANING is included on
    purpose: 'Rule / Proposed Rule / Notice' are three labels a model can pattern-match, while
    'binding / still open for comment / for information' is the decision actually being made, and
    the second framing is the one that survives a document whose wording is unusual."""
    lines = []
    for key in TX.ORDER:
        lines.append('  "%s"  (%s) — %s' % (key, TX.label_of(key), TX.meaning(key)))
    lines.append('  "%s" — you are not confident enough to choose. A person will read it.'
                 % TX.ABSTAIN)
    return "\n".join(lines)


def build(doc_text):
    """Return (system, user). One document in, one decision out — no history, no examples.

    ⚠︎ ZERO-SHOT ON PURPOSE, AND IT IS A MEASUREMENT CHOICE RATHER THAN A SHORTCUT. Adding three
    worked examples would very likely raise the score, and it would also mean the kit publishes a
    number that belongs to the examples somebody picked. The question this kit asks is what a
    model does with the taxonomy alone; few-shot is the obvious next run, and it is a different
    run rather than a better version of this one.
    """
    user = (
        "Route this document to one queue.\n\n"
        "QUEUES:\n%s\n\n"
        "Answer with JSON only, in this exact shape:\n"
        '{"queue": "<one key from the list above>", "confidence": <0.0 to 1.0>, '
        '"why": "<one short sentence, at most 20 words>"}\n\n'
        "DOCUMENT:\n%s"
    ) % (_queue_block(), doc_text.strip())
    return SYSTEM, user


def parse(text):
    """Reply -> {queue, confidence, why, state}. Never raises: a malformed reply is a RESULT.

    The four states are distinguished because they need different fixes and a single `error`
    bucket hides which one you have:
      ok          a valid queue key came back
      abstained   the model declined, in the word the prompt asked for
      offmenu     valid JSON, but a queue this kit does not have — a prompt problem
      unparsed    not JSON at all — a format problem, usually a ceiling or a chatty model
    """
    raw = (text or "").strip()
    # Models fence JSON in markdown more often than not, and a kit that treated that as a failure
    # would be publishing a measurement of fencing habits.
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    try:
        obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return {"queue": None, "confidence": None, "why": "", "state": "unparsed",
                "raw": (text or "")[:400]}
    queue = str(obj.get("queue") or "").strip().lower()
    conf = obj.get("confidence")
    try:
        conf = round(float(conf), 3)
    except (TypeError, ValueError):
        conf = None
    why = str(obj.get("why") or "").strip()
    if queue == TX.ABSTAIN:
        return {"queue": None, "confidence": conf, "why": why, "state": "abstained"}
    if queue in TX.QUEUES:
        return {"queue": queue, "confidence": conf, "why": why, "state": "ok"}
    return {"queue": None, "confidence": conf, "why": why, "state": "offmenu",
            "offered": queue[:60]}
