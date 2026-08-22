"""Adjudicate one warranty claim record: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the recovery flag) is pure code.

⚑ MAX_TOKENS IS A MEASUREMENT HERE, NOT A GUESS -- see the note beside the constant.
"""
import datetime
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED, ON THIS CORPUS, WITH THIS PROMPT -- not inherited from a sibling kit.
#
# `evals/calibrate.py` sent SIX claims at a deliberately generous ceiling of 16,000 on 2026-08-22,
# one from each of the hardest classes in the corpus, and recorded what the provider actually
# billed. Committed at results/calib-c001-coverage-check.json:
#
#     peak completion   647 tokens   (WCL-0007, past_limit)
#     mean completion   543.3 tokens
#     reasoning share   60.3 pct of every completion token billed
#     truncated         none -- all six finish_reason=stop
#
# 3000 is 4.6x the observed peak. That is headroom, not "just past it".
#
# ⚠︎ WHY THE CEILING IS NOT THE REPLY LENGTH. The JSON answer is fourteen keys, one of which copies
# a ~250-character narrative back verbatim -- a couple of hundred tokens of visible text. Six in
# every ten completion tokens billed here are a reasoning pass that never reaches `text`.
# Reasoning is left at the provider's own default (this kit never sends a `thinking` parameter)
# and reasoning tokens are billed and bounded as completion tokens, so the budget a six-branch
# priority rule plus a date calculation consumes is invisible in the reply and is the thing being
# measured. A ceiling set from the visible reply length truncates, and a truncated reply is scored
# as a wrong answer by any grader that cannot tell the two apart -- which is how a sibling kit in
# this series published an inflated failure rate twice before measuring instead. evals/run.py
# counts `finish_reason == "length"` separately for exactly that reason.
MAX_TOKENS = 3000

# The coverage terms, the component lists and the labor operations. Restated here rather than
# imported from tools/build_corpus.py on purpose: a fork that keeps src/ and throws away the
# generator must still run. tools/build_corpus.py asserts the two agree, so they cannot drift
# silently -- see evals/check_labels.py.
#
# ⚠︎ THIS IS THIS KIT'S OWN INVENTED COVERAGE STRUCTURE, NOT ANY MANUFACTURER'S PUBLISHED WARRANTY.
# No real warranty booklet, service contract, component schedule or labor operation catalogue was
# consulted, and none is reproduced.
PLANS = {
    "basic":      {"months": 36, "miles": 36000},
    "powertrain": {"months": 60, "miles": 60000},
    "emissions":  {"months": 96, "miles": 80000},
    "extended":   {"months": 84, "miles": 100000},
}
POWERTRAIN_PARTS = ["transmission_assembly", "engine_short_block", "drive_axle"]
EMISSIONS_PARTS = ["catalytic_converter", "oxygen_sensor", "evap_canister"]
ACCESSORY_PARTS = ["infotainment_head_unit", "power_window_motor", "hvac_blower_motor"]
WEAR_PARTS = ["brake_pads", "wiper_blades", "clutch_disc"]
PLAN_COMPONENTS = {
    "basic": POWERTRAIN_PARTS + EMISSIONS_PARTS + ACCESSORY_PARTS,
    "extended": POWERTRAIN_PARTS + EMISSIONS_PARTS + ACCESSORY_PARTS,
    "powertrain": POWERTRAIN_PARTS,
    "emissions": EMISSIONS_PARTS,
}
LABOR_OPS = {
    "transmission_assembly": "LOP-4412", "engine_short_block": "LOP-4101",
    "drive_axle": "LOP-4520", "catalytic_converter": "LOP-2203",
    "oxygen_sensor": "LOP-2217", "evap_canister": "LOP-2240",
    "infotainment_head_unit": "LOP-8310", "power_window_motor": "LOP-8422",
    "hvac_blower_motor": "LOP-8155", "brake_pads": "LOP-5701",
    "wiper_blades": "LOP-5140", "clutch_disc": "LOP-5330",
}
EARLY_MONTHS = 12
EARLY_MILES = 12000
EXCLUSIONS = ("collision_damage", "unauthorized_modification", "missed_maintenance")
FINDINGS = ("defect",) + EXCLUSIONS


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(claim_ref):
    with open(os.path.join(CORPUS, "%s.txt" % claim_ref), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def months_between(in_service, repair):
    """COMPLETE months in service, from two YYYY-MM-DD strings. Returns None when either date is
    unreadable -- an unknown is not a zero, and a zero here would read as "brand new"."""
    try:
        a = datetime.date.fromisoformat(str(in_service))
        b = datetime.date.fromisoformat(str(repair))
    except (TypeError, ValueError):
        return None
    m = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        m -= 1
    return m


def coverage_verdict(plan, months, miles, component, labor_op, narrative_finding):
    """THE RULE, in one place. Same six-branch priority order in every reader: the corpus generator
    that wrote gold, the prompt that asks the model, and this function, which re-runs it over the
    MODEL's own extracted values for the self-consistency diagnostic.

    Returns "yes" / "no", or None when a value the rule needs is missing or malformed.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED COVERAGE STRUCTURE, NOT A REAL WARRANTY PROGRAMME.
    """
    if plan not in PLANS or component not in LABOR_OPS or narrative_finding not in FINDINGS:
        return None
    if not isinstance(months, (int, float)) or isinstance(months, bool):
        return None
    if not isinstance(miles, (int, float)) or isinstance(miles, bool):
        return None
    if not isinstance(labor_op, str) or not labor_op:
        return None

    if narrative_finding in EXCLUSIONS:
        return "no"
    if labor_op != LABOR_OPS[component]:
        return "no"
    if component in WEAR_PARTS:
        early = months <= EARLY_MONTHS and miles <= EARLY_MILES
        return "yes" if (plan in ("basic", "extended") and early) else "no"
    if component not in PLAN_COMPONENTS[plan]:
        return "no"
    if months > PLANS[plan]["months"] or miles > PLANS[plan]["miles"]:
        return "no"
    return "yes"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling extraction kits in
    this series: it asks "is this the claim somebody has to act on today", not "does this reply
    contradict itself".

    THE CONDITION: a claim that is NOT covered and has ALREADY BEEN PAID to the dealer.

    An uncovered claim still in `submitted` can simply be denied before any money moves -- the
    adjudicator declines it and that is the end of it. The same claim already `paid` means the
    money is out the door and somebody has to open a recovery against the dealer, which is the
    case a warranty desk actually has to work today.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY MANUFACTURER'S WARRANTY-RECOVERY POLICY. No
    published warranty programme, dealer agreement or chargeback procedure was consulted, and none
    is reproduced. A real warranty desk weighs the dollar value of the claim, the dealer's own
    claim history and any audit or appeal window; this is two booleans, chosen because it is the
    smallest rule that is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    covered = values.get("covered")
    status = values.get("claim_status")
    if covered not in ("yes", "no") or status not in ("submitted", "paid"):
        return None
    return (covered == "no") and (status == "paid")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED FOR THE SAME REASON EVERY SIBLING KIT SCOPES IT: an odometer reading and a claim id
    can share digits with each other across records, and an unscoped document-wide search can cite
    the wrong section for a value that is genuinely correct. Scoping costs nothing and closes the
    whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full adjudicated record for one warranty claim. `complete` is injectable so the
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
        # months_in_service is COMPUTED from two dates rather than read off the page, so there is
        # nothing to point at -- a span for it would be a citation of a number the document does
        # not contain. Enum fields are fixed vocabulary and equally unspannable.
        spannable = f.get("type") != "enum" and name != "months_in_service"
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review = compute(flat)
    recomputed = coverage_verdict(flat.get("coverage_plan"), flat.get("months_in_service"),
                                  flat.get("odometer_miles"), flat.get("failed_component"),
                                  flat.get("claimed_labor_op"), flat.get("narrative_finding"))
    # The date arithmetic re-run over the reply's OWN two dates. Needs no gold, so a forker can
    # compute it on unlabelled claims -- and it separates "misread a date" from "cannot count
    # months", which a single accuracy figure folds together.
    recomputed_months = months_between(flat.get("in_service_date"), flat.get("repair_date"))

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_covered": recomputed,
        "recomputed_months": recomputed_months,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
