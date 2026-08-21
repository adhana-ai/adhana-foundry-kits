"""Extract one certificate's fields: segment, select, prompt, one model call, then a pure-code
self-consistency check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the recomputation) is pure code.

MAX_TOKENS -- a ten-field JSON record; the sibling extraction kits in this series needed 3000-4000
for the same shape of task. Set here on that evidence rather than guessed at from zero.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 4000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def recompute_conformance(measured, lower, upper):
    """THE RULE, in one place, boundary-inclusive, a null bound constraining nothing on that side.

    Returns "yes" / "no", or None when there is no measured value to compare. This is the same
    comparison tools/build_corpus.py used to write gold, and the same one src/prompt.py asks the
    model to perform -- stated once here so the kit, the corpus and the prompt cannot drift apart
    about what the word "conforms" means.
    """
    if not isinstance(measured, (int, float)) or isinstance(measured, bool):
        return None
    lower_ok = (lower is None) or (isinstance(lower, (int, float)) and measured >= lower)
    upper_ok = (upper is None) or (isinstance(upper, (int, float)) and measured <= upper)
    return "yes" if (lower_ok and upper_ok) else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL IS A SELF-CONSISTENCY CHECK, WHICH IS A DIFFERENT SHAPE FROM EVERY SIBLING
    KIT IN THIS SERIES. The others flag a BUSINESS condition -- a break aged past a threshold, an
    income figure below a floor -- and to know whether the flag was right you need a labelled
    answer. This one asks a question that needs no gold at all: does the model's stated verdict
    match what the model's OWN extracted numbers actually say?

    Both halves come out of the same reply. `conforms_to_spec` is the model's conclusion; the
    measured value and the two limits are the model's own reading of the certificate. Running the
    published comparison back over those numbers and finding a different answer means the reply
    disagrees with itself, and one of the two halves is wrong -- which is worth a human's attention
    whichever half it is. That is computable live, on a document nobody has labelled, which a
    business-condition flag is not.

    It is exactly the failure this kit is built to catch: a model talked out of the arithmetic by
    the analyst's reassuring or hedging disposition note, returning a verdict its own extracted
    numbers do not support.

    Returns (needs_review, recomputed_conforms). needs_review is True when the two disagree.
    Returns (None, ...) when the reply is missing something the comparison needs -- an unknown is
    not a pass.
    """
    conforms = values.get("conforms_to_spec")
    measured = values.get("measured_value")
    lower = values.get("spec_lower_limit")
    upper = values.get("spec_upper_limit")

    recomputed = recompute_conformance(measured, lower, upper)
    if conforms not in ("yes", "no") or recomputed is None:
        return None, recomputed

    return (recomputed != conforms), recomputed


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one certificate. `complete` is injectable so the eval harness,
    the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    parsed_ok = bool(values) and any(v is not None for v in values.values())

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):
            v = None
        spannable = f.get("type") != "enum"
        span = segment.locate(doc_text, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review, recomputed = compute(flat)

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_conforms": recomputed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
