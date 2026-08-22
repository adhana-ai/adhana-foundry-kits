"""A free, rules-and-regex worksheet builder. No model, no key, no spend -- scored by the same
judge as a paid run, so the two are directly comparable.

⚑ THE SHORTCUT HERE IS THE MONEY COLUMN, AND IT IS THE EXACT SHORTCUT THIS KIT EXISTS TO MEASURE.
The floor reads every stated fact off the pack correctly -- the line code, the description, the
type, the fee column, the dependency sentence and the timing sentence, all by regex, all right --
and then decides `separation` from the fee alone: a line with a price of its own is `distinct`, a
line without one is `bundled`. It decides `pattern` the same way: a stated period is `over_time`
and everything else, INCLUDING SILENCE, is `point_in_time`.

⚑ SO IT NEVER SAYS `not_determined`, EVER, ABOUT ANYTHING. That is the point of it. A worksheet
that cannot say "the paperwork does not settle this" is not a confident worksheet, it is a guessing
one, and this floor is what guessing scores. Every call this corpus's contracts leave open is a
call the floor answers with a confident value.

⚑ AND IT LISTS THE STRUCK LINE. The floor reads the Order Form rows and never reads the amendment
note beside them, so every pack carrying a line withdrawn before signature gets that line on its
worksheet. That is an identification failure with a nameable cause rather than a mystery, and it is
published as one.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. It
already extracts `charge`, `dependency` and `timing` correctly on every line; calling
src.rulebook.decide() on them would score 100 pct and tell you nothing about the model. So the
floor is deliberately the SHORTCUT, not the lookup, and the gap it opens is the gap between reading
a price and applying a rule.

⚠︎ THE KEYWORD LISTS WERE CHECKED AGAINST THE CORPUS'S OWN SENTENCE TEMPLATES BEFORE THIS FLOOR WAS
FIRST RUN, NOT AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a
keyword that fired on a negation inside the opposite register and mis-classified four records for
days; evals/check_labels.py asserts the property here before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a money-derived separation call
produces a money-derived review flag: the floor reads the fee column perfectly every time and the
separation wrong on every open line, and the flag inherits the error. A business-condition
guardrail is only ever as good as the field it reads.
"""
import re

from src.extract import compute as _compute

# Every sentence in the corpus that STATES a prerequisite matches exactly one of these, and no
# sentence that states separability matches any of them. Asserted in evals/check_labels.py.
PREREQ_STEMS = ("not made available to the customer",
                "may be used until this work is accepted",
                "not enabled until the training days",
                "cannot be brought into use until",
                "cannot be taken on its own",
                "cannot be supplied except together with")
SEPARABLE_STEMS = ("may cancel this line",
                   "may obtain this line",
                   "may be deferred or taken on its own")
PERIOD_STEMS = ("supplied over the", "provided continuously across", "delivered across the")
EVENT_STEMS = ("complete on signature", "complete on the date",
               "complete when the final scheduled day")

_ROW = re.compile(r"^ {2}(PO-\d{4})\s{2,}(\S.*?)\s{2,}(\S.*)$", re.M)


def _section(text, name):
    m = re.search(r"^%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S | re.M)
    return m.group(1).strip() if m else None


def _order_rows(text):
    """Every order-form row, scanned over the WHOLE pack.

    ⚠︎ NOT OVER A CUT-OUT "Order Form" SECTION, and the difference is not stylistic. `_section`
    stops at the first blank line, and an order form's blank line sits between its header sentence
    and its rows -- so a section-scoped scan captures the header and none of the rows and reports a
    pack with no lines at all. The two-space-indented row is unique to the order form in this
    layout; every other line in a pack starts at column zero.
    """
    return [(m.group(1), m.group(2).strip(), m.group(3).strip()) for m in _ROW.finditer(text)]


def _charge_of(fee_text):
    low = fee_text.lower()
    if low.startswith("included at no separate charge"):
        return "no_separate_charge"
    if low.startswith("fee not separately stated"):
        return "not_stated"
    if low.startswith("withdrawn"):
        # ⚑ THE FLOOR DOES NOT KNOW WHAT THIS MEANS AND DOES NOT ASK. It reads the cell as "no
        # money here", which is exactly how the struck line ends up on its worksheet.
        return "no_separate_charge"
    return "separate_fee"


def _first(text, stems):
    low = text.lower()
    return any(s in low for s in stems)


def extract_one(text, fields):
    ifields = fields["fields"]
    contract_id = _section(text, "Contract")

    rows = []
    for code, label, fee in _order_rows(text):
        sec = _section(text, "Item %s" % code) or ""
        m = re.search(r"^Type: (\S+)", sec, re.M)
        item_type = m.group(1) if m else None
        d = re.search(r"^Description: (.+)$", sec, re.M)
        desc = d.group(1).strip() if d else label

        charge = _charge_of(fee)
        if _first(sec, PREREQ_STEMS):
            dependency = "required_first"
        elif _first(sec, SEPARABLE_STEMS):
            dependency = "separately_available"
        else:
            dependency = "silent"
        if _first(sec, PERIOD_STEMS):
            timing = "period"
        elif _first(sec, EVENT_STEMS):
            timing = "event"
        else:
            timing = "silent"

        # THE SHORTCUT, both halves. Money decides separability; anything that is not an explicit
        # period is treated as a one-off. Neither branch can produce `not_determined`.
        separation = "distinct" if charge == "separate_fee" else "bundled"
        pattern = "over_time" if timing == "period" else "point_in_time"

        vals = {"item_code": code, "item_label": desc, "item_type": item_type,
                "charge": charge, "dependency": dependency, "timing": timing,
                "separation": separation, "pattern": pattern}
        rows.append({f["name"]: {"value": vals.get(f["name"]), "spannable": False, "span": None}
                     for f in ifields})

    flat = [{n: c["value"] for n, c in r.items()} for r in rows]
    return {
        "contract": {"contract_id": {"value": contract_id, "spannable": True, "span": None}},
        "obligations": rows,
        "needs_drafting_review": _compute(flat),
        "sections_used": [], "prompt_parts": [],
        "input_tokens": 0, "output_tokens": 0, "parsed": True,
    }


def extract(text, fields):
    return extract_one(text, fields)
