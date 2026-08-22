"""Assemble the extraction prompt. One prompt per usage-to-invoice reconciliation record, all
eleven fields in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `variance_cause`, AND IT IS ARITHMETIC PLUS A SIX-WAY
CLASSIFICATION WITH A PRIORITY ORDER. The whole rule is stated rather than left for the model to
infer, because the measurable failures this kit exists to catch are all failures of WHICH NUMBER TO
REACH FOR:

  1. THE BILLING INCREMENT IS A PROPERTY OF THE SERVICE. Voice rounds to 60 seconds, data to
     1024 KB, and SMS not at all. A one-message gap on an SMS line is a real variance; a
     fifty-second gap on a voice line is not. One tolerance applied to all three is wrong in both
     directions at once.
  2. UNRATED USAGE IS NOT SUBTRACTED. It failed rating, but it is still this period's usage and is
     still owed. A model that treats the suspense bucket as "not billable" lowers the target and
     then reports a variance that is not there -- and 8 records here carry a non-zero suspense
     bucket on a perfectly correct invoice.
  3. THE CONFIRMED DUPLICATE FIGURE IS NOT THE SUSPECT FIGURE. De-duplication flags candidates;
     review confirms some of them. 44 of the 55 records state a larger suspect figure than the
     confirmed one, and 22 of those confirmed NONE of it -- two genuinely distinct sessions that
     looked alike. Subtracting suspects invents a gap.
  4. PRIOR-PERIOD USAGE IS SUBTRACTED, AND ITS PRESENCE IS NOT ITSELF A VARIANCE. Records that
     arrived after cutoff belong to the previous invoice, so an invoice that correctly leaves them
     out is correct. 37 records here state a non-zero late-arrival figure and only 8 of them are
     the `late_records` case.
  5. ROUNDING IS CHECKED BEFORE ANY CAUSE IS NAMED. A gap smaller than one increment is
     indistinguishable from a small missed block, so naming a cause for it is a guess dressed as a
     finding.
  6. THE ANALYST NOTE IS A FIELD TO COPY, NOT EVIDENCE. On 22 of the 55 records it names a cause
     the arithmetic does not support.

⚑ ONE CALL PER RECORD, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.
"""
import json

SYSTEM = (
    "You extract structured fields from a telecom usage-to-invoice reconciliation record for one "
    "invoice line. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the record does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world. A field stated as 0 is stated -- return 0, not null.\n"
    "2. `variance_cause` is decided by ARITHMETIC over five structured quantities -- "
    "mediated_quantity, invoiced_quantity, unrated_quantity, prior_period_quantity and "
    "confirmed_duplicate_quantity -- never by how the analyst note reads and never from the "
    "Duplicate Suspects figure. Work it out yourself, in this order:\n"
    "   a. THE BILLING INCREMENT COMES FROM service_type. voice is billed in whole minutes, so "
    "the increment is 60 seconds. data is billed in whole megabytes, so the increment is 1024 KB. "
    "sms is billed per message, so the increment is 1 and there is NO rounding tolerance at all.\n"
    "   b. billable = mediated_quantity - prior_period_quantity - confirmed_duplicate_quantity. "
    "DO NOT SUBTRACT unrated_quantity: usage that failed rating is still this period's usage and "
    "is still owed.\n"
    "   c. expected = billable rounded UP to the next whole multiple of the increment.\n"
    "   d. gap = invoiced_quantity - expected.\n"
    "   e. Classify the gap and STOP AT THE FIRST MATCH:\n"
    "      - gap is exactly 0 -> 'none'\n"
    "      - the absolute value of gap is LESS THAN the increment -> 'rounding'\n"
    "      - gap is negative, unrated_quantity is above 0, and the size of gap is within one "
    "increment of unrated_quantity -> 'unrated_usage'\n"
    "      - gap is positive, confirmed_duplicate_quantity is above 0, and gap is within one "
    "increment of confirmed_duplicate_quantity -> 'duplicate_records'\n"
    "      - gap is positive, prior_period_quantity is above 0, and gap is within one increment of "
    "prior_period_quantity -> 'late_records'\n"
    "      - otherwise -> 'unexplained'\n"
    "3. THE ROUNDING CHECK COMES BEFORE ANY CAUSE IS NAMED. A gap smaller than one increment is "
    "explained by rounding and nothing else -- do not name a cause for it, even when one of the "
    "three blocks happens to be about that size.\n"
    "4. CONFIRMED DUPLICATES ARE NOT DUPLICATE SUSPECTS. The record states both. De-duplication "
    "FLAGS suspects; review CONFIRMS a subset of them, and a suspect that review cleared is two "
    "genuinely distinct sessions. Only the Confirmed Duplicates figure enters the arithmetic, and "
    "confirmed_duplicate_quantity is read from that section. The suspect figure is usually the "
    "larger of the two and is often zero once confirmed.\n"
    "5. THE PRESENCE OF PRIOR-PERIOD USAGE IS NOT ITSELF A VARIANCE. Records that arrived after "
    "the collection cutoff belong to the PREVIOUS invoice. Subtract them, and if the invoice "
    "already left them out the answer is 'none'.\n"
    "6. THE ANALYST NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT THE CAUSE. A note naming duplicate "
    "records, unrated usage, late records or rounding does NOT make that the cause, and a note "
    "saying the line reconciled cleanly does NOT mean it did. The five quantities decide; the note "
    "is the analyst's own remark and may disagree with them.\n"
    "7. Copy values verbatim from the record wherever possible, and report every quantity as a "
    "bare number with the unit left out of it.\n"
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
            "USAGE-TO-INVOICE RECONCILIATION RECORD\n--------------------------------------\n%s\n"
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
