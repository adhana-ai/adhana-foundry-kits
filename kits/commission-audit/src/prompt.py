"""Assemble the extraction prompt. One prompt per commission claim record, all fourteen fields
in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `claim_valid`, AND IT IS A FIVE-BRANCH COMPUTATION WITH A
PRIORITY ORDER. It is stated in full rather than left for the model to infer, because the
measurable failure this kit exists to catch is a model that does the multiplication first and the
eligibility checks second -- or that answers from the property reviewer's note, reading "Folio
matches the claim, no action needed." as proof a line is owed when the folio's own numbers say it
is not.

Five things are spelled out that a model left to its own reading gets wrong:

  1. THE BOOKING SOURCE OUTRANKS EVERYTHING. A stay the folio shows arrived direct, through a
     corporate GDS or as a walk-in owes this channel nothing, however real the stay is and however
     tidy the arithmetic looks.
  2. A STAY ALREADY COMMISSIONED IS OWED NOTHING FURTHER. Every other value on the line can be
     correct and the answer is still zero.
  3. TAXES, FEES AND INCIDENTALS ARE NEVER IN THE BASE. They sit on the same folio, right beside
     room revenue, and the single most common bad claim is the one computed on the total.
  4. A CANCELLATION OR NO-SHOW IS NOT AUTOMATICALLY ZERO. When a penalty was actually charged,
     commission IS owed -- on the penalty, never on the room revenue nobody earned.
  5. A REBOOKED RESERVATION IS A STAY. The guest moved confirmation numbers and stayed; it is
     commissionable exactly as a plain stay is.

And one thing that is stated because it is the whole decoy:

  6. THE REVIEWER NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds like a dispute does
     not mean the claim is wrong, and a note that sounds settled does not mean it is right.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a channel commission claim record. Each record is one "
    "line of a booking channel's commission invoice, joined to the property's own folio record "
    "for the booking it claims against. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `claim_valid` is decided by COMPUTING WHAT IS ACTUALLY OWED from the structured folio "
    "values and comparing it against claimed_commission_usd -- never by how the reviewer note "
    "reads. Compute it yourself, IN THIS ORDER:\n"
    "   a. If booking_source is anything other than 'channel', NOTHING is owed. The booking did "
    "not come through this channel, so no commission is earned on it whatever the stay looks "
    "like. Stop here.\n"
    "   b. Otherwise, if already_commissioned is 'yes', NOTHING is owed. It was commissioned on a "
    "previous invoice and is not owed twice. Stop here.\n"
    "   c. Otherwise work out the commissionable base. If folio_status is 'stayed' or 'rebooked', "
    "the base is room_revenue_usd MINUS room_revenue_refunded_usd. If folio_status is 'cancelled' "
    "or 'no_show', the base is penalty_charged_usd. non_room_charges_usd is NEVER part of the "
    "base, in any branch.\n"
    "   d. If that base is zero or less, nothing is owed.\n"
    "   e. Otherwise the commission owed is base x contract_rate_pct / 100, rounded to the cent.\n"
    "   Answer 'yes' when claimed_commission_usd equals the amount you computed, to the cent. "
    "Answer 'no' in every other case.\n"
    "3. CHECK THE BOOKING SOURCE AND THE PRIOR-COMMISSION FLAG BEFORE YOU DO ANY ARITHMETIC. A "
    "claim on a direct, corporate_gds or walk_in booking is owed nothing even when the "
    "multiplication is perfect, and so is a stay already commissioned last cycle.\n"
    "4. A CANCELLED OR NO-SHOW BOOKING IS NOT AUTOMATICALLY WORTH NOTHING. When a penalty was "
    "charged, commission is owed ON THE PENALTY. It is owed on nothing when the penalty charged "
    "was zero.\n"
    "5. 'rebooked' MEANS THE GUEST STAYED. The reservation moved to a new confirmation number and "
    "the stay happened, so it is commissionable on its room revenue exactly as a plain stay is.\n"
    "6. THE REVIEWER NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT VALIDITY. A note that reads like "
    "a dispute does NOT mean the claim is wrong, and a note that reads as settled does NOT mean "
    "it is right. The structured folio values decide; the note is the property reviewer's own "
    "remark and may disagree with them.\n"
    "7. Copy values verbatim from the record wherever possible, and report every money and "
    "percentage field as a bare number with the currency or percent sign left out of it. "
    "room_revenue_refunded_usd is null on a cancelled or no-show booking, and "
    "penalty_charged_usd is null on a booking the guest stayed on (including a rebooked one) -- "
    "return null for those rather than 0 or a guess.\n"
    "8. Use the exact allowed value for a field that lists them.\n"
    "9. Return every field named in the schema, even when the answer is null."
)


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the record does not state.\n\n"
            "COMMISSION CLAIM RECORD\n-----------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "record sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
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
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
