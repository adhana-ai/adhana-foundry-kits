"""Extract one attestation register: segment, select, prompt, ONE model call, then the pure-code
rule and a pure-code business condition downstream. This is the whole AI layer of the kit --
everything above it (segment, select) and below it (the status rule, the owner-review flag) is
pure code.

⚠︎ THIS KIT WATCHES NOTHING AND CHASES NOBODY. `extract()` returns a proposed worklist with the
rulebook's own reasoning attached and names what it could not determine. It does not poll,
subscribe, schedule, alert, escalate, chase, file, sign off or clear, and nothing in this file
writes anywhere. The shipped rulebook is illustrative rather than an authority -- see
src/rulebook.py and data/SOURCES.md.

⚑ THE MODEL READS. IT DOES NOT DECIDE. Every reply carries the model's own `status` and its own
`due_on`, and BOTH ARE MEASURED AND NEITHER IS PUBLISHED. What the kit publishes is
`computed_status` and `computed_due_on` -- src/rulebook.py run over whatever values came back.
That is what makes the date arithmetic a clean measurement of arithmetic and the status a clean
measurement of the pipeline.

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
# calibration run of 3 registers was fired at max_tokens=20000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 6,574 output
# tokens, the mean was 4,531, and 11,741 of the 13,593 output tokens across the three calls
# (86.4 pct) were provider-side REASONING rather than the JSON register. Nothing came within a
# third of the ceiling. Committed at results/eval-c000-attestation-watch-calibration.json.
#
# 16000 is ~2.4x the largest reply actually observed, and the margin is deliberately wider than a
# flat-record kit would need: a reply here is not one JSON object, it is a roster of them, so the
# ceiling has to clear the LONGEST register in the corpus rather than an average one. The
# calibration saw a six-person register; the corpus goes to seven.
#
# The headroom is deliberate and it is not arbitrary: a sibling kit in this series published three
# successive runs whose "failures" were nothing but a cap set from a smaller corpus, and a
# DIFFERENT set of records truncated each time. A cap that cuts a reply costs a whole register --
# and on a monitoring kit a cut register is worse than a wrong one, because it produces no worklist
# at all and an engagement with no worklist looks exactly like an engagement with nothing to do.
# A cap with headroom costs nothing, because a reply that finishes is billed for what it used and
# not for the ceiling.
#
# ⚠︎ AND IT WAS STILL NOT ENOUGH ONCE, WHICH IS RECORDED HERE RATHER THAN QUIETLY RAISED. The
# scored run r001-attestation-watch lost ONE register of 50 -- ATT-0015, a seven-person one -- to a
# reply that hit exactly 16,000 output tokens with `finish_reason: length` and NO TEXT AT ALL: the
# whole ceiling went on provider-side reasoning and the JSON never started. The largest reply that
# DID finish used 13,333. So a ceiling set at 2.4x the calibrated maximum still cost a register,
# and the cause is not reply length, it is a reasoning pass that ran away.
#
# THE CONSTANT IS DELIBERATELY NOT RAISED AFTER THE FACT. Every figure this kit publishes was
# measured under 16000, and moving it now would put the code and the published run under different
# ceilings -- which is the exact confusion the `--max-tokens` guard in evals/run.py exists to
# prevent. A forker raising it should re-run and re-publish, not inherit our numbers under their
# ceiling. What the run record shows is in results/eval-r001-attestation-watch.json's `failures`.
#
# evals/run.py records `output_tokens_max` on every run, so this margin can be re-checked from any
# scored run without firing another calibration.
MAX_TOKENS = 16000


def load_fields():
    """{"register": [...], "attester": [...]}. Two sets, because the document is a REGISTER and the
    unit of the answer is a PERSON."""
    with open(FIELDS, encoding="utf-8") as f:
        d = json.load(f)
    return {"register": d["register"], "attester": d["attester"]}


def attester_key(fields):
    for f in fields["attester"]:
        if f.get("key"):
            return f["name"]
    return "person_ref"


def scored_attester_fields(fields):
    """Every per-person field except the alignment key. The key is not a scored cell -- it is what
    a row is matched BY, so scoring it would be scoring the join, and every joined row would be a
    free hit. Coverage of the roster is reported on its own instead."""
    return [f for f in fields["attester"] if not f.get("key")]


def load_doc(register_id):
    with open(os.path.join(CORPUS, "%s.txt" % register_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The rulebook's status re-derived from one person's extracted values.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN values.
    """
    return RB.decide(values)


def correct_status(values):
    s = decide(values)["status"]
    return s if s in RB.STATUSES else None


def compute(statuses):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL ROUTES A REGISTER, IT DOES NOT GRADE A PERSON. It asks "does this engagement
    need somebody to OPEN THE FILE, rather than somebody to send a reminder".

    THE CONDITION: the register carries at least one `contradicted` attester, or at least one
    `not_determinable` one.

    A missing or a stale attestation is cleared by asking a person for a form -- that is a chase,
    and an administrator can run it. A contradiction is not: two returns that disagree, or a
    register that records a relationship as gone before somebody declared it, are questions about
    which record is true, and no reminder answers them. A `not_determinable` row is the same shape
    one layer down -- the register itself cannot be read, so there is nothing to remind anybody
    about. Routing both to the same queue as a chase is how they get buried under it.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANYBODY'S ESCALATION POLICY. No firm's procedure,
    professional standard or regulatory rule was consulted, and none is reproduced. A real practice
    weighs who the person is, what the engagement is, how close sign-off is and who already knows.
    It is one predicate over a list of statuses, chosen because it is the smallest condition that
    is genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    if not statuses or any(s not in RB.STATUSES for s in statuses):
        return None
    return any(s in ("contradicted", "not_determinable") for s in statuses)


def _locate(doc_text, secs, field_name, value, person_ref=None):
    """Where in the register this value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. Four sections carry ISO dates
    and four carry person references, so an unscoped document-wide search would happily cite the
    Returns Filed section for a cycle-opened date that is genuinely correct.

    ⚑ AND SCOPED TWICE, BY PERSON AS WELL AS BY SECTION. Within a section a value is looked for on
    THIS PERSON'S OWN LINE first: two people on the same register frequently declare the same
    relationship, and a span pointing at somebody else's line is worse than no span -- it invites a
    reader to check, and the check appears to succeed.
    """
    for s in selector.for_field(secs, field_name):
        if person_ref:
            for line_start, line in _lines_for(s, person_ref):
                hit = segment.locate(line, value)
                if hit:
                    return line_start + hit[0], line_start + hit[1]
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def _lines_for(section, person_ref):
    """[(absolute_offset, line)] for the lines of a section that name this person."""
    out, pos = [], section["start"]
    for line in section["text"].splitlines(True):
        if person_ref in line:
            out.append((pos, line))
        pos += len(line)
    return out


def _cell(doc_text, secs, f, value, person_ref=None):
    v = value
    if v in ("", "null", "None"):
        v = None
    spannable = f.get("type") not in ("enum", "derived")
    span = (_locate(doc_text, secs, f["name"], v, person_ref)
            if (v is not None and spannable) else None)
    return {"value": v, "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None)}


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one attestation register. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    reg_values, att_rows = P.parse(raw, fields)
    parsed_ok = bool(att_rows) and any(v is not None for v in reg_values.values())

    register = {f["name"]: _cell(doc_text, secs, f, reg_values.get(f["name"]))
                for f in fields["register"]}

    key = attester_key(fields)
    attesters = []
    for row in att_rows:
        ref = row.get(key)
        ref = str(ref).strip() if ref not in (None, "") else None
        cells = {f["name"]: _cell(doc_text, secs, f, row.get(f["name"]), ref)
                 for f in fields["attester"]}
        flat = {name: cells[name]["value"] for name in cells}
        d = decide(flat)
        attesters.append({
            "person_ref": ref,
            "fields": cells,
            "computed_status": d["status"],
            "computed_reason": d["reason"],
            "computed_due_on": d["due_on"],
            "computed_stale_after": d["stale_after"],
            "not_determinable_because": d["not_determinable_because"],
        })

    statuses = [a["computed_status"] for a in attesters]
    return {
        "register": register,
        "attesters": attesters,
        # ⚑ THE WORKLIST IS THE PRODUCT. Three statuses, in the order the rule found them, and
        # nothing acts on it.
        "worklist": [a["person_ref"] for a in attesters
                     if a["computed_status"] in RB.WORKLIST],
        "not_determinable": [a["person_ref"] for a in attesters
                             if a["computed_status"] == "not_determinable"],
        "needs_owner_review": compute(statuses),
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
