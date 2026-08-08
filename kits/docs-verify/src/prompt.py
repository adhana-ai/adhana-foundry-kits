"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER DOCUMENT, NOT PER CLAIM. Every claim about a document is checked against that
document in a single call. The alternative — one call per claim — would have sent the same source
text 8 to 10 times over, for the same answer, at roughly nine times the input cost. The document
is the expensive token payload here and the claims are short; batching them is the whole reason
this kit is cheap enough to run twice.

⚠︎ THE MODEL IS ASKED FOR A VERDICT AND A QUOTE, AND THE QUOTE IS NOT DECORATION. A verdict on its
own cannot be checked by a reader — "contradicted" with no sentence beside it is an assertion, and
this kit exists to be sceptical of assertions. Requiring the model to name the sentence it relied
on also does real work on the model's side: it is much harder to confabulate support for an absent
claim when you have to produce the line that provides it.
"""
import json

# The three verdicts, and the definitions the model is held to. `not_stated` is defined FIRST in
# the system prompt's list rather than last, because it is the one a model will otherwise collapse
# into `contradicted` -- "the document doesn't say this" and "the document says otherwise" are the
# same answer to a careless reader and opposite answers to a useful one.
VERDICTS = ("supported", "contradicted", "not_stated")

# ⚑ THE VERDICT VOCABULARY IS DECLARED ONCE, HERE, AND EVERYTHING READS IT FROM HERE. The prompt
# below builds its own definition block from this dict rather than restating it, `parse()` accepts
# nothing outside `VERDICTS`, `evals/judge.py` scores these three and no others, and the site's
# app panel reads this module by AST rather than shipping a `data/verdicts.json` beside it. A
# second copy of a class list is the thing that drifts from the scorer, and a class list that has
# drifted from the scorer is worse than no panel at all.
#
# `costs` is what getting THIS verdict wrong does to whoever trusts it. It is written down for the
# same reason the two failure directions are written on docs-redact's panel: the mistakes are not
# interchangeable, and a single accuracy figure hides which one you are making.
VERDICT_MEANINGS = {
    "not_stated": {
        "means": "The document neither asserts nor denies this. It may be entirely plausible; "
                 "that is irrelevant. If the document simply does not address it, this is the "
                 "answer.",
        "costs": "Called anything else, a hallucination stops being visible. This is the class "
                 "the kit exists to separate, and the one a two-verdict checker cannot express.",
    },
    "supported": {
        "means": "The document states this, or states something that plainly entails it.",
        "costs": "A FALSE SUPPORT is the expensive error: an unbacked claim goes out with a "
                 "confident tick on it. Counted separately from accuracy in evals/judge.py.",
    },
    "contradicted": {
        "means": "The document states something incompatible with this.",
        "costs": "Called not_stated instead, a real error the source WOULD have caught is "
                 "downgraded to a shrug and nobody goes back to check it.",
    },
}

# not_stated is defined FIRST, ahead of the other two, because it is the one a model will otherwise
# collapse into contradicted -- "the document doesn't say this" and "the document says otherwise"
# are the same answer to a careless reader and opposite answers to a useful one.
_DEFS = "".join(
    "  %-12s %s\n" % (name, VERDICT_MEANINGS[name]["means"])
    for name in ("not_stated", "supported", "contradicted"))

SYSTEM = (
    "You check claims against a source document. You are given one document and a numbered list "
    "of claims about it. For each claim, decide which of exactly three verdicts applies, using "
    "ONLY the document -- never outside knowledge, and never what is likely to be true of studies "
    "in general.\n"
    "\n"
    + _DEFS +
    "\n"
    "The distinction between not_stated and contradicted matters more than any other judgement "
    "you will make here. A claim the document is silent about is NOT contradicted. Do not reach "
    "for a nearby sentence that is merely on the same topic.\n"
    "\n"
    "For supported and contradicted, quote the sentence or line from the document you relied on, "
    "verbatim. For not_stated, the quote must be an empty string -- do not offer the closest "
    "line, because a quote that does not decide the claim reads as evidence and is not."
)


def build(doc_text, claims):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes.

    THE PARTS ARE A REAL DECOMPOSITION, NOT A TIDY BREAKDOWN — same rule docs-extract's and
    docs-redact's build() follow: every part's text occurs verbatim in what is sent, in this order.
    """
    numbered = "\n".join("%d. %s" % (i + 1, c["text"]) for i, c in enumerate(claims))
    user = ("Check each claim below against the document.\n\n"
            "Return a JSON object with one key, \"verdicts\", a list with one entry per claim in "
            "the same order, each {\"n\": <claim number>, \"verdict\": <one of: %s>, "
            "\"quote\": <verbatim line from the document, or \"\">}.\n\n"
            "CLAIMS\n------\n%s\n\n"
            "DOCUMENT\n--------\n%s\n" % (", ".join(VERDICTS), numbered, doc_text))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "claims", "text": numbered},
        {"name": "document", "text": doc_text},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts)


def parse(raw, n_claims):
    """Pull the verdict list out of a model reply, tolerantly but never creatively.

    Same discipline as every sibling kit's parse(): a reply that does not parse yields nothing —
    read as "this call produced no answer", never as evidence about the document — and never a
    fallback that scrapes plausible-looking verdicts out of the raw text with a regex. That would
    silently turn a broken call into a mediocre checker, and the run record would show a system
    that half-worked instead of one that failed.

    ⚠︎ A MISSING CLAIM IS RETURNED AS None, NOT AS not_stated. They are easy to confuse and the
    difference is the whole point of the kit: `not_stated` is a judgement the model made, None is
    a judgement it never delivered. Scoring them the same way would let a model that answered
    nothing at all inherit the credit for every genuinely absent claim in the set.
    """
    out = [None] * n_claims
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    for v in (obj.get("verdicts") or []):
        if not isinstance(v, dict):
            continue
        try:
            i = int(v.get("n", 0)) - 1
        except (TypeError, ValueError):
            continue
        if not (0 <= i < n_claims):
            continue
        verdict = str(v.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if verdict not in VERDICTS:
            continue
        out[i] = {"verdict": verdict, "quote": str(v.get("quote", "") or "")}
    return out
