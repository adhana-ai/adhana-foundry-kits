"""Extract one CAM reconciliation line's fields: segment, select, prompt, one model call, then a
pure-code business-condition check downstream. This is the whole AI layer of the kit -- everything
above it (segment, select) and below it (the review flag) is pure code.

MAX_TOKENS -- MEASURED, NOT GUESSED, AND THE MEASUREMENT IS THE INTERESTING PART. Three
calibration calls were fired before this number was set, on the three most arithmetically loaded
lines in the corpus: CAM-0004 (a cap with slack before the gross-up and binding after it),
CAM-0034 (a mid-year expansion under a gross-up) and CAM-0006 (a cumulative cap compounding over
five periods). They returned 1,909 / 1,420 / 1,644 output tokens, every one with finish_reason
`stop`.

⚠︎ AND 88 PCT OF THAT IS INVISIBLE. The provider reports `reasoning_tokens` beside the completion
count, and on those same three calls it was 1,675 / 1,190 / 1,414 -- so the JSON record that
actually arrives is about 234 tokens and everything else is the model working through four
dependent stages of arithmetic where nobody can see it. A ceiling set from the length of the reply
you can read would be 250 and would truncate every single call. This is the kit in the series where
that gap is largest, because it is the one that asks for a computation rather than a copy.

6000 is roughly three times the observed maximum. The slack is deliberate: reasoning length is the
variable here and it is variable in the direction of the hardest records, which are exactly the
ones a truncation would silently destroy. Every result file records `output_tokens_max`,
`replies_at_ceiling` and each reply's `finish_reason`, so a run that ever approaches this number
says so as a fact rather than leaving it to be inferred from a parse failure.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from .rule import TOLERANCE_USD, line_is_ok, permitted_amount

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 6000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(line_ref):
    with open(os.path.join(CORPUS, "%s.txt" % line_ref), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def recompute(values):
    """Re-run the four-stage rule over the MODEL's OWN extracted values. Returns
    (permitted_or_None, line_ok_or_None).

    ⚑ THIS IS THE NO-GOLD DIAGNOSTIC, NOT THE GUARDRAIL. It needs no labels, so a forker can
    compute it on lines nobody has checked -- and it is blind to exactly the case that matters
    most, a reply that misreads a value and then does the arithmetic on the misreading perfectly.
    Reported beside the graded figures in evals/judge.py and deliberately never called a guardrail.
    """
    want = permitted_amount(values.get("expense_class"), values.get("pool_gross_usd"),
                            values.get("amortization_years"), values.get("occupancy_sensitive"),
                            values.get("building_occupancy_pct"), values.get("building_area_sf"),
                            values.get("tenant_area_sf"), values.get("expansion_area_sf"),
                            values.get("expansion_month"), values.get("cap_type"),
                            values.get("cap_pct"), values.get("cap_basis_usd"),
                            values.get("cap_years"))
    return want, line_is_ok(values.get("billed_to_tenant_usd"), want)


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kit immediately
    before this one in the series (rate-verify): it asks "is this the line somebody has to fix
    today", not "does this reply contradict itself".

    THE CONDITION: a line billed WRONG, in the tenant's DISFAVOUR, on a statement that has ALREADY
    GONE OUT.

    All three matter and the middle one is what makes this kit's flag its own. A wrong line still
    in draft can simply be corrected before it is released -- that is what a pre-check is for. A
    wrong line already issued has reached the tenant. And the DIRECTION decides who is exposed: an
    overcharge is what a tenant's auditor claws back with interest and what triggers a corrected
    statement or a credit, while an undercharge is money the landlord did not collect -- real, but
    nobody outside the building is waiting on it.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL PROPERTY-ACCOUNTING POLICY. No lease's
    audit-rights clause, no reconciliation deadline and no landlord's own release procedure was
    consulted, and none is reproduced. A real desk weighs the dollar size against the audit
    threshold, how many cycles the same error has run, and whether the tenant's audit window is
    still open at all; this is three conditions readable off one reply, chosen because it is the
    smallest rule that is genuinely useful.

    ⚠︎ AND IT READS A COMPUTED FIELD, WHICH IS THE HONEST HALF. `permitted_amount_usd` is the
    model's own arithmetic, so this flag INHERITS every arithmetic error. That is stated rather
    than hidden: evals/judge.py scores the flag separately and the free floor below shows what
    happens to a business-condition guardrail whose input field is wrong.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    ok = values.get("line_ok")
    status = values.get("statement_status")
    if ok not in ("yes", "no") or status not in ("draft", "issued"):
        return None
    billed, permitted = values.get("billed_to_tenant_usd"), values.get("permitted_amount_usd")
    try:
        billed, permitted = float(billed), float(permitted)
    except (TypeError, ValueError):
        return None
    return (ok == "no") and (status == "issued") and (billed > permitted + TOLERANCE_USD)


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THE SCOPING IS LOAD-BEARING RATHER THAN TIDY. Nineteen sections
    carry bare numbers and several of them collide by construction: a cap of `4 pct` and an
    expansion in `month 4`; an occupancy of `86 pct` and a tenant area whose digits contain it. An
    unscoped document-wide search would cite the wrong section for a value that is genuinely
    correct, which is worse than citing nothing.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one CAM reconciliation line. `complete` is injectable so the
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
        # ⚑ A COMPUTED FIELD IS NOT SPANNABLE AND MUST NOT BE COUNTED AS AN UNCITED ONE.
        # `permitted_amount_usd` is arithmetic the model did; it is nowhere in the document by
        # design, so searching for it would either find nothing (scored as a missing citation on a
        # correct answer) or -- worse -- collide with an unrelated figure and cite it.
        spannable = f.get("type") != "enum" and not f.get("computed")
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review = compute(flat)
    recomputed_amount, recomputed_ok = recompute(flat)

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_permitted_usd": recomputed_amount,
        "recomputed_line_ok": recomputed_ok,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
