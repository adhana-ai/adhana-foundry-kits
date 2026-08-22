"""Extract one QC pack's fields: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the recompute flag) is pure code.

⚠︎ THIS KIT PRE-CHECKS A DRAFT. IT FILES NOTHING AND CLEARS NOTHING. `extract()` returns a
worklist of defects with the rulebook's own reasoning attached and names what it could not
determine; a qualified person decides what is submitted. Nothing in this file writes, transmits,
lodges, approves or closes anything, and the shipped rulebook is invented rather than an authority
-- see src/rulebook.py and data/SOURCES.md.

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
# calibration run of 6 packs was fired at max_tokens=16000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 2,682 output
# tokens, the mean was 1,939.3, and 10,526 of the 11,636 output tokens across the six calls
# (90.5 pct) were provider-side reasoning rather than the JSON record. Nothing came close to the
# ceiling. The run is committed at results/eval-c000-ctr-precheck-calibration.json.
#
# 8000 is ~3x the largest reply actually observed. The headroom is deliberate and it is not
# arbitrary: a sibling kit in this series published three successive runs whose "failures" were
# nothing but a cap set from a smaller corpus, and a DIFFERENT set of records truncated each time.
# A cap that cuts a reply costs a whole document; a cap with headroom costs nothing at all, because
# a reply that finishes is billed for what it used and not for the ceiling.
#
# ⚠︎ AND THE MARGIN IS NARROWER HERE THAN IN THE SIBLING KITS, BECAUSE THIS TASK REASONS MORE. Nine
# tenths of every reply is provider-side reasoning: the model is re-adding a cage log, applying a
# 06:00 boundary and walking a stopping order, none of which a transcription kit asks for. 6 packs
# is a small calibration for a corpus this varied, so evals/run.py records `output_tokens_max` on
# every run and this margin should be re-checked from a scored run rather than trusted from here.
MAX_TOKENS = 8000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(case_id):
    with open(os.path.join(CORPUS, "%s.txt" % case_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def assess(values):
    """The rulebook's own defect list re-derived from a set of extracted values.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN values for the
    no-gold consistency diagnostic.
    """
    return RB.assess(values.get("draft_reported_total"), values.get("log_qualifying_total"),
                     values.get("draft_window_applied"), values.get("linked_record_id"),
                     values.get("draft_includes_linked_record"),
                     values.get("missing_identification_elements"),
                     values.get("identification_captured_on"), values.get("gaming_day"),
                     values.get("miscoded_transaction_ids"))


def defect_set(raw):
    """A `defects_found` cell -> a set of rulebook codes, or None when it is unanswered.

    ⚑ 'none' IS AN ANSWER AND AN EMPTY SET IS ITS MEANING. A filing with nothing wrong with it is
    the single most important row in a QC kit -- it is the denominator of the false-alarm rate --
    so 'this filing is clean' and 'this reply did not answer' must never collapse into the same
    value. None means unanswered; set() means clean.

    A code the rulebook does not carry is DROPPED rather than kept, and a reply consisting only of
    such codes lands on the empty set. That is the conservative reading: an invented code is not a
    finding anybody can act on.
    """
    if raw in (None, ""):
        return None
    parts = [p.strip().lower() for p in str(raw).replace(";", ",").split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    if parts == ["none"]:
        return set()
    return {p for p in parts if p in RB.DEFECTS}


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "does the
    preparer have to recompute this filing before anyone submits it", not "does this reply
    contradict itself".

    THE CONDITION: the defect set contains at least one defect that changes WHAT WOULD BE FILED --
    a total that is wrong, a window that gathered the wrong entries, a person split across two
    records, a filing that should not exist at all, or a record nobody can compute a total from.

    A missing address element or a mis-coded transaction is corrected in place on the draft; the
    numbers still stand. An under-reported total is a different piece of work: it goes back to the
    preparer, and everything downstream of it has to be done again. Separating the two is the
    smallest useful thing a QC queue can say about a row beyond "this one has something wrong with
    it", and it is readable off one reply.

    `insufficient_information` counts here deliberately -- treating a record nobody can compute a
    total from as though it were clean is the one thing a pre-check must never do.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY COMPLIANCE PROGRAMME'S TRIAGE POLICY. No
    programme, filing instruction or supervisory guidance was consulted, and none is reproduced. A
    real desk weighs how close to the deadline the filing is, whether the patron is already under
    review, how large the shortfall is and who has authority to send it back; this is one set
    membership test, chosen because it is the smallest condition that is genuinely useful.

    Returns True / False, or None when the reply carries no defect answer at all -- an unknown is
    not a pass.
    """
    d = defect_set(values.get("defects_found"))
    if d is None:
        return None
    return bool(d & RB.RECOMPUTE_DEFECTS)


def _locate(doc_text, secs, field_name, value):
    """Where in the pack this field's value was read from -- searched INSIDE the sections
    src/select.py maps the field to, before falling back to the whole document.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. A transaction identifier and an
    amount both appear TWICE in every pack -- once on the draft and once in the log -- and the
    whole point of several cases is that the two copies disagree. An unscoped document-wide search
    would happily cite the log for a value read off the draft, which is precisely the distinction
    the reader is checking. Scoping costs nothing and closes the whole class.
    """
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


def _coerce_number(v):
    """'12400', '12,400', '12400 CU', 12400 -> 12400. Anything else -> None.

    ⚠︎ ACCEPTED, AND THEN MEASURED AS A HIT. The schema asks for a plain integer and the corpus
    prints plain integers, so a separator or a unit here is the model being helpful rather than
    wrong. Normalising it at the boundary means the arithmetic grade measures ARITHMETIC and not
    formatting -- which is the thing this kit actually wants to know about.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "").replace("CU", "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


NUMERIC_FIELDS = ("draft_reported_total", "log_qualifying_total")


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one QC pack. `complete` is injectable so the eval harness, the
    app and tests all drive the same code path against a stub provider."""
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
        # ⚠︎ "None" IS DELIBERATELY NOT IN THIS SENTINEL LIST, AND THAT IS A DIVERGENCE FROM THE
        # SIBLING KITS. `none` is a REAL value in this kit's defect vocabulary -- it is how a
        # clean filing is reported -- so collapsing a case-folded "None" to null would silently
        # delete the single most important answer a QC kit can give and move it into the
        # unanswered column, where it would look like caution instead of a lost clean row.
        if v in ("", "null"):
            v = None
        if name in NUMERIC_FIELDS:
            v = _coerce_number(v)
        spannable = f.get("spannable", f.get("type") != "enum")
        span = (_locate(doc_text, secs, name, v) if (v is not None and spannable) else None)
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_recompute = compute(flat)
    recomputed = assess(flat)

    return {
        "fields": out,
        "needs_recompute": needs_recompute,
        "recomputed_defects": sorted(recomputed["defects"]),
        "recomputed_reasons": recomputed["reasons"],
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
