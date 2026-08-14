"""The prompt. One per document, identical in both conditions.

⚑ IDENTICAL IN BOTH CONDITIONS IS THE WHOLE EXPERIMENT. The temptation is to tell the model "this
page came off a scanner, expect noise" on the messy half — and that would measure a different
thing: how well a model does when it is WARNED. Real pipelines do not know which of their inputs
came back clean. The page changes; nothing else does.

⚠︎ AND THE PROMPT IS NOT TUNED TO THE OBSERVED FAILURES. Standing rule on this estate: fix the
prompt, not the scorer, and do not tune the prompt to the failures you just watched. This wording
was written before the first call and is what shipped.
"""
import json

SYSTEM = (
    "You read one business document and return the fields asked for, as JSON. "
    "You return only JSON: no explanation, no code fence, no commentary."
)

INSTRUCTION = """Read the document below and return this JSON object:

{fields}

Rules:
- Copy values as the document states them. Do not reformat except where a field says to.
- If the document does not state a field, return null for it. Do not guess, and do not
  substitute a similar-looking value from elsewhere on the page.
- Return the JSON object and nothing else.

DOCUMENT
--------
{doc}
"""


def build(fields, doc_text):
    shape = "{\n" + ",\n".join(
        '  "%s": null,   // %s %s' % (f["key"], f["label"], f["hint"]) for f in fields) + "\n}"
    return INSTRUCTION.format(fields=shape, doc=doc_text)


def parts(fields, doc_text):
    """The prompt as its pieces, for the token-share figure. Every part's text occurs in the
    assembled prompt, in order — the standard requires the decomposition to be real, because a
    tidy breakdown that does not match what was sent looks like evidence and is not."""
    whole = build(fields, doc_text)
    head = whole.split("DOCUMENT")[0]
    return [
        {"name": "instruction and field shape", "text": head},
        {"name": "the document", "text": doc_text},
    ]
