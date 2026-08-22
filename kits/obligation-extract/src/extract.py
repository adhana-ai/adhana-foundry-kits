"""Extract one contract pack's worksheet: segment, select, prompt, one model call, then a pure-code
business-condition check downstream. This is the whole AI layer of the kit -- everything above it
(segment, select) and below it (the review flag) is pure code.

⚠︎ THIS KIT PRODUCES A REVIEWER'S WORKSHEET. IT NEVER REACHES AN ACCOUNTING CONCLUSION.
`extract()` returns a row per ordered line with the rulebook's own reasoning attached and NAMES THE
LINES THE PAPERWORK DOES NOT SETTLE. It does not determine performance obligations, does not
allocate a transaction price, does not conclude on timing, does not open a revenue schedule and
does not write a journal entry. A controller does all of that, on the whole arrangement, against
the framework their company reports under. Nothing in this file writes, posts, approves or
dispatches anything, and the shipped rulebook is illustrative rather than an authority -- see
src/rulebook.py and data/SOURCES.md.

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
# provider-side reasoning left at the provider's default. Measured there: the largest reply used
# 3,398 output tokens, the mean was 1,882.5, and 8,967 of the 11,295 output tokens across the six
# calls (79.4 pct) were provider-side reasoning rather than the JSON worksheet. Nothing came close
# to the ceiling. The run is committed at results/eval-c000-obligation-extract-calibration.json.
#
# 8000 is ~2.4x the largest reply actually observed, and the headroom is deliberate. A REPLY HERE
# IS A LIST, which is the one way this kit's output differs structurally from its siblings': a
# seven-line pack is roughly forty per cent more JSON than a four-line one, and the calibration
# subset topped out at six lines, so the ceiling has to clear a pack LONGER than anything it
# measured. A sibling kit in this series published three successive runs whose "failures" were
# nothing but a cap set from a smaller corpus, with a DIFFERENT set of records truncated each time.
# A cap that cuts a reply costs a whole document; a cap with headroom costs nothing at all, because
# a reply that finishes is billed for what it used and not for the ceiling.
#
# evals/run.py records `output_tokens_max` on every run, so this margin can be re-checked without
# another calibration.
MAX_TOKENS = 8000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)


def item_fields(fields=None):
    return (fields or load_fields())["fields"]


def contract_fields(fields=None):
    return (fields or load_fields())["contract_fields"]


def load_doc(contract_id):
    with open(os.path.join(CORPUS, "%s.txt" % contract_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def decide(values):
    """The rulebook's two calls re-derived from one line's extracted facts.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words, and evals/judge.py runs it over the model's OWN facts for the
    no-gold consistency diagnostic.
    """
    return RB.decide(values.get("charge"), values.get("dependency"), values.get("timing"))


def compute(obligations):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "is this the
    contract somebody has to take back to the deal desk", not "does this reply contradict itself".

    THE CONDITION: the pack contains at least one line that the order form PRICES -- a fee of its
    own -- and whose separation call AND delivery pattern the paperwork settles NEITHER of.

    That combination is the one row a reviewer cannot leave alone. A line with no price of its own
    and an open call is a drafting untidiness; an open call with money attached is a number
    somebody will have to place, and the contract says neither where it goes nor when. It is the
    smallest condition that is genuinely useful and readable off one reply.

    ⚠︎ THE NARROWER CONDITION WAS CHOSEN OVER THE OBVIOUS ONE, AND THE REASON IS MEASURED RATHER
    THAN aesthetic. "A priced line whose SEPARATION is open" fires on 41 of this corpus's 50 packs
    -- 82 pct -- and a flag that is almost always on is a flag nobody reads and a grader that
    scores well by saying yes. Requiring both calls to be open splits the corpus properly, and it
    is also the sharper thing to say: the line is priced, and the paperwork answers neither
    question about it.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION, NOT ANY COMPANY'S REVIEW POLICY. No revenue policy,
    audit manual, accounting standard or standard-setter's guidance was consulted, and none is
    reproduced. A real review weighs the size of the fee against materiality, what the sales team
    can tell you that the paperwork cannot, whether a side letter exists, and what the same
    customer's previous orders said.

    Returns True / False, or None when the reply carries no line the rule can read -- an unknown
    is not a pass.
    """
    if not obligations:
        return None
    seen = False
    for o in obligations:
        charge, sep, pat = o.get("charge"), o.get("separation"), o.get("pattern")
        if (charge not in RB.CHARGES or sep not in RB.SEPARATIONS
                or pat not in RB.PATTERNS):
            continue
        seen = True
        if charge == "separate_fee" and sep == "not_determined" and pat == "not_determined":
            return True
    return False if seen else None


def _locate(doc_text, secs, field_name, value, item_code=None):
    """Where in the pack this value was read from -- searched INSIDE the sections src/select.py
    maps the field to, and for a per-line field, inside THAT LINE'S OWN Item section first.

    ⚠︎ SCOPED, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. Every pack carries five to seven
    Item sections drawn from the same small vocabulary of descriptions, so an unscoped
    document-wide search would happily cite one line's section for another line's label. Scoping
    costs nothing and closes the whole class.
    """
    if item_code:
        own = [s for s in secs if s["name"] == "Item %s" % item_code]
        for s in own:
            hit = segment.locate(s["text"], value)
            if hit:
                return s["start"] + hit[0], s["start"] + hit[1]
    for s in selector.for_field(secs, field_name):
        hit = segment.locate(s["text"], value)
        if hit:
            return s["start"] + hit[0], s["start"] + hit[1]
    return segment.locate(doc_text, value)


SPANNABLE = ("item_label",)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full worksheet for one contract pack. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw, fields)
    parsed_ok = bool(parsed)

    cfields = contract_fields(fields)
    ifields = item_fields(fields)

    contract = {}
    for f in cfields:
        v = parsed.get(f["name"])
        if v in ("", "null", "None"):
            v = None
        span = _locate(doc_text, secs, f["name"], v) if v is not None else None
        contract[f["name"]] = {
            "value": v, "spannable": True,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None)}

    rows = []
    for it in parsed.get("obligations") or []:
        code = it.get("item_code")
        cells = {}
        for f in ifields:
            name = f["name"]
            v = it.get(name)
            if v in ("", "null", "None"):
                v = None
            spannable = name in SPANNABLE or name == "item_code"
            span = (_locate(doc_text, secs, name, v, item_code=code)
                    if (v is not None and spannable) else None)
            cells[name] = {
                "value": v, "spannable": spannable,
                "span": ({"start": span[0], "end": span[1],
                          "section": segment.span_label(secs, span[0])} if span else None)}
        flat = {n: cells[n]["value"] for n in cells}
        d = decide(flat)
        cells["_recomputed"] = d
        rows.append(cells)

    flat_rows = [{n: c["value"] for n, c in r.items() if n != "_recomputed"} for r in rows]
    needs_review = compute(flat_rows)

    return {
        "contract": contract,
        "obligations": rows,
        "needs_drafting_review": needs_review,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
