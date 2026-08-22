"""Assemble the pre-check prompt. One prompt per case pack, all fourteen fields in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `defects_found`, AND IT IS A CLOSED VOCABULARY WITH A STOPPING
ORDER. It is stated in full, and THE RULEBOOK ITSELF IS SENT WITH IT, because the threshold, the
window, the code table and the element list are all this kit's own inventions and a model cannot
apply a rulebook it has never been shown. The alternative -- letting the model answer from whatever
it knows about currency-transaction reporting in the world -- is exactly the failure this kit exists
to measure: the SHIPPED rulebook is the authority for this check, and a reading that disagrees with
it is wrong here even where the real-world practice is arguable.

Five things are spelled out that a model left to its own reading gets wrong:

  1. A NON-REPORTABLE ENTRY IS NOT A MISSED AGGREGATION. Wires and promotional credits are in the
     log, are not currency, and are correctly absent from the total. Seeing them left out and
     calling it a defect is the single commonest false alarm on this corpus.
  2. THE GAMING DAY IS NOT THE CALENDAR DAY. It runs 06:00 to 06:00, so an entry at 02:40 the
     morning after belongs to the day being filed, and one at 03:15 on the day's own date does not.
  3. ONE NAMED CAUSE PER DIFFERENCE. Three defects show up the same way -- the drafted total is
     lower than it should be -- and the stopping order picks which one to report. A checker that
     reports all three has tripled its own false-alarm rate on one finding.
  4. A CLEAN FILING IS 'none'. A QC pass that manufactures a finding to look thorough costs a
     person the time to clear a row that never needed clearing, and that is what makes a queue get
     ignored.
  5. THE PREPARER'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A confident note does not make a
     defective filing clean, and an anxious one does not make a clean filing defective.

⚑ ONE CALL PER CASE PACK, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.

⚠︎ AND IT PRE-CHECKS ONLY. The prompt says so, the UI says so and the kit's own pages say so:
nothing here files, lodges, transmits, approves or clears anything.
"""
import json

from . import rulebook as RB

SYSTEM = (
    "You read a CURRENCY-TRANSACTION FILING QC PACK -- a draft filing beside the cage transaction "
    "log it was prepared from -- and extract structured fields from it. You return JSON and "
    "nothing else.\n"
    "\n"
    "You are PRE-CHECKING a draft for a qualified person to act on. You never file anything, you "
    "never clear anything, and your answer is not a substitute for a compliance officer's "
    "judgement or for the filing instructions that actually apply.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the pack does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `defects_found` is decided ONLY by the RULEBOOK given below, applied to the numbers on the "
    "page. Work through the STOPPING ORDER and STOP at the first check that fires:\n"
    "   a. INSUFFICIENT INFORMATION. If any qualifying log entry's amount was never captured, or "
    "the draft does not state a gaming day, the qualifying total cannot be computed. Answer "
    "'insufficient_information' and stop. This is a real answer, not a failure to produce one.\n"
    "   b. THRESHOLD NOT CROSSED. If the qualifying total does not exceed the threshold, no filing "
    "is due at all. Answer 'threshold_not_crossed' and stop.\n"
    "   c. WINDOW MISAPPLIED. If the draft's Window Applied line names anything other than the "
    "gaming day, that is the named cause of any total difference. Report 'window_misapplied' and "
    "do NOT also report 'missed_aggregation' for the same difference.\n"
    "   d. IDENTITY SPLIT. Otherwise, if another patron record in the log matches this patron on "
    "BOTH link keys and the draft did not aggregate it, report 'identity_split'.\n"
    "   e. MISSED AGGREGATION. Otherwise, if the qualifying total exceeds the drafted total, "
    "qualifying entries on the patron's own record were left out. Report 'missed_aggregation'.\n"
    "3. THEN, INDEPENDENTLY OF 2c-2e, add 'identification_gap' when a required identification "
    "element is missing from the draft or the identification is stale, and 'type_miscode' when a "
    "transaction's code on the DRAFT is not the code the LOG records for the same identifier. "
    "These change what the filing SAYS rather than what it FILES, so they are checked separately "
    "and they never suppress a defect from 2c-2e.\n"
    "4. A NON-REPORTABLE ENTRY IS NOT A DEFECT. The log carries entries the rulebook marks "
    "non-reportable, entries in the opposite direction, and entries outside the gaming day. All "
    "three are CORRECTLY absent from the drafted total. Reporting them as a missed aggregation is "
    "a false alarm, and on this check a false alarm costs a person the time to clear a row that "
    "never needed clearing.\n"
    "5. A FILING WITH NOTHING WRONG WITH IT IS 'none'. Answer 'none' and do not manufacture a "
    "finding to look thorough.\n"
    "6. THE PREPARER'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT THE FILING. A note that sounds "
    "confident does NOT make a defective filing clean, and a note that sounds anxious does NOT "
    "make a clean filing defective. The rulebook and the numbers decide; the note is one person's "
    "remark about their own work and may disagree with them.\n"
    "7. Amounts are plain integers in CU. Return them with no unit, no separators and no decimals.\n"
    "8. Use the exact allowed value for a field that lists them.\n"
    "9. Return every field named in the schema, even when the answer is null."
)


def rulebook_block(r=None):
    """The rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of these tables inside this module is a copy
    that drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold labels disagree about the same threshold, silently, and the
    disagreement would score as a model failure.
    """
    r = r or RB.R
    unit = r["unit"]
    lines = ["FILING RULEBOOK (the authority for `defects_found`; this rulebook is INVENTED and was "
             "written for this kit -- it reproduces no real regulation, form or filing "
             "instruction, and CU is an invented unit that is not a currency)", "",
             "THRESHOLD",
             "  A filing is due when the qualifying total for ONE patron, in ONE direction, over "
             "ONE gaming day exceeds %d %s. Exactly %d %s does not cross it."
             % (r["threshold"], unit, r["threshold"], unit), "",
             "AGGREGATION WINDOW",
             "  The GAMING DAY runs from %s on its own date to %s the following calendar date."
             % (r["gaming_day_start"], r["gaming_day_start"]),
             "  An entry timestamped 02:40 on the date AFTER the gaming day still belongs to that "
             "gaming day.",
             "  An entry timestamped 03:15 on the gaming day's OWN date belongs to the PREVIOUS "
             "gaming day.",
             "  Cash in and cash out are aggregated SEPARATELY and are never netted against each "
             "other.", "",
             "TRANSACTION CODES -- direction, and whether the code is part of a CURRENCY total"]
    for code in sorted(r["transaction_codes"]):
        c = r["transaction_codes"][code]
        lines.append("  %-26s %-4s %-15s %s"
                     % (code, c["direction"],
                        "REPORTABLE" if c["reportable"] else "not reportable", c["what"]))
    lines += ["",
              "  A non-reportable code is NEVER part of a currency total, however large the "
              "amount. It is correctly absent from a draft and its absence is not a defect.", "",
              "REQUIRED IDENTIFICATION ELEMENTS -- all %d must be on the draft"
              % len(r["identification_elements"])]
    for el in r["identification_elements"]:
        lines.append("  %s" % el)
    lines += ["  Identification captured more than %d days before the gaming day is STALE."
              % r["identification_stale_days"], "",
              "SAME-PERSON LINK KEYS -- two patron records are one person when BOTH match",
              "  " + " and ".join(k.replace("_", " ") for k in r["identity_link_keys"]),
              "  A record matching on only one key is NOT a link.", "",
              "DEFECT CODES -- the only seven values `defects_found` may carry"]
    for code in r["defect_codes"]:
        lines.append("  %-26s %s" % (code, r["defect_codes"][code]))
    lines += ["", "STOPPING ORDER -- one named cause per total difference"]
    for step in r["stopping_order"]:
        lines.append("  %s" % step)
    return "\n".join(lines)


RULEBOOK_TEXT = rulebook_block()


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
    user = ("%s\n\n"
            "Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the pack does not state.\n\n"
            "QC PACK\n-------\n%s\n"
            % (RULEBOOK_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "filing rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "qc pack sections", "text": context},
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
    out = {}
    for f in fields:
        v = obj.get(f["name"])
        # ⚑ A LIST WHERE A COMMA STRING WAS ASKED FOR IS AN ANSWER, NOT A FAILURE. Three fields
        # here are lists by nature (defect codes, missing elements, transaction ids) and a model
        # that returns a JSON array for them has answered correctly in a different shape. Folding
        # it to the asked-for shape here, once, beats discovering it as fourteen wrong cells.
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v) if v else None
        out[f["name"]] = v
    return out
