"""Extract one student-account tuition assessment's fields: segment, select, prompt, one model
call, then a pure-code business-condition check downstream. This is the whole AI layer of the kit
-- everything above it (segment, select) and below it (the review flag) is pure code.

MAX_TOKENS -- MEASURED, NOT GUESSED. Three calibration calls were made against this corpus at a
deliberately generous ceiling before either scored run, and the ceiling here is set from what they
actually returned. See results/eval-c000-calibrate.json and the note beside MAX_TOKENS below.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ SET FROM A MEASUREMENT, AND THE MEASUREMENT IS IN THE REPO. The three-record calibration run
# (run id c000-calibrate, ceiling deliberately set to 8000 so nothing could hit it) returned 382,
# 460 and 1,209 output tokens with `finish_reason` "stop" on all three -- so nothing was being cut
# off, and the runaway reasoning pass that eats other kits' budgets is not eating this one. 4000 is
# that observed maximum with about 3.3x of headroom: room for a slower-thinking tier and a longer
# bursar note, and not so much that a genuine runaway would go unnoticed for long.
# ⚠︎ A CEILING IS NOT FREE HEADROOM. A reply cut off at the ceiling does not parse, and
# evals/run.py records exactly that -- finish_reason, the output token count and the ceiling, plus
# `output_tokens_max` on every run -- so a future ceiling problem arrives as evidence rather than
# as a mystery. `--max-tokens` on the harness is how the calibration above was taken; it is a
# measurement tool, not a knob to turn when a run misbehaves.
MAX_TOKENS = 4000

# ---------------------------------------------------------------------------------------------
# ⚠︎ THE RATE TABLE IS THIS KIT'S OWN INVENTION, NOT ANY INSTITUTION'S PUBLISHED SCHEDULE. It is
# the same table tools/build_corpus.py used to write gold and the same one src/prompt.py states to
# the model in words. Three readers, one definition.
# ---------------------------------------------------------------------------------------------

FULL_TIME_CREDITS = 12                                   # INCLUSIVE: exactly 12 is full-time
PER_CREDIT = {"In-State": 410, "Out-of-State": 1180}
FLAT_TERM = {"In-State": 4600, "Out-of-State": 13200}
DIFFERENTIAL = {"Lower Division": 0, "Upper Division": 38, "Graduate": 65}
MANDATORY_FULL = 612
MANDATORY_PART = 306
WAIVERS = {
    "None": (0, False),
    "Employee Tuition Remission": (100, False),
    "Staff Dependent Waiver": (50, False),
    "Regents Fee Waiver": (100, True),
}

REASONS = ["none", "credit band", "residency tier", "differential fee", "waiver coverage",
           "mandatory fee"]


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _num(v):
    """A number, or None. A bool is not a number here -- True would otherwise price as 1 credit."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def assess(residency_tier, enrolled_credits, course_level, waiver_type):
    """THE RATE TABLE, run over whatever values are handed to it. Returns the correct total in
    whole dollars, or None when a value the table needs is missing or malformed.

    ⚠︎ THIS IS THIS KIT'S OWN INVENTED RATE TABLE, NOT A REAL TUITION SCHEDULE. No published rate
    schedule, fee bill, waiver programme or residency regulation was consulted, and none is
    reproduced.
    """
    if residency_tier not in PER_CREDIT or course_level not in DIFFERENTIAL:
        return None
    if waiver_type not in WAIVERS:
        return None
    credits = _num(enrolled_credits)
    if credits is None or credits <= 0:
        return None

    full_time = credits >= FULL_TIME_CREDITS
    tuition = FLAT_TERM[residency_tier] if full_time else credits * PER_CREDIT[residency_tier]
    differential = credits * DIFFERENTIAL[course_level]      # never waived, whatever the waiver is
    mandatory = MANDATORY_FULL if full_time else MANDATORY_PART
    pct, covers = WAIVERS[waiver_type]
    waivable = tuition + (mandatory if covers else 0)
    waived = waivable * pct // 100
    return int(tuition + differential + mandatory - waived)


def is_assessment_correct(assessed_total, residency_tier, enrolled_credits, course_level,
                          waiver_type):
    """"yes" / "no", or None when the table could not be run. Same comparison used by
    tools/build_corpus.py to write gold and stated in words by src/prompt.py."""
    want = assess(residency_tier, enrolled_credits, course_level, waiver_type)
    got = _num(assessed_total)
    if want is None or got is None:
        return None
    return "yes" if int(got) == want else "no"


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, the same shape as the sibling kits before this one
    in the series: it asks "is this the account somebody has to fix today", not "does this reply
    contradict itself".

    THE CONDITION: a mis-assessed account whose bill has ALREADY POSTED to the student account.

    A mis-assessed account still in draft can simply be corrected before it posts -- nothing has
    reached the student. The same variance on a posted bill means a corrected bill or a refund, a
    student who may already have paid it, and in a real office an aid recalculation behind it. That
    is the case a bursar's desk actually has to work today.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY INSTITUTION'S BILLING-ADJUSTMENT POLICY. No
    published schedule, regulation or bursar procedure was consulted, and none is reproduced. A
    real office weighs the dollar size of the variance, whether aid has disbursed against it, and
    any refund-deadline rule; this is two booleans, chosen because it is the smallest rule that is
    genuinely useful and readable off one reply.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    correct = values.get("assessment_correct")
    status = values.get("bill_status")
    if correct not in ("yes", "no") or status not in ("draft", "posted"):
        return None
    return (correct == "no") and (status == "posted")


def _locate(doc_text, secs, field_name, value):
    """Where in the document this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THE SCOPING IS MEASURED TO CHANGE NOTHING. An earlier version of
    this docstring claimed the opposite -- that an unscoped search would cite the residency ACTION
    line ("Reclassified to In-State ...") for the tier of record, on every record where the two
    agree in spelling. THAT WAS FALSE, and falsifying it took one loop: `residency_tier` is an
    ENUM, enums are not spannable, and no span is ever computed for it. Re-locating all six
    spannable fields across all 55 records both ways produces 0 differences out of 324 values.

    It stays because the class it closes is real in the sibling kits -- a demand reading and a
    usage figure sharing digits, an ordered and a delivered quantity that are the same number on a
    correct record -- and because it costs nothing. Not because this corpus needs it. A rule kept
    for a reason that was checked and found untrue is worse than no rule at all; a rule kept for a
    reason honestly stated as precautionary is fine.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one student-account tuition assessment. `complete` is injectable
    so the eval harness, the app and tests all drive the same code path against a stub provider."""
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
        if v in ("", "null", "None") and name != "waiver_type":
            # ⚠︎ "None" IS A REAL VALUE OF waiver_type ON THIS CORPUS, not an absence. Folding it
            # into null the way every other field's empty string is folded would silently turn
            # fifteen accounts with no waiver into fifteen unanswered cells.
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
    recomputed = is_assessment_correct(flat.get("assessed_total_usd"), flat.get("residency_tier"),
                                       flat.get("enrolled_credits"), flat.get("course_level"),
                                       flat.get("waiver_type"))

    return {
        "fields": out,
        "needs_review": needs_review,
        "recomputed_assessment_correct": recomputed,
        "recomputed_total_usd": assess(flat.get("residency_tier"), flat.get("enrolled_credits"),
                                       flat.get("course_level"), flat.get("waiver_type")),
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
