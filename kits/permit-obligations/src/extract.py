"""Read one site's permit obligation register: segment, select, prompt, one model call, then the
pure-code status rule and one business-condition check downstream. This is the whole AI layer of the
kit -- everything above it (segment, select) and everything below it (the status of every obligation,
the worklist, the escalation flag) is pure code.

⚠︎ THIS KIT WATCHES NOTHING. It reads ONE SNAPSHOT that somebody else assembled, as at the register
date printed on it, and proposes a worklist. It does not poll, subscribe, schedule, alert, escalate,
file, submit, renew or clear, and nothing in it runs unattended. `extract()` returns a status per
obligation with the rulebook's own reasoning attached and names what it could not determine; a
qualified person reads the permit. The shipped rulebook is illustrative rather than an authority --
see src/rulebook.py and data/SOURCES.md.

⚠︎ THE MODEL NEVER RETURNS A STATUS. It returns what the register records. `src/rulebook.py::decide`
turns that into overdue / due_in_window / not_yet_due / not_binding / not_determinable. So every
status error on this kit's published numbers is an inherited READING error, and the false-alarm rate
is a measurement of reading accuracy propagated through a rule -- which is exactly what a monitoring
desk is buying and is worth saying out loud rather than leaving for somebody to work out.

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
# calibration run of 6 registers was fired at max_tokens=16000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 2,097 output
# tokens, the mean was 987.2, and 3,588 of the 5,923 output tokens across the six calls (60.6 pct)
# were provider-side reasoning rather than the JSON record. Nothing came close to the ceiling.
#
# 8000 is ~3.8x the largest reply actually observed. The headroom is deliberate and it is not
# arbitrary: a sibling kit in this series published three successive runs whose "failures" were
# nothing but a cap set from a smaller corpus, and a DIFFERENT set of records truncated each time.
# A cap that cuts a reply costs a whole register -- and on a monitor, a lost register is not a lost
# score, it is a site nobody looked at. A cap with headroom costs nothing at all, because a reply
# that finishes is billed for what it used and not for the ceiling.
#
# ⚠︎ AND THE REPLY LENGTH HERE IS NOT FIXED THE WAY A FLAT-RECORD KIT'S IS. This corpus returns one
# entry per condition block and a register carries 4 to 7 of them, so the JSON alone varies by
# nearly a factor of two between the smallest and largest register. The calibration deliberately
# covered both ends rather than the first six files.
#
# The calibration run is committed at results/eval-c000-permit-obligations-calibration.json, and
# evals/run.py records `output_tokens_max` on every run so this margin can be re-checked without
# another calibration.
MAX_TOKENS = 8000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_obligation_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["obligation_fields"]


def load_doc(register_id):
    with open(os.path.join(CORPUS, "%s.txt" % register_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def statuses(values):
    """The rulebook run over a whole extracted record. [{condition_id, status, reason, due_date...}].

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words as context for WHY each field matters, and evals/judge.py runs it over
    the model's OWN values to build the worklist that is scored.
    """
    rd = values.get("register_date")
    out = []
    for ob in values.get("obligations") or []:
        d = RB.decide(rd, ob)
        out.append(dict(d, condition_id=ob.get("condition_id"),
                        obligation_type=ob.get("obligation_type")))
    return out


def escalate_from(decided, obligations):
    """The business condition, over an already-decided list of statuses and their register flags.

    ⚑ SPLIT OUT FROM `compute()` SO THE FREE FLOOR CAN BE ROUTED BY IDENTICAL CODE. evals/baseline.py
    derives its statuses from the site's own register flag instead of from the rulebook, and it must
    still be routed by the same guardrail a real run is routed by -- otherwise the floor's guardrail
    number measures a different guardrail and the comparison is worthless. One function, two
    callers, no second copy of the condition.
    """
    unreadable = False
    for d, ob in zip(decided, obligations or []):
        if (d or {}).get("status") != "overdue":
            continue
        flag = (ob or {}).get("register_flag")
        if flag in ("on track", "closed"):
            return True
        if flag != "attention":
            unreadable = True
    return None if unreadable else False


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the site
    somebody has to look at before the others", not "does this reply contradict itself".

    THE CONDITION: the register carries at least one obligation the rulebook makes OVERDUE, and that
    row's own `register_flag` -- the site's self-assessment -- reads `on track` or `closed`.

    An overdue row already flagged `attention` is a site that knows. It may still be a problem, but
    somebody is looking at it. An overdue row flagged `on track` or `closed` is the other thing
    entirely: the site's own tracker is quiet about something that has already lapsed, so nobody is
    looking, and no amount of chasing the site's own list will surface it. That is the register a
    compliance desk should open first, and it is the one thing on this page that a person would act
    on before reading anything else.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY REAL ESCALATION POLICY. No permit, no
    regulator's guidance and no operator's procedure was consulted, and none is reproduced. A real
    compliance function weighs which condition lapsed, by how long, whether the breach is reportable
    in its own right, whether the administering body already knows, and who is authorised to
    disclose it. This is two values and a comparison, chosen because it is the smallest condition
    that is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs. An unknown is
    neither a pass nor an alarm here: raising on a row whose flag could not be read would be a false
    alarm, and clearing it would be a silent one.
    """
    rd = values.get("register_date")
    obs = values.get("obligations")
    if not rd or not isinstance(obs, list) or not obs:
        return None
    return escalate_from(statuses(values), obs)


def _cell(doc_text, secs, ob_field, value, condition_id=None):
    """One extracted value, with the span it was read from where one can be located.

    ⚠︎ SCOPED TO THE CONDITION'S OWN BLOCK. Every block on a register carries the same nine line
    labels and dates drawn from the same few months, so a document-wide search would cite condition
    C-3.1's block for a date that genuinely belongs to C-8.4 and the citation would look correct.
    Where the value cannot be found inside its own block it ships WITHOUT a span rather than with a
    guessed one -- an approximate span invites a reader to check, and the check appears to succeed.
    """
    spannable = ob_field.get("type") != "enum"
    span = None
    if value is not None and spannable:
        for s in selector.for_condition(secs, condition_id) if condition_id else \
                selector.for_field(secs, ob_field["name"]):
            hit = segment.locate(s["text"], value)
            if hit:
                span = (s["start"] + hit[0], s["start"] + hit[1])
                break
    return {"value": value, "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None)}


def extract(cfg, doc_text, fields, ob_fields, complete=None, thinking=None):
    """Return the full record for one obligation register. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, ob_fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    top, rows = P.parse(raw, fields, ob_fields)
    parsed_ok = rows is not None and bool(top)

    out_fields = {}
    for f in fields:
        v = top.get(f["name"])
        if v in ("", "null", "None"):
            v = None
        out_fields[f["name"]] = _cell(doc_text, secs, f, v)

    obligations = []
    for r in rows or []:
        cid = r.get("condition_id")
        cells = {}
        for f in ob_fields:
            v = r.get(f["name"])
            if v in ("", "null", "None"):
                v = None
            cells[f["name"]] = _cell(doc_text, secs, f, v, condition_id=cid)
        obligations.append({"condition_id": cid, "cells": cells,
                            "values": {k: cells[k]["value"] for k in cells}})

    flat = {name: out_fields[name]["value"] for name in out_fields}
    flat["obligations"] = [o["values"] for o in obligations]

    decided = statuses(flat)
    for ob, d in zip(obligations, decided):
        ob["status"] = d["status"]
        ob["reason"] = d["reason"]
        ob["due_date"] = d["due_date"]
        ob["days_to_due"] = d["days_to_due"]
        ob["undetermined_because"] = d["undetermined_because"]

    return {
        "fields": out_fields,
        "obligations": obligations,
        "worklist": [o["condition_id"] for o in obligations if o["status"] in RB.ACTIONABLE],
        "escalate": compute(flat),
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
