"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER DOCUMENT, NOT PER RULE. All 41 rules are checked against a document in a single call.
The alternative — one call per rule — would have sent the same document 41 times for the same
answer, at roughly forty times the input cost. The document is the expensive token payload and the
rules are short, so batching them is the whole reason this kit is cheap enough to run twice.

⚠︎ THE MODEL IS ASKED FOR A VERDICT AND A QUOTE, AND THE QUOTE IS NOT DECORATION. A verdict on its
own cannot be checked by a reader — "breached" with no line beside it is an assertion, and this kit
exists to be sceptical of assertions. Requiring the model to name the line it relied on also does
real work on the model's side: it is much harder to confabulate a satisfied requirement when you
have to produce the line that satisfies it.

⚑ WHY ALL 41 RULES ARE SENT, INCLUDING THE ONES THAT DO NOT BIND THIS DOCUMENT. Applicability is
computed in the gold set from STRUCTURED fields — whether the trial is FDA-regulated, whether it
was terminated — and a deployment holding only the document does not have those. Filtering the
prompt down to the applicable rules would quietly hand the model a fact it is supposed to be
working without, and would flatter every number the eval prints. So the model sees the whole
rulebook, answers in the three verdicts the panel shows, and `evals/judge.py` drops the rules the
regulation does not bind before scoring. The model is never asked to judge applicability.
"""
import json

# The three verdicts, and the definitions the model is held to. `never_addressed` is defined FIRST
# because it is the one a model will otherwise collapse into `breached` — "the document doesn't say"
# and "the document says something deficient" are the same answer to a careless reader and opposite
# answers to a useful one. They also have opposite remedies: one is a missing statement to write,
# the other a wrong statement to correct.
VERDICTS = ("met", "breached", "never_addressed")

# ⚑ THE VERDICT VOCABULARY IS DECLARED ONCE, HERE, AND EVERYTHING READS IT FROM HERE. The prompt
# below builds its definition block from this dict rather than restating it, `parse()` accepts
# nothing outside `VERDICTS`, `evals/judge.py` scores these three and no others, and the site's app
# panel reads this module rather than shipping a `data/verdicts.json` beside it. A second copy of a
# class list is the thing that drifts from the scorer, and a class list that has drifted from the
# scorer is worse than no panel at all.
#
# `costs` is what getting THIS verdict wrong does to whoever trusts it. Written down for the same
# reason docs-redact's two failure directions are on its panel: the mistakes are not
# interchangeable, and a single accuracy figure hides which one you are making.
VERDICT_MEANINGS = {
    "never_addressed": {
        "means": "The document is silent on this requirement. No line addresses it, so no line "
                 "can be quoted. Plausibility is irrelevant — if the document does not speak to "
                 "the requirement, this is the answer.",
        "costs": "Called met, a mandatory disclosure that was never made disappears entirely — "
                 "nobody goes looking for a rule the checker said was fine. Called breached, "
                 "someone is sent to correct a statement that does not exist.",
    },
    "met": {
        "means": "The document satisfies the requirement, and a line in it says so.",
        "costs": "A FALSE MET ships a breach with a tick on it. This is the expensive error and "
                 "it is counted separately from accuracy in evals/judge.py.",
    },
    "breached": {
        "means": "The document ADDRESSES the requirement and fails it — a statement exists and "
                 "falls short of what the rule asks for.",
        "costs": "A compliant document sent back for rework, and a reviewer who stops trusting "
                 "the checker after the second false alarm.",
    },
}

_DEFS = "".join(
    "  %-16s %s\n" % (name, VERDICT_MEANINGS[name]["means"])
    for name in ("never_addressed", "met", "breached"))

SYSTEM = (
    "You check one document against a fixed rulebook. You are given a numbered list of rules "
    "transcribed from a federal regulation, and one document. For each rule, decide which of "
    "exactly three verdicts applies, using ONLY the document -- never outside knowledge, and "
    "never what is likely to be true of documents of this kind in general.\n"
    "\n"
    + _DEFS +
    "\n"
    "The distinction between never_addressed and breached matters more than any other judgement "
    "you will make here, because the two have different remedies: one is a missing statement "
    "someone must write, the other a wrong statement someone must correct. A requirement the "
    "document is silent about is NOT breached. Do not reach for a nearby line that is merely on "
    "the same topic.\n"
    "\n"
    "For met and breached, quote the line from the document you relied on, verbatim. For "
    "never_addressed the quote MUST be an empty string -- do not offer the closest line, because "
    "a quote that does not decide the rule reads as evidence and is not.\n"
    "\n"
    "Some rules will not be relevant to this document. Judge them on the document anyway: if the "
    "document says nothing about the requirement, that is never_addressed."
)


def rule_line(r):
    """One rule as the model sees it. The citation travels with the rule so a verdict can be
    traced back to the paragraph that imposes it without a second lookup."""
    text = "[%s] %s — %s" % (r["id"], r["cite"], r["requirement"])
    if r.get("definition"):
        text += " The regulation defines %r as: %s" % (r["element"], r["definition"])
    if r.get("applies_note"):
        text += " (The regulation qualifies this element: %s.)" % r["applies_note"]
    return text


def build(doc_text, rules):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes.

    THE PARTS ARE A REAL DECOMPOSITION, NOT A TIDY BREAKDOWN — same rule every sibling kit's
    build() follows: every part's text occurs verbatim in what is sent, in this order.
    """
    numbered = "\n".join("%d. %s" % (i + 1, rule_line(r)) for i, r in enumerate(rules))
    user = ("Check the document below against each rule.\n\n"
            "Return a JSON object with one key, \"verdicts\", a list with one entry per rule in "
            "the same order, each {\"n\": <rule number>, \"verdict\": <one of: %s>, "
            "\"quote\": <verbatim line from the document, or \"\">}.\n\n"
            "RULEBOOK\n--------\n%s\n\n"
            "DOCUMENT\n--------\n%s\n" % (", ".join(VERDICTS), numbered, doc_text))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "rulebook", "text": numbered},
        {"name": "document", "text": doc_text},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts)


def parse(raw, n_rules):
    """Pull the verdict list out of a model reply, tolerantly but never creatively.

    Same discipline as every sibling kit's parse(): a reply that does not parse yields nothing —
    read as "this call produced no answer", never as evidence about the document — and never a
    fallback that scrapes plausible-looking verdicts out of the raw text with a regex. That would
    silently turn a broken call into a mediocre checker, and the run record would show a system
    that half-worked instead of one that failed.

    ⚠︎ A MISSING RULE IS RETURNED AS None, NOT AS never_addressed. They are easy to confuse and the
    difference is the whole point of the kit: `never_addressed` is a judgement the model made,
    None is a judgement it never delivered. Scoring them the same way would let a model that
    answered nothing at all inherit the credit for every genuinely silent rule in the set — and on
    this corpus that is 22% of the applicable rules, free.
    """
    out = [None] * n_rules
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
        if not (0 <= i < n_rules):
            continue
        verdict = str(v.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if verdict not in VERDICTS:
            continue
        out[i] = {"verdict": verdict, "quote": str(v.get("quote", "") or "")}
    return out
