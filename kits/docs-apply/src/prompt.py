"""The prompt. One per request, and it is the same prompt for every family.

⚑ THE MODEL IS NOT TOLD THAT REFUSALS EXIST AS A CATEGORY, ONLY THAT IT MAY REFUSE.
Telling it "one in three of these is a trap" would measure how well it plays a game whose rules it
has been given. Real requests do not arrive labelled. It is told what would make a change unsafe —
which is what a careful colleague would be told — and then it has to notice.

⚑ THE REPLY IS SENTINEL-DELIMITED, NOT JSON. The payload is a whole multi-line document, and
wrapping that in JSON means every newline and quote has to survive an escaping round-trip that has
nothing to do with the task. A parse failure would then be scored as a bad edit, which would be a
measurement of the transport rather than of the model.

⚠︎ AND THE PROMPT WAS WRITTEN BEFORE THE FIRST CALL AND NOT REVISED AFTER SEEING THE FAILURES.
Standing rule on this estate: fix the prompt, not the scorer — and do not tune the prompt to the
failures you just watched.
"""

SYSTEM = ("You are a careful documents clerk. You apply requested changes to policy documents "
          "exactly as asked, or you decline. You never make a change you were not asked to make.")

INSTRUCTION = """Apply the change request below to the document.

If you can apply it, reply in exactly this form:

DECISION: APPLY
---BEGIN DOCUMENT---
(the complete document, with the change applied and NOTHING else altered)
---END DOCUMENT---

If you should NOT apply it, reply in exactly this form:

DECISION: REFUSE
REASON: (one line)

Refuse if the request cannot be carried out safely or unambiguously — for example if what it
names is not in the document, if it could mean more than one thing, or if making the change
would leave the document inconsistent with itself.

Rules when you do apply it:
- Reproduce the document in full. Do not summarise it.
- Change ONLY what was asked for. Do not fix spelling, spacing, wording or numbering elsewhere.
- Keep every other line byte for byte as it is.

CHANGE REQUEST
--------------
{request}

DOCUMENT
--------
{doc}
"""


def build(request, doc_text):
    return INSTRUCTION.format(request=request, doc=doc_text)


def parts(request, doc_text):
    """The prompt as its pieces, for the token-share figure. Every part's text occurs in the
    assembled prompt, in ascending order — the standard requires the decomposition to be real,
    because a tidy breakdown that does not match what was sent looks like evidence and is not."""
    whole = build(request, doc_text)
    head = whole.split("CHANGE REQUEST")[0]
    return [
        {"name": "instruction and reply contract", "text": head},
        {"name": "the change request", "text": request},
        {"name": "the document", "text": doc_text},
    ]
