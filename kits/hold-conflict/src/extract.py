"""Extract one records-disposition review's fields: segment, select, prompt, one model call, then
a pure-code business-condition check downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the review flag) is pure code.

⚠︎ THIS KIT PROPOSES; A RECORDS OFFICER RELEASES. `disposition_eligible` is a proposal about
whether a series may be put in front of somebody for destruction approval. Nothing here destroys,
deletes or disposes of anything, and the guardrail below is the opposite of a disposal action --
it pulls a series back OUT of a destruction queue.

⚑ MAX_TOKENS IS A MEASUREMENT, NOT A GUESS -- see results/eval-c000-ceiling.json. Before either
scored run, five records were run at a deliberately over-generous ceiling of 8,000 to find out
what this shape of reply actually costs. Every reply parsed, and the spread was enormous:

    output tokens   min 294   max 1,849      latency   min 2,623 ms   max 17,830 ms

The visible JSON is about 290 tokens on every one of them -- twelve fields, the longest of which
is a one-sentence note. So the record that billed 1,849 spent roughly 1,550 of them on
provider-side reasoning that never reaches `text`, and took six times as long to do it. THAT is
what the ceiling has to clear, and it is not knowable from the shape of the output.

6,000 is 3.2x the highest of those five. A ceiling set at the visible reply size would have
truncated that record into an unparseable reply and lost it from the run; a ceiling is only free
until something hits it, and only tokens actually produced are billed, so headroom above a
measured tail costs nothing and truncation costs a record.

⚠︎ FIVE CALLS IS A FLOOR ON THE TAIL, NOT THE TAIL. See `output_tokens_max` on every run record:
both scored runs report their own observed maximum, which is the only honest way to know whether
this number is still right.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 6000

# ⚑ ONE REVIEW DATE, DECLARED ONCE. src/prompt.py states it to the model, tools/build_corpus.py
# wrote gold against it, and evals/check_labels.py asserts the two agree. A "has this elapsed"
# question with a drifting today is a different question every run.
AS_OF = "2026-08"


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(case_id):
    with open(os.path.join(CORPUS, "%s.txt" % case_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _ym(value):
    """'YYYY-MM' or None. Deliberately strict: a date this cannot read is an unknown, and an
    unknown must not be allowed to look like an elapsed retention."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if len(v) != 7 or v[4] != "-":
        return None
    if not (v[:4].isdigit() and v[5:].isdigit()):
        return None
    if not 1 <= int(v[5:]) <= 12:
        return None
    return v


def eligibility(binding_hold, overlapping_expires, retention_expires, as_of=AS_OF):
    """THE RULE, in one place, collapsed to the three values a reply actually carries.

    tools/build_corpus.py::eligibility() is the same function, used to write gold; data/fields.json
    and src/prompt.py state it to the model in words. Three readers, one definition, so the corpus,
    the prompt and the guardrail cannot drift apart about what eligible means.

    Returns "yes" / "no", or None when a value the rule needs is missing or malformed.

    ⚠︎ IT DOES NOT RE-RUN THE HOLD SEARCH. `binding_hold` arrives already decided -- by the corpus
    generator when writing gold, and by the MODEL when this runs over a reply. That is the honest
    boundary of the self-consistency diagnostic in evals/judge.py: it can catch a reply whose
    verdict contradicts its own named hold and its own dates, and it is blind to a reply that
    names the WRONG hold and then reasons about it perfectly. See the note there.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED DISPOSITION RULE, NOT ANY JURISDICTION'S. No published
    general records schedule, disposition authority or hold procedure was consulted, and none is
    reproduced.
    """
    ret = _ym(retention_expires)
    if ret is None:
        return None
    if binding_hold not in (None, ""):
        if not isinstance(binding_hold, str):
            return None
        return "no"
    if overlapping_expires not in (None, ""):
        ov = _ym(overlapping_expires)
        if ov is None:
            return None
        if ov > as_of:
            return "no"
    if ret > as_of:
        return "no"
    return "yes"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kits in this
    series: it asks "is this the record somebody has to fix today", not "does this reply
    contradict itself".

    THE CONDITION: a series that is NOT eligible for disposition and is ALREADY SITTING IN THE
    DESTRUCTION QUEUE.

    A frozen series that nobody has queued can simply be left where it is -- the next review cycle
    will look at it again and nothing is at risk in the meantime. The same series already in the
    queue is one approval away from being destroyed under a live hold, which is the case a records
    office actually has to act on today: pull it out of the queue before the batch runs.

    ⚠︎ NOTE THE DIRECTION. This flag never proposes a destruction. It is a request to REMOVE
    something from a destruction queue, which is the only direction a decision like this should be
    automated in at all.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A REAL RECORDS PROGRAMME'S ESCALATION POLICY. A
    real records office weighs how close the destruction batch is, who issued the hold, whether
    counsel has been notified, and whether the series has already been certified for destruction;
    this is two values, chosen because it is the smallest rule that is genuinely useful and
    readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    eligible = values.get("disposition_eligible")
    queue = values.get("queue_status")
    if eligible not in ("yes", "no") or queue not in ("queued", "not_queued"):
        return None
    return (eligible == "no") and (queue == "queued")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THE SCOPING IS NOT COSMETIC. Two dates in the same record are
    both 'YYYY-MM' and can be equal; a project name appears in the title, in its own section and
    inside a hold's scope prose. An unscoped document-wide search would cite the first of those
    for a value that was correctly read from the last.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one disposition review. `complete` is injectable so the eval
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
        if v in ("", "null", "None", "none on file"):
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
    recomputed = eligibility(flat.get("binding_hold_id"), flat.get("overlapping_expires"),
                             flat.get("retention_expires"))

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_disposition_eligible": recomputed,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
