"""Extract one label-restriction case: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the hold flag) is pure code.

⚠︎ THIS KIT PROPOSES A READING OF A LABEL. IT NEVER AUTHORISES AN APPLICATION. `extract()` returns
a verdict with the check set's own reasoning attached, names the restriction that decided it, and
names what it could not determine; a qualified adviser decides against the approved label for the
product in the territory it is being used in. Nothing in this file writes, dispatches, releases or
clears anything, and the shipped check set is illustrative rather than an authority -- see
src/checks.py and data/SOURCES.md.

MAX_TOKENS -- see the note on the constant below. It is NOT a calibrated number and this file says
so rather than implying one.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from . import checks as CK

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ SET WITH HEADROOM, AND NOT CALIBRATED BY ITS OWN RUN -- which is a weaker claim than the
# sibling kit that fired a six-document calibration pass first, and it is stated as the weaker
# claim rather than dressed up.
#
# What it is reasoned from: sibling extraction kits in this series measured a TEN-key reply at
# roughly 600 output tokens, of which about three quarters was provider-side reasoning left at the
# provider's default. This kit's reply carries TWENTY-TWO keys over a longer prompt, so a reply
# three times that size is entirely plausible and 6000 is about 3x even that.
#
# The headroom is deliberate and it is not arbitrary: a sibling kit published three successive runs
# whose "failures" were nothing but a cap set from a smaller corpus, and a DIFFERENT set of records
# truncated each time. A cap that cuts a reply costs a whole document; a cap with headroom costs
# nothing at all, because a reply that finishes is billed for what it used and not for the ceiling.
#
# evals/run.py records `output_tokens_max` on every run, so the real margin is a fact on the run
# record rather than an argument here -- and the kit publishes what that margin turned out to be.
MAX_TOKENS = 6000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(case_id):
    with open(os.path.join(CORPUS, "%s.txt" % case_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The check-set walk re-derived from a set of extracted values.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py renders
    it to the model out of the same JSON file, and evals/judge.py runs it over the model's OWN
    values for the no-gold consistency diagnostic.
    """
    return CK.decide(values)


def correct_verdict(values):
    return CK.verdict_of(values)


def correct_restriction(values):
    return CK.restriction_of(values)


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    field somebody has to act on right now", not "does this reply contradict itself".

    THE CONDITION: a proposed application whose verdict is anything other than `within_label`, and
    which has ALREADY BEEN MADE.

    A planned application that is outside the label can simply be changed before the sprayer goes
    out -- a different product, a lower rate, a fortnight later, or not at all -- and nothing has
    happened yet. The same verdict on an application already made means the product is already on
    the crop, which is the case somebody has to deal with today: record it, work out what it does
    to the harvest date, and get a qualified adviser to it. `insufficient_information` counts here
    too, deliberately -- product already applied under a label restriction nobody could read is
    precisely a hold, and treating an unknown as a pass is the one thing a label check must never
    do.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANYBODY'S REAL PROCEDURE. No manufacturer's
    guidance, assurance-scheme rule or regulation was consulted, and none is reproduced. A real
    holding weighs which restriction was breached and by how much, whether the crop is destined for
    food or feed, what the buyer's own assurance scheme requires, and who has authority to decide;
    this is two values and a comparison, chosen because it is the smallest condition that is
    genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    verdict = values.get("verdict")
    status = values.get("application_status")
    if verdict not in CK.VERDICTS or status not in ("planned", "applied"):
        return None
    return (verdict != "within_label") and (status == "applied")


def _locate(doc_text, secs, field, value):
    """Where in the case this field's value was read from.

    ⚠︎ ANCHORED TO THE FIELD'S OWN LABEL LINE FIRST, AND THAT IS NOT A REFINEMENT -- IT IS THE
    ONLY WAY A SPAN MEANS ANYTHING ON THIS LAYOUT. Eight numeric restrictions share one section
    here. A section-scoped search for the buffer `5` matches the `5` inside `2.5 L/ha` two lines
    above it, on a word boundary, correctly by the regex and wrongly by every other measure: the
    span would point a reader at the rate line and invite them to check a citation that appears to
    hold. So the search is anchored to the line the field is stated on (`data/fields.json`'s
    `line`), and only falls back to the section and then the document for a field that has no line
    -- the identifier, the status, the note, each of which is the whole body of its own section.
    """
    line = field.get("line")
    for s in selector.for_field(secs, field["name"]):
        if line:
            hit = segment.locate_in_line(s["text"], line, value)
        else:
            hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    if line:
        return None                       # a value not on its own line is not located, not guessed
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one case. `complete` is injectable so the eval harness, the app
    and tests all drive the same code path against a stub provider."""
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
        span = _locate(doc_text, secs, f, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_hold = compute(flat)
    recomputed = decide(flat)

    return {
        "fields": out,
        "needs_hold": needs_hold,
        "recomputed_verdict": recomputed["verdict"],
        "recomputed_restriction": recomputed["deciding_restriction"],
        "recomputed_reason": recomputed["reason"],
        "recomputed_checks": recomputed["checks"],
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
