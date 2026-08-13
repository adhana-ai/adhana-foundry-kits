"""The verdict vocabulary and the prompt. Declared once, here, and read from here by everything.

⚑ THIS MODULE IS THE SINGLE SOURCE OF THE THREE VERDICTS. The prompt, the parser, the scorer, the
guardrail and the app panel all read `VERDICTS` from this file rather than each holding its own copy —
the same rule UC004's taxonomy and UC007's verdict list state about themselves, for the same reason: a
second copy is a silent disagreement waiting for the day somebody edits one of them.

⚑ THERE ARE THREE, AND THE THIRD IS NOT OPTIONAL. `UNSURE` exists because the corpus contains a pair no
field can settle — twins at one address with one date of birth — and the correct answer there is to say
so, not to guess. A two-verdict prompt forces a coin flip on exactly the pairs where a wrong guess is
most expensive, and then scores the flip as a decision.

⚠︎ AND `UNSURE` IS NOT THE SAME AS NO ANSWER. A model that says UNSURE has read the pair and declined;
a model that returns an empty string has failed. They are counted apart in `evals/run.py`, because the
first is a product feature (hand it to a person) and the second is a reliability problem.

THE PROMPT ASKS FOR ONE WORD AND NOTHING ELSE, which is what makes the parse deterministic. It is not
asked for a confidence number: three kits in this repo have now measured confidence figures that
carried no information (every wrong answer above 0.95 on UC004), so this one does not collect a number
it would have to caveat into meaninglessness.
"""
VERDICTS = ("SAME", "DIFFERENT", "UNSURE")

MEANS = {
    "SAME": "one entity, entered twice — safe to merge",
    "DIFFERENT": "two entities that resemble each other — must stay apart",
    "UNSURE": "the fields do not settle it; hand it to a person",
}

SYSTEM = (
    "You decide whether two customer records describe the same real person. "
    "Answer with exactly one word: SAME, DIFFERENT or UNSURE. No explanation, no punctuation."
)

RULES = (
    "Rules:\n"
    "- Nicknames, shortened forms and married or hyphenated surnames are NOT differences by "
    "themselves.\n"
    "- Abbreviated street types (Rd/Road) and email formatting are NOT differences by themselves.\n"
    "- Two people at one address with different dates of birth are DIFFERENT, however alike their "
    "names are. Relatives share addresses and surnames.\n"
    "- If the records could plausibly be two different people and no field settles it, answer "
    "UNSURE rather than guessing."
)

FIELDS = ("name", "dob", "address", "email")
LABEL = {"name": "Name", "dob": "Date of birth", "address": "Address", "email": "Email"}


def render(rec_a, rec_b):
    """The exact user message sent, field by field. Raw values, not normalised: the model is being
    asked to judge the mess a person typed, and handing it tidied strings would be measuring a
    different pipeline from the one the app runs."""
    lines = ["Record A:"]
    lines += ["  %s: %s" % (LABEL[f], rec_a.get(f, "") or "(missing)") for f in FIELDS]
    lines += ["", "Record B:"]
    lines += ["  %s: %s" % (LABEL[f], rec_b.get(f, "") or "(missing)") for f in FIELDS]
    lines += ["", RULES, "", "One word:"]
    return "\n".join(lines)


def parse(reply):
    """A verdict, or None when nothing usable came back.

    ⚠︎ None IS A THIRD OUTCOME AND MUST NOT DEFAULT TO 'DIFFERENT'. Falling back to DIFFERENT would be
    the safe-looking choice — it never merges anything — and it would silently convert every failed
    call into a missed match, hiding a reliability problem inside a quality number. `evals/run.py`
    counts these in their own bucket.
    """
    if not reply:
        return None
    up = reply.strip().upper()
    for v in VERDICTS:                       # a bare word first, so "SAME." and "SAME" agree
        if up.rstrip(".!,").strip() == v:
            return v
    hits = [v for v in VERDICTS if v in up]
    return hits[0] if len(hits) == 1 else None
