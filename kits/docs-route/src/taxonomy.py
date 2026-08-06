"""The routing taxonomy: the queues a document can land in, and what landing there MEANS.

⚑ THIS FILE IS THE USE CASE. Every other kit here consumes a document and produces prose or
fields; this one produces a DECISION, and a decision is only as good as the options it chooses
between. So the classes are written down once, with the action each one triggers, and everything
downstream — the prompt, the baseline, the scorer, the guardrail — reads them from here. A class
list that lives in a prompt string is a class list that the scorer cannot check against.

⚠︎ THE CLASSES ARE THE PUBLISHER'S, NOT MINE. `type` is a field the Office of the Federal Register
assigns to every document it prints; it is not a label I invented and then graded a model against.
That distinction is the whole reason this kit can be scored by machine while UC003 cannot: there
is a gold answer, somebody else wrote it, and it was not written with this eval in mind.

⚑ WHY PRESIDENTIAL DOCUMENTS ARE NOT A FOURTH CLASS, MEASURED RATHER THAN ASSUMED.
The Federal Register prints four types and this kit routes three. Presidential Documents were
pulled and counted: 20 of 20 sampled carry NO abstract, where Rules, Proposed Rules and Notices
carry one 20 of 20, 20 of 20 and 17 of 20 respectively. Including them would have meant one class
whose input is a bare title against three whose input is a paragraph — and then the confusion
matrix would be measuring which documents happen to have an abstract, not which queue they belong
in. That is a corpus artefact wearing the costume of a result. They are excluded, in one place,
with the count that decided it.
"""

# key -> (label, what routing here actually commits you to)
QUEUES = {
    "rule": (
        "Rule",
        "BINDING. A final rule is already law or is about to be; the comment window has closed. "
        "This queue is the one with a deadline attached — somebody has to read it against what "
        "the organisation currently does and say whether anything must change.",
    ),
    "proposed": (
        "Proposed Rule",
        "OPEN FOR COMMENT. Nothing binds yet, and there is a window in which saying something is "
        "still possible. Routing a proposed rule to the binding queue wastes a lawyer's morning; "
        "routing it to the FYI queue silently forfeits the only chance to influence it, which is "
        "the more expensive of the two mistakes and the reason this class exists separately.",
    ),
    "notice": (
        "Notice",
        "FOR INFORMATION. Meetings, filings, applications, statements of policy. The overwhelming "
        "majority of what the Federal Register prints, and the queue whose job is to stay boring.",
    ),
}

ORDER = ["rule", "proposed", "notice"]

# What the model must answer with when it will not choose. NOT a fourth class: it is a refusal,
# and it is scored as one — see evals/score.py, which reports abstentions apart from errors
# because "I don't know" and "wrong" are different failures with different fixes.
ABSTAIN = "unsure"

# The publisher's own spelling of each class, as it arrives from the API. The gold label is
# translated into a queue key exactly once, here, so a change in the API's wording is a one-line
# fix rather than a hunt through a prompt, a scorer and a baseline.
FROM_SOURCE = {
    "Rule": "rule",
    "Proposed Rule": "proposed",
    "Notice": "notice",
}


def labels():
    """The queue keys, in a fixed order. Fixed because the confusion matrix's rows and columns
    are read positionally by anything that renders it, and a dict's order is not a contract."""
    return list(ORDER)


def label_of(key):
    return QUEUES[key][0]


def meaning(key):
    return QUEUES[key][1]


def from_source(raw):
    """The publisher's type -> a queue key, or None if it is a type this kit does not route.

    Returning None rather than raising is deliberate: `tools/build_corpus.py` uses it to FILTER,
    and a document of an unrouted type is a normal thing to meet in a fetch, not an error.
    """
    return FROM_SOURCE.get((raw or "").strip())
