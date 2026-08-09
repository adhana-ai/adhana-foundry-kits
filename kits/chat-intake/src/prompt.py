"""The one prompt this kit sends, and the contract its answer has to satisfy.

⚑ THE MODEL IS ASKED TO EXTRACT, NOT TO DECIDE. It reads the conversation so far and reports which
required facts have been established and with what values. Whether that is ENOUGH is then computed
in `src/slots.missing()` — pure code, a set difference.

⚠︎ THAT SPLIT IS THE DESIGN, AND IT IS WORTH DEFENDING BECAUSE THE OTHER WAY IS THE OBVIOUS ONE.
Asking the model "should you ask again?" hands the one deterministic step in the pipeline to the
component that cannot be held to it. The checklist is known in advance and set arithmetic is not a
judgement call; a model that says "I have enough" while its own extracted list is short of the
checklist is a model contradicting itself, and there is no reason to let it. So the model owns the
part only a model can do — reading natural language — and the decision stays in code where it can
be audited, tested offline and never varies between runs.

⚑ WHICH ALSO MAKES THE EVAL FREE. Because the decision is derived, scoring it needs no judge: the
gold slot values come from the dataset's own dialogue state and the comparison is `==`.
"""
import json

from . import slots

# ⚑ THE OUTPUT CONTRACT, DECLARED ONCE. The prompt below quotes these keys, `intake.py` parses
# them, and `evals/judge.py` scores them. A key changed in one place and not the others is the
# drift this single declaration exists to prevent.
KEYS = ("collected", "notes")

SYSTEM = (
    "You read a customer-service conversation and report which required facts the customer has "
    "already given. You do not decide whether the conversation is finished, you do not ask the "
    "next question, and you do not guess. Report only what the conversation actually establishes."
)

# ⚠︎ "OMIT, DO NOT INVENT" IS THE LOAD-BEARING INSTRUCTION. The expensive failure on this task is a
# fact recorded as collected when nobody said it: the checklist then reads as full, the pipeline
# stops asking, and the value is never confirmed by anyone. An omission is recoverable by one more
# turn; a confident wrong value is not recoverable at all.
RULES = (
    "Rules:\n"
    "- Report a fact ONLY if the customer stated it in the conversation. If it has not been "
    "stated, leave it out entirely. Never guess, never infer from what is likely, and never fill "
    "a plausible default.\n"
    "- An omitted fact costs one more question. A wrong fact is never caught, because the "
    "checklist will read as complete and nothing downstream will ask again.\n"
    "- Copy the customer's own value. Do not normalise, expand, abbreviate or correct it.\n"
    "- Report only the facts on the required list below. Ignore anything else the conversation "
    "contains.\n"
)


def render(intent, turns):
    """The whole prompt for one turn of one conversation, assembled verbatim.

    `turns` is the conversation SO FAR — the prefix. The kit re-sends it each turn rather than
    keeping a server-side session, which is what keeps this inside the four layers a kit is
    allowed: there is no store, no session id and nothing that outlives the request.
    """
    need = slots.required(intent)
    lines = "\n".join("%s: %s" % (t["speaker"].title(), t["utterance"]) for t in turns)
    return (
        "%s\n\n"
        "The customer wants to: %s\n\n"
        "Required facts, and nothing else counts:\n%s\n\n"
        "%s\n"
        "Conversation so far:\n%s\n\n"
        "Answer with JSON only, no prose and no code fence:\n"
        '{\"collected\": {\"<fact name>\": \"<the customer\'s own words>\"}, '
        '\"notes\": \"<one short line, or an empty string>\"}\n'
        % (SYSTEM, intent, "\n".join("- %s" % s for s in need), RULES, lines))


def parse(text):
    """The model's reply -> {collected: {...}, notes: str}, or None if it did not answer the shape.

    ⚠︎ A REFUSAL TO PARSE IS A RESULT, NOT AN EXCEPTION, and it is counted separately from a wrong
    answer everywhere downstream. Folding an unparseable reply into "collected nothing" would score
    a broken response exactly like a careful model that correctly found nothing yet — and those are
    opposite outcomes.
    """
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        return None
    try:
        out = json.loads(s[i:j + 1])
    except ValueError:
        return None
    if not isinstance(out, dict) or not isinstance(out.get("collected"), dict):
        return None
    # Values are stringified here rather than at the call site so the scorer never has to think
    # about whether a model returned 100 or "100".
    return {"collected": {str(k): str(v) for k, v in out["collected"].items()},
            "notes": str(out.get("notes") or "")}
