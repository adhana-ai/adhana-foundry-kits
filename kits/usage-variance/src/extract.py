"""Extract one usage-to-invoice reconciliation record's fields: segment, select, prompt, one model
call, then a pure-code business-condition check downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the credit flag) is pure code.

⚑ MAX_TOKENS IS A MEASUREMENT, NOT A GUESS -- see MEASURED_ON below the constant.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED, NOT INHERITED, AND THE MEASUREMENT FOUND SOMETHING. One calibration call was fired
# against TLV-0005 at a deliberately oversized ceiling of 8000 before any scored run
# (evals/measure_max_tokens.py; results/calib-c001-usage-variance.json is committed). The provider
# billed 552 output tokens, finish_reason "stop" -- and its own completion-token breakdown says 444
# of those 552, EIGHTY PERCENT, were reasoning tokens that never reach `text`. The visible reply is
# 381 characters of JSON, about 108 tokens.
#
# So the ceiling has to cover the reasoning pass, not the answer: 3000 is 5.4x the measured total
# and roughly 28x the visible reply. Sizing it off the JSON alone -- the obvious reading, and the
# one a sibling kit in this series paid for with four lost documents -- would have clipped every
# reply at the point the model stopped thinking and started answering. The run harness records
# finish_reason on every call and names "CUT OFF AT THE CEILING" if any reply ever reaches it.
#
# ⚠︎ AND THE SAME MEASUREMENT IS THIS KIT'S LARGEST COST DRIVER, published as one. The reasoning
# pass is not requested by anything here: src/adapters/__init__.py sends `thinking` only when a
# caller passes it, and this kit's harness never does, so it is the provider's own default and
# every run recorded here paid for it.
MAX_TOKENS = 3000
MEASURED_ON = ("calib-c001-usage-variance, TLV-0005, 552 output tokens (444 of them reasoning), "
               "finish_reason=stop, at a ceiling of 8000")

CAUSES = ("none", "rounding", "unrated_usage", "duplicate_records", "late_records", "unexplained")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(line_ref):
    with open(os.path.join(CORPUS, "%s.txt" % line_ref), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def increment(service_type):
    """THE BILLING INCREMENT, in the same unit the quantities are stated in. One place.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED INCREMENT TABLE, NOT A REAL CARRIER'S RATING CONFIGURATION.
    Whole-minute voice rounding and whole-megabyte data rounding are ordinary telecoms practice; the
    exact values here were chosen for this corpus, and no published tariff, rate schedule or
    interconnect agreement was consulted or is reproduced.

    Returns None for a service this kit does not recognise -- an unknown is not a default.
    """
    return {"voice": 60, "data": 1024, "sms": 1}.get(service_type)


def _int(v):
    """A quantity, or None. Accepts an int, a float that is a whole number, and a numeric string --
    a model that returns "598133" or 598133.0 has answered the question. Anything else is None,
    which the rule treats as unanswerable rather than as zero."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if float(v).is_integer() else None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        try:
            f = float(s)
        except ValueError:
            return None
        return int(f) if f.is_integer() else None
    return None


def round_up(x, inc):
    """Integer ceiling to the next whole increment. `-(-x // inc)` rather than math.ceil on a
    float, because a float division of two large integers is exactly where a boundary case at
    15,360 KB silently becomes 15,359."""
    return -(-x // inc) * inc


def expected_invoiced(service_type, mediated, prior_period, confirmed_duplicates):
    """What SHOULD have been on the invoice line, or None when a value the rule needs is missing or
    malformed. tools/build_corpus.py::expected_invoiced() is the same function, used to write gold;
    data/fields.json states it to the model in words. Three readers, one definition.

    ⚠︎ `unrated` IS NOT SUBTRACTED. Usage that failed rating is still this period's usage and is
    still owed; the invoice being short of it is the variance, not a reason to lower the target.
    """
    inc = increment(service_type)
    m, p, d = _int(mediated), _int(prior_period), _int(confirmed_duplicates)
    if inc is None or m is None or p is None or d is None:
        return None
    if m < 0 or p < 0 or d < 0:
        return None
    return round_up(m - p - d, inc)


def classify(service_type, mediated, invoiced, unrated, prior_period, confirmed_duplicates):
    """THE RULE, in one place, with its priority order. Returns one of CAUSES, or None when a value
    the rule needs is missing or malformed.

    Same six-way classification in every reader: the corpus generator that wrote gold, the prompt
    that asks the model, and this function, which re-runs it over the MODEL's own extracted values
    for the self-consistency diagnostic.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED RECONCILIATION RULE, NOT A REAL CARRIER'S REVENUE-ASSURANCE
    PROCEDURE. No published mediation specification, billing-system configuration or interconnect
    settlement rule was consulted, and none is reproduced.
    """
    inc = increment(service_type)
    exp = expected_invoiced(service_type, mediated, prior_period, confirmed_duplicates)
    inv, un = _int(invoiced), _int(unrated)
    p, d = _int(prior_period), _int(confirmed_duplicates)
    if inc is None or exp is None or inv is None or un is None or un < 0:
        return None
    gap = inv - exp
    if gap == 0:
        return "none"
    if abs(gap) < inc:
        return "rounding"
    if gap < 0 and un > 0 and abs(-gap - un) < inc:
        return "unrated_usage"
    if gap > 0 and d > 0 and abs(gap - d) < inc:
        return "duplicate_records"
    if gap > 0 and p > 0 and abs(gap - p) < inc:
        return "late_records"
    return "unexplained"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kits immediately
    before this one in the series: it asks "is this the line somebody has to fix today", not "does
    this reply contradict itself".

    THE CONDITION: a line that OVER-BILLED the customer on an invoice that has ALREADY BEEN ISSUED.

    Over-billing is `duplicate_records` (confirmed duplicate sessions were charged for) or
    `late_records` (the previous period's usage was charged again on this one). Either of those on
    a draft invoice can simply be corrected before it goes out -- nothing has reached the customer.
    The same variance on an invoice already issued means the customer has been charged money they
    do not owe and is due a credit, which is the case a billing desk actually has to act on today.

    ⚠︎ AND NOTE WHAT IT DELIBERATELY DOES NOT FIRE ON. `unrated_usage` is UNDER-billing -- real
    revenue leakage, and a real revenue-assurance team cares about it -- but nobody is owed money
    and no customer is waiting, so it is not this flag's job. Splitting the two is the whole reason
    this rule is a separate function from classify(): changing WHO GETS A CREDIT does not change
    WHAT THE VARIANCE IS.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL CARRIER'S BILLING-ADJUSTMENT POLICY. No
    published tariff, regulatory rule or operator's own credit procedure was consulted, and none is
    reproduced. A real billing desk weighs the dollar size of the credit, the dispute window, and
    whether the line is inside a contracted tolerance; this is one enum test and one boolean, chosen
    because it is the smallest rule that is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    cause = values.get("variance_cause")
    status = values.get("invoice_status")
    if cause not in CAUSES or status not in ("draft", "issued"):
        return None
    return (cause in ("duplicate_records", "late_records")) and (status == "issued")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THE SCOPING IS LOAD-BEARING RATHER THAN PRECAUTIONARY. Five of
    the eleven fields are quantities in the same unit sitting in adjacent sections, and on a line
    where the invoice is exactly right the mediated and invoiced figures can be the same digits.
    An unscoped document-wide search would cite `Mediated Usage` for a value read from
    `Invoiced Quantity` and the citation would look perfectly good.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one reconciliation line. `complete` is injectable so the eval
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
    needs_credit = compute(flat)
    recomputed = classify(flat.get("service_type"), flat.get("mediated_quantity"),
                          flat.get("invoiced_quantity"), flat.get("unrated_quantity"),
                          flat.get("prior_period_quantity"),
                          flat.get("confirmed_duplicate_quantity"))

    return {
        "fields": out,
        "needs_credit": needs_credit,
        "recomputed_variance_cause": recomputed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
