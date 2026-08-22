"""Assemble the reconciliation prompt. One prompt per component record pack, all thirteen fields
in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `life_status`, AND IT IS AN ACCUMULATION FOLLOWED BY A
FIVE-VALUE COMPARISON WITH A PRIORITY ORDER. Both halves are stated in full rather than left for
the model to infer, because the measurable failures this kit exists to catch are arithmetic ones a
model falls into on its own:

  1. SUMMING THE TRAIL AT ALL. The total hours and cycles since new are not printed anywhere on the
     pack. They are the sum of every installation period's own accrual. The figures that ARE
     printed -- on the component's tag -- are a claim, and on this corpus they disagree with the
     records on 14 of 50 packs.
  2. HOURS AND CYCLES ARE SUMMED SEPARATELY. Each period ran on a different airframe at a different
     hours-per-cycle ratio, so scaling one total off the other is wrong by construction.
  3. AN OVERHAUL RESETS TIME SINCE OVERHAUL AND NOT TIME SINCE NEW. The trail line says exactly
     that, in words. Restarting the accumulation at the overhaul undercounts the component,
     usually enormously, and it is the single most expensive misreading available here.
  4. A DECLARED GAP CONTRIBUTES NOTHING AND MUST NOT BE ESTIMATED. The conservative move is to
     state the gap, not to invent a number for it.
  5. THE EXCEEDANCE CHECK OUTRANKS THE GAP CHECK. A missing period can only ADD accumulated life,
     so it can never bring a component the surviving records already put at or past a limit back
     inside it. Seeing "records not available" and answering `cannot_determine` without first
     checking the surviving total against the limits is the wrong order, and 5 of the 12 gapped
     packs here are built to catch it.
  6. THE LIMIT IS INCLUSIVE. Exactly at the published limit there is no life remaining.
  7. THE REVIEWER'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. On 20 of 50 packs it is written in the
     register that contradicts the record.

⚑ ONE CALL PER PACK, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.

⚠︎ AND WHAT THE PROMPT DELIBERATELY DOES NOT ASK FOR. It never asks whether the component may be
returned to service, and it never asks the model to resolve a disagreement between the tag and the
trail. Both are stated as things to REPORT. This kit reconstructs, reconciles and escalates; the
airworthiness determination is not in it and is not asked for.
"""
import json

SYSTEM = (
    "You reconcile the accumulated life of one life-limited component from its maintenance record "
    "pack. You return JSON and nothing else.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the pack does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `trail_hours` and `trail_cycles` are TOTALS YOU COMPUTE, not values you copy. Add up the "
    "`accrued N hours / M cycles` figure of EVERY installation period in the Service Record "
    "Trail. Sum the hours and the cycles SEPARATELY -- each period ran on a different airframe at "
    "a different hours-per-cycle ratio, so one total can never be derived from the other.\n"
    "3. AN OVERHAUL DOES NOT RESET TIME SINCE NEW. A trail line reading 'overhaul completed - "
    "time since overhaul reset to 0 hours / 0 cycles' resets the time-since-overhaul counter "
    "ONLY. The life limit is against time since NEW, which is unaffected. Keep adding every "
    "period before the overhaul as well as every period after it. Do NOT restart the "
    "accumulation there.\n"
    "4. A PERIOD MARKED 'accrual NOT RECORDED' CONTRIBUTES NOTHING TO THE TOTALS. Do not estimate "
    "it, do not interpolate it from the periods either side of it, and do not fall back on the "
    "tag figures to fill it. Report `record_gap` as 'yes' and let the totals be the total of what "
    "the surviving records actually substantiate.\n"
    "5. THE COMPONENT'S OWN TAG IS A CLAIM, NOT A MEASUREMENT. Copy `tag_hours` and `tag_cycles` "
    "verbatim and never correct them, never use them as `trail_hours`/`trail_cycles`, and never "
    "let them decide `life_status`. `tag_agrees` is 'yes' only when tag_hours EXACTLY equals your "
    "trail_hours AND tag_cycles EXACTLY equals your trail_cycles.\n"
    "6. `life_status` is decided by COMPARING YOUR RECONSTRUCTED TOTALS against the two published "
    "limits, in this order:\n"
    "   a. If trail_hours >= life_limit_hours AND trail_cycles >= life_limit_cycles, answer "
    "'both_exceeded'.\n"
    "   b. Otherwise, if trail_hours >= life_limit_hours, answer 'hours_exceeded'.\n"
    "   c. Otherwise, if trail_cycles >= life_limit_cycles, answer 'cycles_exceeded'.\n"
    "   d. Otherwise, if record_gap is 'yes', answer 'cannot_determine'.\n"
    "   e. Otherwise, answer 'within_limits'.\n"
    "7. THE EXCEEDANCE CHECKS COME BEFORE THE GAP CHECK. A missing period of records can only ADD "
    "accumulated life -- it can never bring a component that the surviving records already put at "
    "or past a limit back inside it. So a declared gap makes 'within limits' undeterminable and "
    "leaves 'exceeded' perfectly determinable. Do not answer 'cannot_determine' without first "
    "checking the surviving totals against both limits.\n"
    "8. THE LIMIT IS INCLUSIVE. A total EXACTLY equal to the published limit is exceeded, not "
    "within limits -- there is no life remaining at the limit.\n"
    "9. THE REVIEWER'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds calm does NOT "
    "mean the component is inside its limits, and a note that sounds worried does NOT mean it is "
    "not. The figures decide; the note is one person's remark and may disagree with them.\n"
    "10. Report every hours and cycles figure as a bare whole number with the unit left out of "
    "it. Use the exact allowed value for a field that lists them, and return every field named in "
    "the schema even when the answer is null.\n"
    "\n"
    "YOU ARE NOT DECIDING WHETHER THIS COMPONENT MAY FLY. `life_status` is a statement about what "
    "the RECORDS substantiate. It is not an airworthiness determination and it releases nothing "
    "to service."
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
            "Use null for any field the pack does not state.\n\n"
            "COMPONENT RECORD PACK\n---------------------\n%s\n"
            % (schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "field schema", "text": schema},
        {"name": "pack sections", "text": context},
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
