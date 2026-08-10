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
    "- Where a fact lists allowed values, answer with exactly one of them. Where it does not, "
    "copy the customer's own words and do not normalise, expand, abbreviate or correct them.\n"
    "- Report only the facts on the required list below. Ignore anything else the conversation "
    "contains.\n"
)


def one_line(utterance):
    """One turn renders as exactly one line. Collapse every run of whitespace, newlines included.

    ⚠︎ THIS IS A SECURITY FIX AND IT IS THE WHOLE OF ONE. The conversation is laid out below as
    `Speaker: utterance`, so before this existed an utterance containing a newline and the word
    `System:` rendered as an extra line in the SYSTEM's voice — a turn the customer wrote and the
    model had no way to tell from the transcript around it. The red team measured what that buys:
    the reply came back empty on 5 of 5 attempts, `finish_reason=length`, with 100% of the output
    ceiling spent on a reasoning pass the provider bills and never returns. Raising the ceiling
    four-fold billed four times as much for the same silence.

    ⚑ COLLAPSING IS THE FIX, NOT STRIPPING OR REFUSING. Nothing is removed — every word the
    customer typed still reaches the model, in their own words, which rule 3 of RULES requires and
    which a filter that deleted suspicious text would break. What is removed is the STRUCTURE:
    after this, a forged `System:` is a phrase inside a line clearly attributed to the customer,
    which is a claim rather than a forgery. The kit already resists customer claims — being told
    to stop asking, being told the facts are on file, being told they were given three times, all
    held at 100% across every run.

    ⚠︎ AND IT CHANGES THE SHIPPED PROMPT, so every number measured against the old one is stale
    the moment this lands. That is why the fix waited for a decision rather than being slipped in:
    the cost was never the line, it was re-measuring 16 published pages.
    """
    return " ".join(str(utterance).split())


def render(intent, turns):
    """The whole prompt for one turn of one conversation, assembled verbatim.

    `turns` is the conversation SO FAR — the prefix. The kit re-sends it each turn rather than
    keeping a server-side session, which is what keeps this inside the four layers a kit is
    allowed: there is no store, no session id and nothing that outlives the request.
    """
    need = slots.required(intent)
    allowed = slots.values(intent)
    about = slots.descriptions(intent)
    # ⚑ A CLOSED-VOCABULARY SLOT IS SHOWN WITH ITS VOCABULARY — added after r001, which scored 18
    # of 28 stated facts wrong purely because the model answered "savings account" and the schema
    # says "savings". A free-text slot (`amount`, `recipient_account_name`) has no list and still
    # takes the customer's own words, which is why the copy-verbatim rule below stays.
    #
    # ⚑ AND EVERY SLOT IS SHOWN WITH THE SCHEMA'S OWN DESCRIPTION — added after r005/r006, the same
    # shape of finding one step further in. r001 was the model not knowing what a slot's ANSWERS may
    # be; this is the model not knowing what the slot IS. 6 of the 9 wrong facts on the full 298 were
    # the recipient's account type filed under `account_type` — a slot the schema defines as "the
    # account type of the USER", beside a separate optional `recipient_account_type` the checklist
    # never mentions. From the bare identifier that substitution is not a mistake, it is the only
    # available reading, and both tiers made it on exactly the same cases.
    #
    # ⚠︎ THE DESCRIPTION IS THE DATASET'S, NOT A HINT WE WROTE. Nothing here says "do not confuse
    # these two slots", which is what a fix tuned to the observed failure would say — that is
    # teaching to the test, and it would not survive the corpus being swapped. Handing over the
    # schema's own gloss is the general fix: it costs about 8 input tokens per slot, it needs no
    # maintenance, and the unseen-schema probe picks up Banks_2's wording with no code change.
    need_lines = "\n".join(
        "- %s%s%s" % (s,
                      ("  — %s" % about[s]) if about.get(s) else "",
                      ("  (answer with exactly one of: %s)" % ", ".join(allowed[s]))
                      if allowed.get(s) else "")
        for s in need)
    lines = "\n".join("%s: %s" % (t["speaker"].title(), one_line(t["utterance"])) for t in turns)
    return (
        "%s\n\n"
        "The customer wants to: %s\n\n"
        "Required facts, and nothing else counts:\n%s\n\n"
        "%s\n"
        "Conversation so far:\n%s\n\n"
        "Answer with JSON only, no prose and no code fence:\n"
        '{\"collected\": {\"<fact name>\": \"<the customer\'s own words>\"}, '
        '\"notes\": \"<one short line, or an empty string>\"}\n'
        % (SYSTEM, intent, need_lines, RULES, lines))


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
