"""Assemble the worksheet prompt. ONE prompt per contract pack, every ordered line in the reply.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `separation` AND `pattern`, AND THEY ARE RULEBOOK LOOKUPS.
Both are stated in full, and THE RULEBOOK ITSELF IS SENT WITH THEM, because a lookup a model has
never been shown is not a lookup. The alternative -- letting the model answer from whatever it
knows about how software contracts are usually accounted for -- is exactly the failure this kit
exists to measure: the shipped rulebook is the authority here, and a reading that disagrees with it
is wrong on this corpus even where a real reviewer might argue the other way.

⚠︎ AND WHAT COMES BACK IS A WORKSHEET, NOT A CONCLUSION. The prompt says so, the UI says so and the
kit's own pages say so: nothing here determines a performance obligation, allocates a price,
concludes on timing, opens a schedule or writes an entry. A controller does all of that.

Four things are spelled out that a model left to its own reading gets wrong:

  1. A PRICE IS NOT A STATEMENT ABOUT SEPARABILITY. A line with a fee of its own and NOTHING said
     about whether the customer could take it alone is `not_determined`. This is the biggest bucket
     in the corpus and the single most attractive wrong answer on the page.
  2. A LINE PRICED AT NOTHING CAN STILL BE `distinct`. If the contract says the customer may cancel
     or source it separately, that settles it -- the fee column does not get a vote.
  3. A LINE STRUCK BY AN AMENDMENT IS NOT AN OBLIGATION, and its whole clause is still printed in
     the pack. Only the order-form row and the notes say it was removed.
  4. A RATE CARD AND A CARRIED-OVER ITEM ARE NOT OBLIGATIONS EITHER. Both carry a code in the same
     format as a real line. A price with no order behind it, and somebody else's order form.

⚑ ONE CALL PER CONTRACT, NOT ONE PER LINE -- same reasoning as every sibling extraction kit. The
reply is a LIST, which is the one structural difference from those kits, and it is why
identification is scored separately from the calls made about what was identified.
"""
import json

from .rulebook import rulebook_block

SYSTEM = (
    "You read a SUBSCRIPTION CONTRACT PACK -- an order form plus the clauses behind its lines -- "
    "and return a REVIEWER'S WORKSHEET of the promises in it. You return JSON and nothing else.\n"
    "\n"
    "You are preparing a worksheet for a qualified reviewer. You never determine a performance "
    "obligation, never allocate a price, never conclude on timing, never open a revenue schedule "
    "and never write a journal entry. Your job is to say what the paperwork states, apply the "
    "rulebook given below, and NAME THE LINES THE PAPERWORK DOES NOT SETTLE.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. ONE OBJECT PER ORDERED LINE OF THIS ORDER FORM, AND NO OTHERS. A line struck by an "
    "amendment is not ordered, even though its clause is still printed in the pack. A rate card, "
    "day rate or price list for work nobody has ordered is not a line. An item supplied under an "
    "EARLIER order form and continuing is not a line. All three carry codes in the same format as "
    "a real line, and putting one on the worksheet puts a promise in front of a reviewer that "
    "does not exist.\n"
    "2. REPORT WHAT THE PACK STATES. `charge`, `dependency` and `timing` are readings of the "
    "paperwork, not judgements about it. If a line's Item section says nothing about how it "
    "relates to the other lines, `dependency` is 'silent' -- that is a finding about the "
    "contract, and it is the most common one. Never infer a dependency from the line type, from "
    "the fee, or from what you know about how software is usually sold.\n"
    "3. `separation` IS DECIDED ONLY BY THE RULEBOOK BELOW, from `charge` and `dependency`. Work "
    "through the four steps IN ORDER and STOP at the first that fires:\n"
    "   a. dependency 'required_first' -> 'bundled'.\n"
    "   b. dependency 'separately_available' -> 'distinct'. This holds WHATEVER the fee column "
    "says, including a line the order form prices at nothing.\n"
    "   c. dependency 'silent' AND charge 'no_separate_charge' -> 'bundled'.\n"
    "   d. anything else -> 'not_determined'.\n"
    "4. A FEE OF ITS OWN IS A PRICE, NOT A STATEMENT ABOUT SEPARABILITY. A priced line whose "
    "clause says nothing about whether the customer could take it alone is 'not_determined'. It "
    "is not 'distinct'. This is the step a confident reader skips, and on this rulebook it is "
    "the wrong answer rather than a defensible one.\n"
    "5. `pattern` IS DECIDED ONLY FROM `timing`: 'period' -> 'over_time', 'event' -> "
    "'point_in_time', 'silent' -> 'not_determined'. It is asked of every line independently of "
    "its separation call.\n"
    "6. 'not_determined' IS A REAL ANSWER AND YOU ARE EXPECTED TO USE IT. A worksheet that never "
    "reaches for it is guessing, and a call recorded as settled is a call nobody re-reads.\n"
    "7. Copy `item_code`, `item_label` and `item_type` verbatim from the pack. Use the exact "
    "allowed value for every field that lists them, and return every field for every line."
)

RULEBOOK_TEXT = rulebook_block()


def field_schema(contract_fields, item_fields):
    out = []
    for f in contract_fields:
        line = "- %s (%s) -- %s" % (f["name"], f["type"], f.get("hint", ""))
        out.append(line)
    out.append("- obligations (array of objects) -- one object per ORDERED line, each carrying:")
    for f in item_fields:
        line = "    - %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    contract_fields = fields["contract_fields"]
    item_fields = fields["fields"]
    wanted = selector.sent(secs)
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(contract_fields, item_fields)
    keys = ", ".join([f["name"] for f in contract_fields] + ["obligations"])
    user = ("%s\n\n"
            "Return these:\n%s\n\n"
            "Return a JSON object with exactly these top-level keys: %s\n"
            "`obligations` is an array. Return it empty only if the order form has no ordered "
            "line at all.\n\n"
            "CONTRACT PACK\n-------------\n%s\n"
            % (RULEBOOK_TEXT, schema, keys, context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "worksheet rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "contract pack sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    """The reply into {contract_id, obligations:[{...}]}. Fails CLOSED to {} rather than to a
    plausible-looking empty worksheet -- on this kit an empty `obligations` list is a real answer
    ('this order form orders nothing'), so it must never be what a parse failure looks like."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict) or "obligations" not in obj:
        return {}
    items = obj.get("obligations")
    if not isinstance(items, list):
        return {}
    out = {f["name"]: obj.get(f["name"]) for f in fields["contract_fields"]}
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rows.append({f["name"]: it.get(f["name"]) for f in fields["fields"]})
    out["obligations"] = rows
    return out
