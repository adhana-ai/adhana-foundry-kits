"""Extract one channel commission claim record's fields: segment, select, prompt, one model call,
then a pure-code business-condition check downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the recovery flag) is pure code.

MAX_TOKENS -- MEASURED, NOT GUESSED. A calibration run of three records was fired at a deliberately
generous ceiling of 8000 before anything else spent, purely to read the provider's own
`output_tokens` back off a fourteen-field JSON record of this shape. The measurement is committed
at results/tokens-c000-commission-audit.json; the ceiling below is set from it with headroom, and
the number the measurement produced is written in the comment beside it so a later reader can see
what it was set against rather than trusting the constant.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED, NOT GUESSED -- evals/max_tokens.py, run c000-commission-audit, three records at a
# deliberately generous 8000-token ceiling: 294 / 540 / 746 output tokens, finish_reason "stop" on
# all three, none clipped (results/tokens-c000-commission-audit.json).
#
# ⚠︎ THE SPREAD IS THE FINDING, NOT THE MEDIAN. Three replies to three records of identical shape
# ranged 294 to 746 -- a 2.5x spread on a fourteen-key JSON object whose keys never change. Whatever
# is producing the extra 450 tokens is not the record, so a ceiling set near the median would clip
# the tail and a clipped reply is not a short reply, it is an unparseable one. 4000 is ~5.4x the
# largest measured, which is headroom over the tail rather than over the middle.
MAX_TOKENS = 4000

STAY_STATUSES = ("stayed", "rebooked")
CANCEL_STATUSES = ("cancelled", "no_show")
FOLIO_STATUSES = STAY_STATUSES + CANCEL_STATUSES
BOOKING_SOURCES = ("channel", "direct", "corporate_gds", "walk_in")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(claim_ref):
    with open(os.path.join(CORPUS, "%s.txt" % claim_ref), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _num(v):
    """A money or percentage value as a float, or None when it is not one. `True` is an int in
    Python and would multiply happily, so booleans are refused explicitly."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def owed_commission(folio_status, booking_source, already_commissioned,
                    room_revenue_usd, room_revenue_refunded_usd, penalty_charged_usd,
                    contract_rate_pct):
    """THE RULE, in one place. Same five-branch priority order in every reader: the corpus
    generator that wrote gold, the prompt that asks the model, and this function, which re-runs it
    over the MODEL's own extracted values for the self-consistency diagnostic.

    Returns the commission owed in dollars, or None when a value the rule needs is missing or
    malformed. An unknown is never silently a zero -- a claim the rule cannot evaluate must not
    come out looking like a claim the rule evaluated to nothing.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COMMISSION STRUCTURE, NOT A REAL CHANNEL AGREEMENT. No
    booking channel's published terms, no signed distribution agreement and no real commission
    schedule was consulted, and none is reproduced.
    """
    if booking_source not in BOOKING_SOURCES:
        return None
    if booking_source != "channel":
        return 0.0
    if already_commissioned not in ("yes", "no"):
        return None
    if already_commissioned == "yes":
        return 0.0
    if folio_status not in FOLIO_STATUSES:
        return None
    rate = _num(contract_rate_pct)
    if rate is None:
        return None
    if folio_status in STAY_STATUSES:
        rev = _num(room_revenue_usd)
        refunded = _num(room_revenue_refunded_usd)
        if rev is None:
            return None
        # A stay with no refund line at all is read as no refund; the corpus always states one,
        # and a reply that dropped it should not take the whole record down with it.
        base = rev - (refunded or 0.0)
    else:
        base = _num(penalty_charged_usd)
        if base is None:
            return None
    if base <= 0:
        return 0.0
    return round(base * rate / 100.0, 2)


def is_claim_valid(claimed_commission_usd, folio_status, booking_source, already_commissioned,
                   room_revenue_usd, room_revenue_refunded_usd, penalty_charged_usd,
                   contract_rate_pct):
    """"yes" / "no", or None when the rule could not be computed. Same comparison used by
    tools/build_corpus.py to write gold and stated in words by src/prompt.py."""
    owed = owed_commission(folio_status, booking_source, already_commissioned,
                           room_revenue_usd, room_revenue_refunded_usd, penalty_charged_usd,
                           contract_rate_pct)
    claimed = _num(claimed_commission_usd)
    if owed is None or claimed is None:
        return None
    return "yes" if abs(claimed - owed) < 0.005 else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as every sibling kit in this
    series: it asks "is this the line somebody has to chase today", not "does this reply
    contradict itself".

    THE CONDITION: a claim that is not owed as claimed, on an invoice the property has ALREADY
    PAID.

    A bad line on an unpaid invoice can simply be short-paid before settlement -- no money has
    left the property and there is nothing to recover. The same line on an invoice already paid
    means the property is out of pocket and has to raise a recovery claim against the channel,
    which is the case a hotel finance desk actually has to act on today.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL PROPERTY'S DISPUTE POLICY. No booking
    channel's published dispute procedure, no signed distribution agreement and no property's own
    recovery threshold was consulted, and none is reproduced. A real desk weighs the dollar size
    of the variance, whether the channel's dispute window is still open, and the cost of raising a
    claim at all; this is two booleans, chosen because it is the smallest rule that is genuinely
    useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    valid = values.get("claim_valid")
    status = values.get("invoice_status")
    if valid not in ("yes", "no") or status not in ("unpaid", "paid"):
        return None
    return (valid == "no") and (status == "paid")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED FOR THE SAME REASON EVERY SIBLING KIT SCOPES IT, and this corpus makes the case
    sharply: four money fields sit on one folio and a claimed commission can share digits with a
    refund or a penalty. An unscoped document-wide search can cite the wrong section for a value
    that is genuinely correct. Scoping costs nothing and closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def _span_value(field, value):
    """What to look for in the text. Money and percentage fields come back as bare numbers and the
    document states them formatted -- `482.36 USD`, `17.5 pct` -- so a bare `482.36` still
    locates, but `482.4` or `482` would not. Formatting the number the way the corpus writes it
    before searching is what keeps a correct value from shipping with no span.
    """
    if field.get("type") != "number" or value is None:
        return value
    n = _num(value)
    if n is None:
        return value
    return ("%.1f" % n) if field["name"].endswith("_pct") else ("%.2f" % n)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one commission claim. `complete` is injectable so the eval
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
        span = _locate(doc_text, secs, name, _span_value(f, v)) if (v is not None and spannable) \
            else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_recovery = compute(flat)
    recomputed = is_claim_valid(flat.get("claimed_commission_usd"), flat.get("folio_status"),
                                flat.get("booking_source"), flat.get("already_commissioned"),
                                flat.get("room_revenue_usd"),
                                flat.get("room_revenue_refunded_usd"),
                                flat.get("penalty_charged_usd"), flat.get("contract_rate_pct"))
    owed = owed_commission(flat.get("folio_status"), flat.get("booking_source"),
                           flat.get("already_commissioned"), flat.get("room_revenue_usd"),
                           flat.get("room_revenue_refunded_usd"),
                           flat.get("penalty_charged_usd"), flat.get("contract_rate_pct"))

    return {
        "fields": out,
        "needs_recovery": needs_recovery,
        "recomputed_claim_valid": recomputed,
        "recomputed_owed_usd": owed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
