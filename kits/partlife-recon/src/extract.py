"""Reconcile one life-limited component's record pack: segment, select, prompt, one model call,
then a pure-code escalation check downstream. This is the whole AI layer of the kit -- everything
above it (segment, select) and below it (the escalate flag) is pure code.

⚠︎ MAX_TOKENS IS MEASURED HERE, NOT GUESSED, AND IT IS MEASURED ON BOTH TIERS. Five live probe
calls were spent before any scored run, at a deliberately generous ceiling of 6,000, on the
LONGEST packs in the corpus rather than typical ones -- the reply carries the reviewer's note back
verbatim, so the pack with the most trail lines is the pack whose reply is biggest, and sampling
typical packs would under-measure exactly the case that truncates.

    fast tier          (results/cap-c001-partlife-recon.json)      466, 506, 809 output tokens
    deliberating tier  (results/cap-c002-partlife-recon-pro.json)  834, 976 output tokens

Every one of the five finished on `stop`, not `length` -- so the probe measured the REPLY and not
the ceiling. MAX_TOKENS is set at 2,000: roughly 2x the longest reply the more verbose tier
produced. A ceiling copied from a sibling kit is a number nobody measured on this prompt; a ceiling
with no headroom is a truncated reply that fails to parse and reads on a results page as a model
that could not do the task. Five calls bought the difference.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 2000

LIFE_STATUSES = ("within_limits", "hours_exceeded", "cycles_exceeded", "both_exceeded",
                 "cannot_determine")
DISPOSITIONS = ("return to service", "shelf storage")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(rec_id):
    with open(os.path.join(CORPUS, "%s.txt" % rec_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def spannable(field):
    """⚑ A COMPUTED TOTAL HAS NO SPAN, AND SAYING SO IS THE HONEST ANSWER.

    Every other kit in this series derives spannability from the field TYPE: an enum is a fixed
    value that cannot be quoted, everything else can be located in the document. That rule is
    wrong here for exactly two fields. `trail_hours` and `trail_cycles` are the SUM of several
    stated figures and appear nowhere in the pack -- the sum is the work, not a citation. A
    document-wide search for "16000" on a pack whose tag happens to read 16000 would find the tag
    and cite it, producing a span that points at the one figure the total is deliberately NOT
    copied from. So the schema carries an explicit `spannable: false` on those two, and the
    span-rate denominator excludes them rather than counting them as misses.
    """
    if "spannable" in field:
        return bool(field["spannable"])
    return field.get("type") != "enum"


def life_status(trail_hours, trail_cycles, limit_hours, limit_cycles, record_gap):
    """THE RULE, in one place. Same five-branch priority order in every reader: the corpus
    generator that wrote gold, the prompt that asks the model, and this function, which re-runs it
    over the MODEL's own reconstructed figures for the self-consistency diagnostic.

    Returns one of LIFE_STATUSES, or None when a figure the rule needs is missing or malformed.

    ⚠︎ THE EXCEEDANCE CHECKS RUN BEFORE THE GAP CHECK. A missing period of records can only ADD
    accumulated life; it can never bring a component the surviving records already put at or past
    a limit back inside it. A gap makes "within limits" undeterminable and leaves "exceeded"
    perfectly determinable.

    ⚠︎ THE LIMIT IS INCLUSIVE. Exactly at the published limit there is no life remaining.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED LIFE-LIMIT STRUCTURE AND ITS OWN CONVENTION ABOUT WHAT A
    RECORD TRAIL SUBSTANTIATES. No real airworthiness directive, maintenance manual, operator
    procedure or manufacturer limit was consulted, and none is reproduced. It is a statement about
    the RECORDS. It is not an airworthiness determination, and nothing in this kit releases
    anything to service.
    """
    for v in (trail_hours, trail_cycles, limit_hours, limit_cycles):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
    if record_gap not in ("yes", "no"):
        return None
    hours_out = trail_hours >= limit_hours
    cycles_out = trail_cycles >= limit_cycles
    if hours_out and cycles_out:
        return "both_exceeded"
    if hours_out:
        return "hours_exceeded"
    if cycles_out:
        return "cycles_exceeded"
    if record_gap == "yes":
        return "cannot_determine"
    return "within_limits"


def tag_agreement(tag_hours, tag_cycles, trail_hours, trail_cycles):
    """"yes" / "no", or None when a figure the comparison needs is missing. Exact equality on both
    counters: a tag that is right about hours and wrong about cycles does not agree. Same function
    tools/build_corpus.py used to write gold."""
    for v in (tag_hours, tag_cycles, trail_hours, trail_cycles):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
    return "yes" if (tag_hours == trail_hours and tag_cycles == trail_cycles) else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kits before this one
    in the series: it asks "is this the pack somebody has to stop today", not "does this reply
    contradict itself".

    THE CONDITION: the pack carries a discrepancy -- the trail does not clear the component, OR the
    component's own tag disagrees with the trail -- AND somebody is asking for it to go back on an
    aircraft right now.

    The same discrepancy on a component headed for shelf storage still has to be resolved, and it
    does not have to be resolved before the aircraft moves. The pack up for return to service is
    the one a records desk has to reach first, which is what "escalated before release" means.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY OPERATOR'S OR AUTHORITY'S RELEASE PROCEDURE.
    No airworthiness regulation, approved maintenance organisation exposition or continuing-
    airworthiness management procedure was consulted, and none is reproduced. A real records desk
    weighs which discrepancy it is, what evidence can still be recovered, and who is authorised to
    accept what; this is three fields and a boolean, chosen because it is the smallest rule that
    is genuinely useful and readable off one reply.

    ⚠︎ AND IT ESCALATES. IT DOES NOT CLEAR, RELEASE OR CERTIFY ANYTHING. A `False` here means this
    rule found nothing to raise -- it does not mean the component may fly.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    status = values.get("life_status")
    agrees = values.get("tag_agrees")
    disposition = values.get("disposition_requested")
    if status not in LIFE_STATUSES or agrees not in ("yes", "no") \
            or disposition not in DISPOSITIONS:
        return None
    discrepancy = (status != "within_limits") or (agrees == "no")
    return discrepancy and (disposition == "return to service")


def _locate(doc_text, secs, field_name, value):
    """Where in the pack this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THE SCOPING IS LOAD-BEARING RATHER THAN TIDY. A pack states four
    different hours figures and four different cycles figures (a limit, a tag figure and one per
    installation period) and they collide constantly -- REC-0015's limit, tag and reconstructed
    total are all 16000/20000. An unscoped document-wide search would cite whichever came first
    and look exactly like a located value.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one component pack. `complete` is injectable so the eval harness,
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
        can_span = spannable(f)
        span = _locate(doc_text, secs, name, v) if (v is not None and can_span) else None
        out[name] = {
            "value": v,
            "spannable": can_span,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    escalate = compute(flat)
    recomputed_status = life_status(flat.get("trail_hours"), flat.get("trail_cycles"),
                                    flat.get("life_limit_hours"), flat.get("life_limit_cycles"),
                                    flat.get("record_gap"))
    recomputed_agrees = tag_agreement(flat.get("tag_hours"), flat.get("tag_cycles"),
                                      flat.get("trail_hours"), flat.get("trail_cycles"))

    return {
        "fields": out,
        "escalate": escalate,
        "recomputed_life_status": recomputed_status,
        "recomputed_tag_agrees": recomputed_agrees,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
