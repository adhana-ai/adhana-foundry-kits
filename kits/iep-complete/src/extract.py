"""Check one education plan: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the worklist flag) is pure code.

⚠︎ THIS KIT PRODUCES A REVIEWER'S WORKLIST. IT NEVER APPROVES, SIGNS, FILES OR AMENDS A PLAN.
`extract()` returns a set of component states with the rulebook's own reasoning attached and names
what it could not determine; the team that writes the plan decides what goes in it. Nothing in this
file writes, submits, approves or amends anything, and the shipped rulebook is invented rather than
an authority -- see src/rulebook.py and data/SOURCES.md.

MAX_TOKENS -- MEASURED, not guessed. See the note on the constant below.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from . import rulebook as RB

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED ON THIS CORPUS, NOT INHERITED FROM A SIBLING KIT AND NOT GUESSED FROM ZERO. A
# calibration run of 6 plans was fired at max_tokens=16000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 1,258 output
# tokens, the mean was 1,147.3, and 5,903 of the 6,884 output tokens across the six calls (85.8 pct)
# were provider-side reasoning rather than the JSON record. Nothing came close to the ceiling.
#
# 5000 is ~4x the largest reply actually observed. The headroom is deliberate and it is not
# arbitrary: a sibling kit in this series published three successive runs whose "failures" were
# nothing but a cap set from a smaller corpus, and a DIFFERENT set of records truncated each time. A
# cap that cuts a reply costs a whole document; a cap with headroom costs nothing at all, because a
# reply that finishes is billed for what it used and not for the ceiling.
#
# ⚠︎ AND THIS KIT'S REPLY IS LARGER THAN ITS SIBLINGS', WHICH IS WHY THE CAP IS NOT THEIRS. Fourteen
# fields, of which seven are a judgement about a whole section, produce roughly twice the output of
# the ten-field sibling this shape was taken from. Copying that kit's 4000 would have been a cap set
# from somebody else's corpus -- the exact defect described above, one repository over.
#
# The calibration run is committed at results/eval-c000-iep-complete-calibration.json, and
# evals/run.py records `output_tokens_max` on every run so this margin can be re-checked without
# another calibration.
MAX_TOKENS = 5000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(plan_id):
    with open(os.path.join(CORPUS, "%s.txt" % plan_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The rulebook outcome re-derived from a set of extracted values.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN states for the
    no-gold consistency diagnostic.
    """
    states = {k: values.get(k) for k in RB.COMPONENTS}
    return RB.decide(states, values.get("pupil_age"))


def correct_outcome(values):
    """Just the outcome string, or None when the values are outside the rulebook's vocabulary."""
    o = decide(values)["outcome"]
    return o if o in RB.OUTCOMES else None


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    plan a reviewer has to pick up today", not "does this reply contradict itself".

    THE CONDITION: a plan whose outcome is anything other than `complete`, and which is ALREADY IN
    EFFECT.

    A draft that is missing a component can simply have the component written before it is signed;
    a draft with an unmeasurable goal can be rewritten at the table. The same finding on a plan
    already in effect means a pupil is being taught against it now -- against a goal nobody can
    measure, or a service with no frequency to deliver against -- and that is the row a reviewer
    should open first. `undetermined` counts here too, deliberately: a plan in effect whose
    transition requirement nobody can determine is precisely a row to work, and treating an unknown
    as a pass is the one thing a completeness check must never do.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANYBODY'S REVIEW POLICY. No district procedure,
    agency guidance or regulation was consulted, and none is reproduced. A real review queue weighs
    how long the plan has left to run, which component is missing, whether the next meeting is
    already booked and who has authority to reopen it; this is two values and a comparison, chosen
    because it is the smallest condition that is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    outcome = values.get("plan_outcome")
    status = values.get("plan_status")
    if outcome not in RB.OUTCOMES or status not in ("draft", "in_effect"):
        return None
    return (outcome != "complete") and (status == "in_effect")


def _locate(doc_text, secs, field_name, value):
    """Where in the plan this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS. `pupil_age` is a bare integer and small integers
    appear all over a plan -- goal criteria, service durations, session counts -- so an unscoped
    document-wide search would happily cite a service line for an age that is genuinely correct.
    Scoping costs nothing and closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one education plan. `complete` is injectable so the eval harness,
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
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    on_worklist = compute(flat)
    recomputed = decide(flat)

    return {
        "fields": out,
        "on_worklist": on_worklist,
        "recomputed_outcome": recomputed["outcome"],
        "recomputed_reason": recomputed["reason"],
        "recomputed_missing": recomputed["missing"],
        "recomputed_unmeasurable": recomputed["unmeasurable"],
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
