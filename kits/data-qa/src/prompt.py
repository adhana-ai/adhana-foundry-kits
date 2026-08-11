"""SEAM 5 — what the model actually receives.

Lens 05 publishes the assembled prompt IN FULL and its decomposition: every part's text must occur
in the assembled prompt, in order. So the parts are built as the string is built, from one
assembly, and there is no second code path that "describes" the prompt — a description is the
thing that drifts, and a tidy breakdown that does not match what was sent is worse than none
because it looks like evidence.

⚑ THE COST SHAPE HERE IS THE OPPOSITE OF UC001's, AND THAT IS WORTH SEEING. In a RAG kit the
retrieved passages dwarf the question, so the bill is driven by how much context you retrieve. Here
the schema card is FIXED — the same tokens on every question, however short the question is — so
the per-question bill barely moves with the question and moves a lot with the width of your
database. Two kits, two different levers, both visible in lens 07's numbers rather than asserted.
"""
SYSTEM = (
    "You write SQLite queries. Given a database schema and a question, reply with ONE SQL "
    "statement and nothing else.\n"
    "Rules:\n"
    "- Reply with SQL only. No explanation, no markdown fences, no commentary.\n"
    "- Use only the tables and columns in the schema.\n"
    "- The query must be read-only: a single SELECT (or WITH ... SELECT). Never modify data.\n"
    "- If the question cannot be answered from this schema, reply with exactly: CANNOT ANSWER"
)

# The refusal token. It is checked for exactly, and it is deliberately not SQL: a model that says
# "I cannot answer" in prose would be handed to the guard, refused as not-a-SELECT, and recorded as
# a guard block — which would blame the wrong stage. An explicit token keeps "no answer exists"
# separate from "wrote something dangerous", and the eval taxonomy depends on telling them apart.
CANNOT = "CANNOT ANSWER"


def assemble(question, schema_card):
    """Return (system, user, parts). `parts` is the decomposition lens 05 publishes."""
    parts, chunks = [], []

    head = "Database schema:\n\n"
    parts.append({"name": "instruction", "text": head})
    chunks.append(head)

    block = schema_card + "\n\n"
    parts.append({"name": "schema card", "text": block, "chars": len(block)})
    chunks.append(block)

    tail = "Question: %s\nSQL:" % question
    parts.append({"name": "question", "text": tail})
    chunks.append(tail)

    user = "".join(chunks)
    # A cheap invariant, checked rather than asserted: every part must occur in the assembled
    # prompt, in ascending position. If this fires, the decomposition is lying.
    pos = 0
    for part in parts:
        found = user.find(part["text"], pos)
        if found < 0:
            raise AssertionError("prompt part %r is not in the assembled prompt" % part["name"])
        part["offset"] = found
        pos = found
    return SYSTEM, user, parts


def clean(text):
    """Strip what models add around SQL despite being asked not to.

    ⚠︎ THIS IS NOT LENIENCE ABOUT CORRECTNESS. Fences and a leading "sql" language tag are a
    FORMATTING habit, and stripping them costs nothing. What is deliberately NOT done here is
    repairing the statement — no adding semicolons, no rewriting keywords, no picking the first of
    two statements. A pipeline that silently fixes the model's output stops measuring the model,
    and `guard.py` would then be checking something the model never wrote.
    """
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
