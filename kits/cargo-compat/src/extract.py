"""Extract one pre-load check sheet's fields: segment, select, prompt, one model call, then a
pure-code business-condition check downstream. This is the whole AI layer of the kit -- everything
above it (segment, select) and below it (the hold flag) is pure code.

⚠︎ THIS KIT PROPOSES A VERDICT. IT NEVER AUTHORISES A LOAD. `extract()` returns a recommendation
with the matrix's own reasoning attached and names what it could not determine; a qualified person
authorises the load, against the incoming product's safety data sheet and the tank's real cleaning
record. Nothing in this file writes, dispatches, releases or clears anything, and the shipped
matrix is illustrative rather than an authority -- see src/matrix.py and data/SOURCES.md.

MAX_TOKENS -- MEASURED, not guessed. See the note on the constant below.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from . import matrix as MX

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED ON THIS CORPUS, NOT INHERITED FROM A SIBLING KIT AND NOT GUESSED FROM ZERO. A
# calibration run of 6 sheets was fired at max_tokens=16000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 597 output
# tokens, the mean was 488.2, and 2,232 of the 2,929 output tokens across the six calls (76.2 pct)
# were provider-side reasoning rather than the JSON record. Nothing came close to the ceiling.
#
# 4000 is ~6.7x the largest reply actually observed. The headroom is deliberate and it is not
# arbitrary: a sibling kit in this series published three successive runs whose "failures" were
# nothing but a cap set from a smaller corpus, and a DIFFERENT set of records truncated each time.
# A cap that cuts a reply costs a whole document; a cap with headroom costs nothing at all, because
# a reply that finishes is billed for what it used and not for the ceiling.
#
# The calibration run is committed at results/eval-c000-calibration.json, and evals/run.py records
# `output_tokens_max` on every run so this margin can be re-checked without another calibration.
MAX_TOKENS = 4000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(check_id):
    with open(os.path.join(CORPUS, "%s.txt" % check_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The matrix verdict re-derived from a set of extracted values. {verdict, reason, ...}.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN values for the
    no-gold consistency diagnostic.
    """
    return MX.decide(values.get("incoming_product"), values.get("incoming_grade"),
                     values.get("prior_cargo"), values.get("two_back_cargo"),
                     values.get("wash_certified_for"))


def correct_verdict(values):
    """Just the verdict string, or None when the values are outside the matrix's vocabulary."""
    v = decide(values)["verdict"]
    return v if v in MX.VERDICTS else None


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    tank somebody has to act on right now", not "does this reply contradict itself".

    THE CONDITION: a tank whose verdict is anything other than `accept`, and whose incoming
    product has ALREADY BEEN LOADED.

    A pending load that needs cleaning can simply be cleaned before it goes in, and a pending load
    that must be refused can simply be refused -- nothing has happened yet. The same verdict on a
    tank already loaded means product is sitting on a residue it should not be sitting on, which
    is the case a terminal has to deal with today: quarantine it, sample it, and get a competent
    person to it. `undetermined` counts here too, deliberately -- product already in a tank whose
    prior cargo nobody recorded is precisely a hold, and treating an unknown as a pass is the one
    thing a pre-load check must never do.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A TERMINAL'S REAL QUARANTINE POLICY. No
    operator's procedure, industry code or regulatory rule was consulted, and none is reproduced.
    A real terminal weighs how much product is in the tank, whether it can still be diverted,
    what the receiving customer's own specification says, and who has authority to release it;
    this is two values and a comparison, chosen because it is the smallest condition that is
    genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    verdict = values.get("verdict")
    status = values.get("load_status")
    if verdict not in MX.VERDICTS or status not in ("pending", "loaded"):
        return None
    return (verdict != "accept") and (status == "loaded")


def _locate(doc_text, secs, field_name, value):
    """Where in the sheet this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. `prior_cargo` and
    `two_back_cargo` are drawn from the SAME cargo vocabulary and sit in adjacent sections, so an
    unscoped document-wide search would happily cite the Prior Cargo section for a two-back value
    that is genuinely correct. Scoping costs nothing and closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one pre-load check sheet. `complete` is injectable so the eval
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
    needs_hold = compute(flat)
    recomputed = decide(flat)

    return {
        "fields": out,
        "needs_hold": needs_hold,
        "recomputed_verdict": recomputed["verdict"],
        "recomputed_reason": recomputed["reason"],
        "recomputed_required_wash": recomputed["required_wash"],
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
