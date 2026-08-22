"""Extract one scheduling order's deadlines: segment, select, prompt, one model call, then two
pure-code passes downstream. This is the whole AI layer of the kit -- everything above it (segment,
select) and below it (the recomputed date and the undatable flag) is pure code.

⚠︎ THIS KIT COMPUTES A PROPOSED CALENDAR. IT NEVER FILES, SERVES, DOCKETS OR WAIVES ANYTHING.
`extract()` returns arithmetic with its own working attached and names what it could not date; a
person with the file and the rules that actually govern it decides what goes on the calendar.
Nothing in this file writes, sends or docketed anything, and the shipped rulebook is illustrative
rather than an authority -- see src/calendar_rules.py and data/SOURCES.md.

⚑ TWO ANSWERS PER OBLIGATION, ON PURPOSE. `due_date` is the model's own arithmetic and
`computed_date` is src/calendar_rules.py::compute() re-run over the model's OWN extracted values.
Keeping both is what lets evals/judge.py separate "it did not find the obligation" from "it found
the obligation and mis-dated it" -- which is the number this kit exists to publish -- and it is
what makes the no-gold consistency diagnostic possible on orders nobody has labelled.

MAX_TOKENS -- MEASURED, not guessed. See the note on the constant below.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P
from . import calendar_rules as CR

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ MEASURED ON THIS CORPUS, NOT INHERITED FROM A SIBLING KIT AND NOT GUESSED FROM ZERO. A
# calibration run of 6 orders was fired at max_tokens=16000 BEFORE any scored run, with
# provider-side reasoning left at its default. Measured there: the largest reply used 9,521 output
# tokens, the mean was 7,256, and 40,886 of the 43,536 output tokens across the six calls
# (93.9 pct) were provider-side reasoning rather than the JSON record. The calibration run is
# committed at results/eval-c000-order-dates-calibration.json.
#
# ⚠︎ THE FIRST VALUE WRITTEN HERE WAS 8000 AND IT WOULD HAVE TRUNCATED THE LARGEST CALIBRATION
# REPLY. That is what the calibration is for, and it is why it runs before anything is scored: a
# guess informed by a sibling extraction kit was 16 pct BELOW the largest reply this kit's own
# corpus produced, because counting a business-day period is day-by-day reasoning and a
# ten-field-per-obligation record is not the same shape as a ten-field record.
#
# 32000 is ~3.4x the largest reply actually observed, and the ceiling itself was probed with one
# live call rather than assumed to be accepted. The headroom is deliberate: a sibling kit published
# three successive runs whose "failures" were nothing but a cap set from a smaller corpus, with a
# DIFFERENT set of records truncated each time. A cap that cuts a reply costs a whole ORDER here --
# up to six obligations, not one field -- and a cap with headroom costs nothing at all, because a
# reply that finishes is billed for what it used and not for the ceiling. evals/run.py records
# `output_tokens_max` on every run so this margin can be re-checked without another calibration,
# and it tests `finish_reason` explicitly so a truncation is NAMED rather than scored as a miss.
MAX_TOKENS = 32000

# The subfields that are graded as EXTRACTION cells. `paragraph` is the join key rather than a
# cell, and `due_date` is the arithmetic answer and is graded on its own -- folding it in would
# average the thing this kit measures into the thing every extraction kit measures.
SCORED_SUBFIELDS = ("item", "basis", "period_days", "trigger_event", "trigger_event_date",
                    "stated_date", "party_calculated_date")

# Values that can be located verbatim in the order they came from. Every date is converted to ISO
# on the way out and the Order writes dates in words, so a date CANNOT be found verbatim -- it is
# excluded from the span denominator rather than counted as a miss, exactly as an enum is.
SPANNABLE_SUBFIELDS = ("item", "trigger_event")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def subfields(fields):
    for f in fields:
        if f.get("subfields"):
            return f["subfields"]
    return []


def load_doc(order_id):
    with open(os.path.join(CORPUS, "%s.txt" % order_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def recompute(row, order_date):
    """The rulebook date re-derived from one row's own extracted values. ISO string or None.

    One definition, three readers: tools/build_corpus.py writes gold with it, src/prompt.py states
    it to the model in words and renders the rulebook into every call, and evals/judge.py runs it
    over the model's OWN values for the no-gold consistency diagnostic.
    """
    return CR.due_date(row.get("basis"), row.get("period_days"), order_date,
                       row.get("trigger_event_date"), row.get("stated_date"))


def explain(row, order_date):
    """The full working for one row -- what it counted from, whether it rolled, and why."""
    return CR.compute(row.get("basis"), row.get("period_days"), order_date,
                      row.get("trigger_event_date"), row.get("stated_date"))


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    ⚑ THIS GUARDRAIL FLAGS A BUSINESS CONDITION, not a check on the model. It asks "can this
    obligation be calendared at all from the four corners of the Order", not "does this reply
    contradict itself".

    THE CONDITION: the period runs from a triggering event, and the Order's own Recorded Events
    table gives that event NO date. Nothing on the face of the Order dates the obligation, so it
    cannot go on a calendar -- it goes on a list for somebody to find out when the event happened.

    ⚠︎ AN UNDATED TRIGGER IS NOT THE ORDER DATE AND IT IS NOT ZERO DAYS. Substituting the Order
    date is the shortcut evals/baseline.py takes deliberately, and it is the failure that hurts
    most on a docketing queue: a blank gets chased and a confident wrong date gets diarised.

    ⚠︎ THIS IS THIS KIT'S OWN SIMPLIFICATION. It reads two of the row's own values and nothing
    else. A real docketing desk also knows what the file says, what the parties have agreed, what
    the clerk's own record shows, and which of those outranks the others; none of that is here.

    Returns True / False, or None when the reply is missing something the rule needs -- an unknown
    is not a pass.
    """
    basis = values.get("basis")
    if basis not in CR.BASES:
        return None
    if basis == "explicit_date":
        # A stated date the reply did not carry is still an obligation nobody can calendar. True
        # is the safe direction here: it routes the row to a person rather than off the list.
        return CR.parse(values.get("stated_date")) is None
    if not isinstance(values.get("period_days"), int):
        return None
    if basis in CR.FROM_EVENT:
        if not values.get("trigger_event"):
            return None
        return CR.parse(values.get("trigger_event_date")) is None
    return False


def _span_in(paras, para_no, value):
    """Where in ITS OWN PARAGRAPH this value was read from, or None.

    ⚠︎ SCOPED TO THE PARAGRAPH, AND ON THIS CORPUS THAT MATTERS MORE THAN ON MOST. One order
    carries up to six obligations drawn from the same item vocabulary in the same section, so a
    document-wide search would happily cite paragraph 2's text for a value paragraph 5 stated. A
    span that points at roughly the right place is worse than none -- it invites a reader to check,
    and the check appears to succeed.
    """
    p = paras.get(para_no)
    if p is None or value in (None, ""):
        return None
    hit = segment.locate(p["text"], value)
    if not hit:
        return None
    return {"start": p["start"] + hit[0], "end": p["start"] + hit[1], "label": "¶%d" % para_no}


def _row(raw_row, paras, order_date, subs):
    row = {k: raw_row.get(k) for k in [s["name"] for s in subs]}
    for k, v in list(row.items()):
        if v in ("", "null", "None"):
            row[k] = None
    try:
        row["paragraph"] = int(row["paragraph"])
    except (TypeError, ValueError):
        row["paragraph"] = None
    if row.get("period_days") is not None:
        try:
            row["period_days"] = int(row["period_days"])
        except (TypeError, ValueError):
            row["period_days"] = None

    row["spans"] = {k: _span_in(paras, row["paragraph"], row.get(k))
                    for k in SPANNABLE_SUBFIELDS}
    row["computed_date"] = recompute(row, order_date)
    working = explain(row, order_date)
    row["rolled"] = working["rolled"]
    row["rolled_from"] = working["rolled_from"]
    row["landed_on"] = working["landed_on"]
    row["working"] = working["reason"]
    row["undatable"] = compute(row)
    return row


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one scheduling order. `complete` is injectable so the eval
    harness, the app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    paras = segment.numbered(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    parsed_ok = bool(values)

    order_date = values.get("order_date")
    if order_date in ("", "null", "None"):
        order_date = None
    matter = values.get("matter_number")
    if matter in ("", "null", "None"):
        matter = None

    subs = subfields(fields)
    rows = [_row(r, paras, order_date, subs) for r in (values.get("deadlines") or [])]
    rows.sort(key=lambda r: (r["paragraph"] is None, r["paragraph"] or 0))

    m_span = None
    hit = segment.locate(doc_text, matter) if matter else None
    if hit:
        m_span = {"start": hit[0], "end": hit[1], "label": segment.span_label(secs, hit[0])}

    return {
        "matter_number": {"value": matter, "spannable": True, "span": m_span},
        "order_date": {"value": order_date, "spannable": False, "span": None},
        "deadlines": rows,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
