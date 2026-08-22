"""Extract one screening alert's fields: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the escalation flag) is pure code.

⚠︎ THIS KIT PROPOSES AN ADJUDICATION. IT CLEARS NOTHING, BLOCKS NOTHING AND FILES NOTHING.
`extract()` returns a recommendation with the deciding identifier attached and names what it could
not determine; a human makes the call. No alert is closed, no party is designated or
de-designated, no account is frozen or released, no payment is stopped or let through, and no
report of any kind is made to anybody. Nothing in this file writes anything anywhere, and the
shipped rulebook is illustrative rather than an authority -- see src/rulebook.py and
data/SOURCES.md.

MAX_TOKENS -- see the note on the constant below.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from . import rulebook as RB

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ HEADROOM, NOT A TARGET, AND THE MARGIN IS RE-CHECKED OFF EVERY RUN RATHER THAN ASSERTED HERE.
# A seventeen-key JSON record over two short sections is a few hundred tokens of content; what a
# ceiling actually has to survive is provider-side reasoning, which on this model family is the
# majority of the output and is left at the provider's default by this harness.
#
# A cap that cuts a reply costs a WHOLE ALERT -- and on a screening queue an alert with no verdict
# is indistinguishable from an alert nobody looked at, which is worse than a wrong verdict because
# nothing marks it. A cap with headroom costs nothing at all: a reply that finishes is billed for
# what it used and not for the ceiling. A sibling kit in this series published three successive
# runs whose "failures" were nothing but a cap set from a smaller corpus, with a DIFFERENT set of
# records truncated each time.
#
# evals/run.py records `output_tokens_max` on every run, so this margin is a number in the result
# file rather than a claim in a comment. Run r001-sanction-screen's own figure is on the kit page.
MAX_TOKENS = 4000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(alert_id):
    with open(os.path.join(CORPUS, "%s.txt" % alert_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The rulebook adjudication re-derived from a set of extracted values.
    {verdict, deciding_identifier, reason, would_settle_it}.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN values for the
    no-gold consistency diagnostic.
    """
    return RB.decide(values.get("customer_identifier_type"),
                     values.get("customer_identifier_value"),
                     values.get("listed_identifier_type"),
                     values.get("listed_identifier_value"),
                     values.get("customer_dob"), values.get("listed_dob"),
                     values.get("customer_place_of_birth"), values.get("listed_place_of_birth"))


def correct_verdict(values):
    """Just the verdict string, or None when the values are outside the rulebook's vocabulary."""
    v = decide(values)["verdict"]
    return v if v in RB.VERDICTS else None


def correct_deciding_identifier(values):
    d = decide(values)["deciding_identifier"]
    return d if d in RB.DECIDING else None


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    alert a person has to reach first today", not "does this reply contradict itself".

    THE CONDITION: the alert is NOT DISMISSIBLE on the file -- the verdict is anything other than
    `not_a_match` -- AND the customer's account is already `live`.

    A pending onboarding can wait for a person to work the alert; nothing has moved yet. The same
    verdict on a LIVE account means money is moving for a party nobody has adjudicated, which is
    the alert that has to be reached today. `insufficient_information` counts here too,
    deliberately and emphatically -- an alert nobody can decide, on an account that is already
    running, is precisely the one to put in front of a human, and treating "cannot tell" as a
    clearance is the single worst thing anything in this kit could do.

    ⚠︎ IT IS A WORKLIST ORDERING AND NOTHING ELSE. It does not freeze the account, stop a payment,
    close or escalate a case, or notify anybody. It returns True, and a person decides what that
    is worth. This is also THIS KIT'S OWN SIMPLIFICATION, not anybody's real alert-handling
    policy: no supervisor's guidance, no institution's procedure and no regulatory rule was
    consulted, and none is reproduced. A real desk weighs the exposure, the customer's own risk
    rating, how long the alert has been open and who is allowed to decide it.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    verdict = values.get("verdict")
    status = values.get("account_status")
    if verdict not in RB.VERDICTS or status not in ("pending_onboarding", "live"):
        return None
    return (verdict != "not_a_match") and (status == "live")


def _locate(doc_text, secs, field_name, value):
    """Where in the alert sheet this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS IT MATTERS MORE THAN ON ALMOST ANY SIBLING. Ten of the twelve
    spannable fields come in CUSTOMER/LISTED pairs drawn from the same vocabulary, sitting in two
    adjacent sections, and on a `same_party` alert the two values are frequently the SAME STRING.
    An unscoped document-wide search would happily cite the Customer Record for a listed value
    that is genuinely correct, and the citation would look perfect. Scoping costs nothing and
    closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one alert. `complete` is injectable so the eval harness, the app
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
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_escalation = compute(flat)
    recomputed = decide(flat)

    return {
        "fields": out,
        "needs_escalation": needs_escalation,
        "recomputed_verdict": recomputed["verdict"],
        "recomputed_deciding_identifier": recomputed["deciding_identifier"],
        "recomputed_reason": recomputed["reason"],
        "recomputed_would_settle_it": recomputed["would_settle_it"],
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
