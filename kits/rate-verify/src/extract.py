"""Extract one utility billing-account record's fields: segment, select, prompt, one model call,
then a pure-code business-condition check downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the review flag) is pure code.

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


def correct_rate_code(service_class, meter_type, usage_kwh, demand_kw):
    """THE RULE, in one place. Same three-branch priority order in every reader: the corpus
    generator that wrote gold, the prompt that asks the model, and this function, which re-runs it
    over the MODEL's own extracted values for the self-consistency diagnostic.

    Returns a rate code string, or None when a value the rule needs is missing or malformed.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED RATE STRUCTURE, NOT A REAL TARIFF. No published rate case
    or filed tariff was consulted, and none is reproduced.
    """
    if service_class not in ("Residential", "Small Commercial", "Large Commercial", "Industrial"):
        return None
    if service_class == "Residential":
        return "R-1"
    if meter_type not in ("standard", "interval"):
        return None
    if not isinstance(usage_kwh, (int, float)) or isinstance(usage_kwh, bool):
        return None
    if meter_type == "interval" and usage_kwh >= 15000:
        return "TOU-8"
    if demand_kw is not None:
        if not isinstance(demand_kw, (int, float)) or isinstance(demand_kw, bool):
            return None
        if demand_kw >= 50:
            return "GS-2"
    return "GS-1"


def is_rate_correct(applied_code, service_class, meter_type, usage_kwh, demand_kw):
    """"yes" / "no", or None when the rule could not be computed. Same comparison used by
    tools/build_corpus.py to write gold and stated in words by src/prompt.py."""
    want = correct_rate_code(service_class, meter_type, usage_kwh, demand_kw)
    if want is None or applied_code not in ("R-1", "GS-1", "GS-2", "TOU-8"):
        return None
    return "yes" if applied_code == want else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kit immediately
    before this one in the series (pod-conformance): it asks "is this the record somebody has to
    fix today", not "does this reply contradict itself".

    THE CONDITION: a misrated account whose bill has ALREADY BEEN SENT to the customer.

    A misrated account still in draft can simply be corrected before it goes out -- nothing has
    reached the customer yet. The same mismatch on a bill already sent means the customer has to
    be issued a corrected bill or a credit, which is the case a billing desk actually has to act
    on today.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL UTILITY'S BILLING-ADJUSTMENT POLICY. No
    published tariff, regulatory rule or utility's own adjustment procedure was consulted, and
    none is reproduced. A real billing desk weighs the dollar size of the correction, how many
    billing cycles it has been wrong, and any regulatory notice requirement; this is two booleans,
    chosen because it is the smallest rule that is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an
    unknown is not a pass.
    """
    correct = values.get("rate_correct")
    status = values.get("bill_status")
    if correct not in ("yes", "no") or status not in ("draft", "sent"):
        return None
    return (correct == "no") and (status == "sent")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED FOR THE SAME REASON THE SIBLING KIT IMMEDIATELY BEFORE THIS ONE SCOPES IT: a demand
    reading and a usage figure can share digits with each other or with an account id across
    records, and an unscoped document-wide search can cite the wrong section for a value that is
    genuinely correct. Scoping costs nothing and closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one utility billing-account. `complete` is injectable so the
    eval harness, the app and tests all drive the same code path against a stub provider."""
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
    recomputed = is_rate_correct(flat.get("applied_rate_code"), flat.get("service_class"),
                                 flat.get("meter_type"), flat.get("metered_usage_kwh"),
                                 flat.get("peak_demand_kw"))

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_rate_correct": recomputed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
