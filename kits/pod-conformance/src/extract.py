"""Extract one proof-of-delivery record's fields: segment, select, prompt, one model call, then a
pure-code business-condition check downstream. This is the whole AI layer of the kit -- everything
above it (segment, select) and below it (the review flag) is pure code.

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


def is_complete(delivered, ordered, condition):
    """THE RULE, in one place, strict in both directions, `unknown` never a pass.

    Returns "yes" / "no", or None when a value the comparison needs is missing. This is the same
    comparison tools/build_corpus.py used to write gold and the same one src/prompt.py asks the
    model to perform -- stated once here so the corpus, the prompt and the scorer cannot drift
    apart about what the word "complete" means.
    """
    if condition not in ("undamaged", "damaged", "unknown"):
        return None
    for v in (delivered, ordered):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
    return "yes" if (delivered == ordered and condition == "undamaged") else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, and that is a different shape from the sibling
    kit directly before it in this series, whose flag was a self-consistency check. Both shapes
    are worth shipping and they answer different questions. A self-consistency check asks "does
    this reply contradict itself" and needs no labels; this one asks "is this the record a person
    has to pick up today", and it is the question an operations desk actually has.

    THE CONDITION: an incomplete delivery with NO recipient signature on file.

    A shortfall or a damaged pallet that IS signed for is already documented and acknowledged --
    somebody at the receiving end saw the delivery and put their name to it, and the claim, the
    credit note or the re-ship follows an ordinary paper trail. The same problem with no signature
    is the one that turns into a dispute: there is nothing on file to show the recipient was ever
    told, so the carrier's account of the stop and the consignee's are free to diverge, and the
    only surviving evidence is the driver's own note.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL CARRIER'S CLAIMS-INTAKE POLICY. No
    published SLA, tariff or carrier liability rule was consulted, and none is reproduced. A real
    claims desk weighs value, commodity, the consignee's own receiving standard and the terms on
    the bill of lading; this is two booleans, chosen because it is the smallest rule that is
    genuinely useful and can be read off the reply with no second call.

    Returns True / False, or None when the reply is missing something the rule needs -- an
    unknown is not a pass.
    """
    complete = values.get("delivery_complete")
    signature = values.get("recipient_signature_present")
    if complete not in ("yes", "no") or signature not in ("yes", "no"):
        return None
    return (complete == "no") and (signature == "no")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ WHY IT IS SCOPED, WHICH THE SIBLING KITS' UNSCOPED `segment.locate` IS NOT. This corpus
    states the same number twice on purpose: on a complete delivery `ordered_quantity` and
    `delivered_quantity` are equal, and a document-wide search for "72" finds the Ordered Quantity
    line first and cites it for BOTH fields. That is a citation pointing at the wrong section --
    the exact failure src/segment.py's own docstring records paying for once already, because a
    span that looks checkable and is wrong is worse than no span at all. It would have been
    invisible here: the value is right, the section label is wrong, and nothing scores section
    labels.

    Scoping costs nothing. The field's own sections are searched first, in document order, and
    only a value that appears in none of them falls through to the whole document -- so a model
    that paraphrases or reads a value out of an unexpected place still gets a span, and it still
    gets an honest one.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one proof of delivery. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
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
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review = compute(flat)
    recomputed = is_complete(flat.get("delivered_quantity"), flat.get("ordered_quantity"),
                             flat.get("condition_code"))

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_complete": recomputed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
