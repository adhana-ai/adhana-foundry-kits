"""Assemble the detection prompt. One prompt per document, all seven categories in it.

⚠︎ THE GUARDRAIL OF THIS KIT IS ASYMMETRIC, AND THE PROMPT SAYS SO EXPLICITLY.
docs-extract's guardrail is "return null rather than invent a value" because a confident wrong
answer is worse than an honest gap. This kit's failure has the same shape but a different name and
a real cost difference: a span that should have been caught and was not is a LEAK — the sensitive
text ships in the redacted document, in front of whoever was supposed to be protected from it. A
span that gets caught and should not have been is OVER-REDACTION — a `[NAME]` where a real name
belonged, annoying and sometimes damaging (a legal document that redacts its own signatory), but
never a disclosure. `evals/judge.py` scores both and never averages them into one number, the same
discipline docs-extract's judge applies to extraction vs. refusal — but the PROMPT is where the
asymmetry has to be instilled in the first place, because a scorer downstream of a model that was
never told which mistake costs more is grading a coin flip.

⚑ ONE CALL FOR THE WHOLE DOCUMENT, NOT ONE PER CATEGORY. Same reasoning as docs-extract's
prompt.py: seven calls would be seven times the fixed overhead and seven round trips for documents
short enough to send whole. There is no section-selection step here at all — unlike docs-extract's
documents, these are a few hundred words each and fit in a single call with room to spare, so the
selection layer docs-extract needed to control cost simply has nothing to select from.
"""
import json

SYSTEM = (
    "You detect sensitive spans (PII) in a document. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. Find EVERY span that is a genuine instance of one of the categories below. A span you miss "
    "leaks — it ships to whoever reads the redacted document. That is the more expensive mistake, "
    "so when genuinely unsure whether something is an instance of a category, include it.\n"
    "2. Do not invent a span that is not actually in the document, and do not flag ordinary text "
    "that only resembles a category without being a real instance of it (a four-digit year is not "
    "a CARD; a business's public office address is not a personal ADDRESS). Flagging safe text is "
    "a real mistake too — it is just the cheaper one.\n"
    "3. Copy each span's text VERBATIM from the document — the exact substring, character for "
    "character, so it can be located afterward. Do not normalise, reformat or truncate it.\n"
    "4. If the same value occurs more than once in the document, return one entry per occurrence.\n"
    "5. Return a JSON object of the exact form {\"spans\": [{\"text\": \"...\", \"category\": "
    "\"...\"}, ...]}. Use exactly one of the category names given below for every entry."
)


def category_schema(categories):
    """The schema as the model sees it: name and one-line hint, one per line."""
    return "\n".join("- %s — %s" % (c["name"], c["hint"]) for c in categories)


def build(doc_text, categories):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes.

    THE PARTS ARE A REAL DECOMPOSITION, NOT A TIDY BREAKDOWN — same rule docs-extract's build()
    follows: every part's text occurs verbatim in what is sent, in this order.
    """
    schema = category_schema(categories)
    names = [c["name"] for c in categories]
    user = ("Find every sensitive span in this document, across these categories:\n%s\n\n"
            "Return a JSON object with one key, \"spans\", a list of {\"text\", \"category\"} "
            "objects. Use exactly one of: %s\n\n"
            "DOCUMENT\n--------\n%s\n" % (schema, ", ".join(names), doc_text))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "category schema", "text": schema},
        {"name": "document", "text": doc_text},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts)


def parse(raw, categories):
    """Pull the spans list out of a model reply, tolerantly but never creatively.

    Same discipline as docs-extract's parse(): a reply that does not parse yields an empty list —
    read as zero spans found, not as evidence about the document — never a fallback that scrapes
    plausible-looking values out of the raw text with a regex. That would silently turn a broken
    model call into a mediocre detector and the run record would show a system that half-worked.
    """
    allowed = {c["name"] for c in categories}
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return []
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    raw_spans = obj.get("spans")
    if not isinstance(raw_spans, list):
        return []

    out = []
    for sp in raw_spans:
        if not isinstance(sp, dict):
            continue
        text = sp.get("text")
        cat = sp.get("category")
        if not isinstance(text, str) or not text.strip():
            continue
        # ⚠︎ AN UNKNOWN CATEGORY IS DROPPED, NOT COERCED. A model that answers "CREDIT_CARD"
        # instead of "CARD" is a format fault, not a fifth failure mode the judge has to invent a
        # verdict for — dropping it here means it shows up honestly as a missed span (a leak) in
        # scoring, rather than silently being renamed into a category it never actually claimed.
        if not isinstance(cat, str) or cat.upper() not in allowed:
            continue
        out.append({"text": text, "category": cat.upper()})
    return out
