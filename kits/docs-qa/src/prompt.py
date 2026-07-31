"""SEAM 5 — what the model actually receives.

Lens 05 publishes the assembled prompt IN FULL, and publishes its decomposition: every part's text
must occur in the assembled prompt, in order, and the parts' token counts must sum to the input
total. That gate exists because a tidy breakdown that does not match what was really sent is the
worst kind of wrong -- it looks like evidence.

So this file returns the parts and the whole together, from one assembly. There is no second code
path that "describes" the prompt, because a description is the thing that drifts.
"""
SYSTEM = (
    "You answer questions using only the provided document passages.\n"
    "If the passages do not contain the answer, say so plainly and do not guess.\n"
    "Cite the passage number you used, like [2]."
)


def assemble(question, passages):
    """Return (system, user, parts). `parts` is the decomposition lens 05 publishes.

    The parts are built as the string is built, so they cannot disagree with it. The cost lesson
    lands here and is visible in the numbers: the retrieved passages dwarf the question, which is
    why a per-query bill is driven by how much context you retrieve, not by what the user typed.
    """
    parts, chunks = [], []

    head = "Answer the question using only these passages.\n\n"
    parts.append({"name": "instruction", "text": head})
    chunks.append(head)

    for i, p in enumerate(passages, 1):
        block = "[%d] %s (%s)\n%s\n\n" % (i, p["doc"], p["format"], p["text"])
        parts.append({"name": "passage %d" % i, "text": block, "doc": p["doc"],
                      "chunk": p["id"], "score": p.get("score")})
        chunks.append(block)

    tail = "Question: %s\n" % question
    parts.append({"name": "question", "text": tail})
    chunks.append(tail)

    user = "".join(chunks)
    # A cheap invariant, checked rather than asserted in prose: every part must occur in the
    # assembled prompt, in ascending position. If this ever fires, the decomposition is lying.
    pos = 0
    for part in parts:
        found = user.find(part["text"], pos)
        if found < 0:
            raise AssertionError("prompt part %r is not in the assembled prompt" % part["name"])
        part["offset"] = found
        pos = found
    return SYSTEM, user, parts
