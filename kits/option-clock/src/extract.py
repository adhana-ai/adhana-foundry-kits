"""Extract one rights-and-option register snapshot: segment, select, prompt, one model call, then a
pure-code COUNT and a pure-code business-condition check downstream. This is the whole AI layer of
the kit -- everything above it (segment, select) and below it (the count and the escalation flag) is
pure code.

⚑ THE MODEL READS. THE CODE COUNTS. That split is the whole shape of this kit and it is not a
stylistic choice: a due date is arithmetic, and arithmetic done in prose is arithmetic nobody can
check. `extract()` returns the model's own claimed `expiry_date` and `status` as fields -- so the
gap between them and the count is measurable -- and it returns the COUNTED expiry and status
beside them. The counted one is the answer this kit publishes.

⚠︎ THIS KIT WATCHES NOTHING. It reads ONE snapshot that somebody else assembled and proposes a
worklist. It does not poll, subscribe, schedule, alert, escalate, file, exercise, renew, lapse or
clear, and nothing in it runs unattended. `escalate_now` is a value in a response, not an action.

⚠︎ AND IT PROPOSES ONLY. `extract()` returns a status with the count that produced it attached and
names what it could not determine; a qualified person reads the executed agreement. Nothing in this
file writes, dispatches or files anything, and the shipped rulebook is illustrative rather than an
authority -- see src/rulebook.py and data/SOURCES.md.

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
# provider-side reasoning left at its default. Measured there: the largest reply used 1,104 output
# tokens and the mean was 853.3, of which 4,002 of the 5,120 output tokens across the six calls
# (78.2 pct) were provider-side reasoning rather than the JSON record. Nothing came within an order
# of magnitude of the ceiling.
#
# ⚠︎ AND 6000 -- 5.4x THAT LARGEST OBSERVED REPLY -- WAS STILL NOT ENOUGH, WHICH IS THE FINDING
# THIS CONSTANT EXISTS TO CARRY. The first 50-register pass was fired at 6000 and LOST ONE
# REGISTER: ROR-0026 returned finish_reason=length at exactly 6,000 output tokens with an empty
# text body, and the same pass produced a reply of 5,456 -- five times anything the six-document
# calibration had seen. A six-document calibration measures the MIDDLE of the distribution and
# tells you nothing about its tail, and on a count with four ordered steps the tail is long,
# because the reasoning length is what varies between documents and it was 86 pct of the output on
# that run. The superseded pass is committed at results/eval-r000-option-clock-ceiling.json rather
# than deleted.
#
# 16000 is ~2.9x the largest reply the FULL corpus produced, and it is the ceiling the calibration
# itself ran under. The headroom is deliberate: a cap that cuts a reply costs a whole register, and
# on a monitoring worklist a register with no status is indistinguishable from a register nobody
# read. A cap with headroom costs nothing at all, because a reply that finishes is billed for what
# it used and not for the ceiling.
#
# ⚑ THE CALIBRATION EARNED ITS SIX CALLS TWICE. Besides the ceiling it caught an ambiguous field
# hint before any scored run: `property_title` was returning "A Title -- stage play", because the
# register writes the form of the work after the title and the hint did not say the form is not
# part of it. 3 of 6 replies did it. The hint in data/fields.json was tightened and the scored run
# fired afterwards. That is what a calibration is for -- finding it on the scored run would have
# meant either publishing a schema defect as a model failure or paying for the corpus twice.
#
# The calibration run is committed at results/eval-c000-option-clock-calibration.json, and
# evals/run.py records `output_tokens_max` on every run so this margin can be re-checked without
# another calibration.
MAX_TOKENS = 16000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(register_ref):
    with open(os.path.join(CORPUS, "%s.txt" % register_ref), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def count(values):
    """The rulebook count re-derived from a set of extracted values.
    {status, expiry_date, reason, days_to_expiry, clock_start_date, ...}.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN values -- both to
    produce this kit's published answer and for the no-gold consistency diagnostic.
    """
    return RB.decide(values.get("register_as_of"), values.get("clock_basis"),
                     values.get("trigger_status"), values.get("option_granted_date"),
                     values.get("trigger_date"), values.get("initial_term_months"),
                     values.get("extension_months_each"), values.get("extensions_perfected"))


def counted_status(values):
    """Just the counted status string, or None when the values are outside the rulebook's
    vocabulary."""
    s = count(values)["status"]
    return s if s in RB.STATUSES else None


def compute(status, register_status):
    """PURE CODE, run on whatever the system published -- never on gold.

    ⚑ IT TAKES THE PUBLISHED STATUS AS AN ARGUMENT RATHER THAN RECOUNTING IT, and that is what
    lets the free floor be routed by identical code. src/extract.py publishes the COUNT; the free
    floor in evals/baseline.py publishes the register's own status column. Both then go through
    this one function, so the two are comparable on the flag as well as on the answer, and a
    business-condition change cannot be made for one and forgotten for the other.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    register nobody knows is a problem", not "does this reply contradict itself".

    THE CONDITION: the COUNTED status is anything other than `live`, and the register still carries
    itself as `live`.

    An option the register already shows as lapsed is a known loss -- somebody has typed the bad
    news into the file and the desk can see it. The same count on a register still carrying `live`
    is the one nobody is looking at: it is on no report, it is in nobody's diary, and it will be
    found when somebody tries to exercise. `not_determinable` counts here too, deliberately --
    a record nobody can date, carried as live, is precisely the row to open first, and treating an
    unknown as a pass is the one thing a monitoring queue must never do.

    ⚑ NOTE WHAT THIS DOES WITH THE DECOY, BECAUSE IT LOOKS LIKE A CONTRADICTION AND IS NOT.
    `register_status` is never an input to the COUNT -- the count is arithmetic and the status line
    is not evidence about arithmetic. It IS an input to the ROUTING, because what the desk currently
    believes is exactly what decides whether this row is news. Reading a field for what it is
    evidence OF, rather than trusting or ignoring it wholesale, is the distinction this kit is
    built around.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT A RIGHTS DESK'S REAL ESCALATION POLICY. No
    company's procedure was consulted and none is reproduced. A real desk weighs what the property
    is worth, whether anybody still wants it, whether the counterparty would grant a fresh option
    anyway, and who has authority to spend the exercise money; this is two values and a comparison,
    chosen because it is the smallest condition that is genuinely useful and readable off one
    snapshot.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    if status not in RB.STATUSES or register_status not in RB.REGISTER_STATES:
        return None
    return (status != "live") and (register_status == "live")


def _locate(doc_text, secs, field_name, value):
    """Where in the register this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. A register states a grant date, a
    triggering-event date, a payment date, a file-opened date and a reindex date within a few lines
    of each other, all in the same ISO format, and `18` appears both as a term length and inside
    half the dates on the page. An unscoped document-wide search would happily cite the filing
    history for a trigger date that is genuinely correct. Scoping costs nothing and closes the whole
    class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one register snapshot. `complete` is injectable so the eval
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
        # ⚑ A FIELD MAY DECLARE ITSELF UNSPANNABLE, AND THREE HERE DO. `expiry_date` is a COUNT and
        # is nowhere on the register; `extensions_recorded_taken` and `extensions_perfected` are
        # counts over the extension entries rather than a value stated in one place. Scoring them
        # for a span would count a correct answer as an unlocated one, which would make the span
        # rate a number about the field schema rather than about the model.
        spannable = f.get("spannable") is not False and f.get("type") != "enum"
        span = _locate(doc_text, secs, name, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    counted = count(flat)
    escalate = compute(counted["status"], flat.get("register_status"))

    return {
        "fields": out,
        # ⚑ THE ANSWER THIS KIT STANDS BEHIND IS THE COUNT, NOT THE MODEL'S CLAIM. `published_*` is
        # the key the harness and the scorer read, and evals/baseline.py fills the same two keys
        # with the register's own status column -- so the two systems are graded through identical
        # code and neither gets a grader written for it.
        "published_status": counted["status"],
        "published_expiry_date": counted["expiry_date"],
        "escalate_now": escalate,
        "counted_status": counted["status"],
        "counted_expiry_date": counted["expiry_date"],
        "counted_clock_start_date": counted["clock_start_date"],
        "counted_days_to_expiry": counted["days_to_expiry"],
        "counted_reason": counted["reason"],
        "undetermined_because": counted["undetermined_because"],
        "window_days": RB.WINDOW_DAYS,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
