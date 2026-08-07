"""What a flagged change means, and what routing it triggers.

⚑ THIS FILE IS THE USE CASE, THE SAME WAY taxonomy.py IS docs-route's. Every other kit here
either answers a question or fills a field; this one draws a line between two changes that read
almost identically on the page and mean very different things to a person who has to act on one
of them. The levels are written down once, with what each one costs to get wrong, and everything
downstream — the prompt, the scorer, the guardrail — reads them from here.

⚠︎ UNLIKE docs-route's queues, THESE ARE NOT THE PUBLISHER'S LABEL. The Office of the Federal
Register does not grade its own corrections "material" or "editorial" — it just publishes the
fix. So this kit cannot score materiality the way docs-route scores a queue, by `==` against a
field somebody else already filled in, and it does not pretend otherwise: see evals/score.py and
Eval.could_not_verify on the published kit for what that honestly costs.
"""

# key -> (label, what calling it this actually costs to get wrong)
LEVELS = {
    "material": (
        "Material",
        "Changes an obligation, a deadline, a number, a legal citation, or an amount — something "
        "a regulated party would act on differently. Missing one of these is the expensive "
        "direction: a compliance deadline that quietly moved and nobody re-read the notice.",
    ),
    "editorial": (
        "Editorial",
        "Wording, formatting, punctuation, or an internal cross-reference — corrects how the rule "
        "reads without changing what it requires. Flagging one of these as material wastes a "
        "reviewer's morning on a typo.",
    ),
}

ORDER = ["material", "editorial"]

# What the model must answer with when it will not choose. Scored as its own outcome — see
# evals/score.py — not folded into either level.
ABSTAIN = "unsure"


def label_of(key):
    return LEVELS[key][0]


def meaning(key):
    return LEVELS[key][1]


def labels():
    return list(ORDER)
