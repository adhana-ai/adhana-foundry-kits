"""Assemble the alert-adjudication prompt. One prompt per alert, all seventeen fields in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `verdict` AND `deciding_identifier`, AND THEY ARE A
FIVE-CHECK COMPARISON WITH A STOPPING ORDER. It is stated in full, and THE RULEBOOK ITSELF IS SENT
WITH IT, because "which identifier outranks which" is a policy and a model cannot apply a policy it
has never been shown. The alternative -- letting the model answer from whatever it thinks entity
resolution means -- is exactly the failure this kit exists to measure: the shipped rulebook is the
authority for this decision, and a reading that disagrees with it is wrong here even where the
reading is defensible.

Five things are spelled out that a model left to its own reading gets wrong:

  1. A STRONG IDENTIFIER OUTRANKS EVERYTHING BELOW IT, IN BOTH DIRECTIONS. Two records with the
     same passport number are the same party even if the names are spelled differently, the
     nationalities disagree and the places of birth conflict. Two records with DIFFERENT passport
     numbers are different parties even if the name and the full date of birth agree exactly.
  2. TWO IDENTIFIERS OF DIFFERENT TYPES ARE NOT COMPARABLE. A passport number on one side and a
     national identity number on the other tell you nothing about each other. That is not a weak
     match, it is no match at all, and the rule falls through as though neither existed.
  3. A PARTIAL DATE OF BIRTH IS NOT A MATCH AND NOT A MISMATCH. "1978" against "1978-04-12" is a
     stated fact that cannot be compared at the precision the rule needs. It contributes nothing.
  4. NAMES, NATIONALITIES AND THE ANALYST'S NOTE DECIDE NOTHING. The alert only exists because the
     names looked alike; a list record's nationality is routinely stale; and the note was written
     by somebody who triaged the alert before anybody compared identifiers.
  5. `insufficient_information` IS A REAL ANSWER. Reaching for it when the file does not decide is
     the correct behaviour, not a failure to produce a verdict.

⚑ ONE CALL PER ALERT, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.

⚠︎ AND THE VERDICT IS A PROPOSAL. The prompt says so, the UI says so and the kit's own pages say
so: this kit clears nothing, blocks nothing and files nothing. A human makes the call.
"""
import json

from .rulebook import R, MIN_MODERATE

SYSTEM = (
    "You read a SANCTIONS SCREENING ALERT REVIEW SHEET -- one customer record beside the "
    "watchlist entry a screening engine matched it to -- and extract structured fields from it. "
    "You return JSON and nothing else.\n"
    "\n"
    "You are PROPOSING an adjudication for a human to decide. You clear nothing, you block "
    "nothing and you file nothing: no alert is closed, no party is designated or de-designated, "
    "no account is frozen or released, no payment is stopped or let through, and no report is "
    "made to anybody.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the sheet does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world. Every name, list, programme, place and identifier on these "
    "sheets is invented for this exercise -- there is nothing to recognise.\n"
    "2. `verdict` and `deciding_identifier` are decided ONLY by the ADJUDICATION RULEBOOK given "
    "below, applied to eight values -- the two identifier types, the two identifier values, the "
    "two dates of birth and the two places of birth. Work through these five checks IN ORDER and "
    "STOP at the first one that fires:\n"
    "   a. STRONG IDENTIFIER, SAME VALUE. If BOTH records carry a strong identifier OF THE SAME "
    "TYPE and the two values are the same, answer 'same_party' and name that identifier. This "
    "outranks everything below it.\n"
    "   b. STRONG IDENTIFIER, DIFFERENT VALUE. If both carry a strong identifier of the same type "
    "and the values differ, answer 'not_a_match' and name that identifier. This also outranks "
    "everything below it.\n"
    "   c. MODERATE CONFLICT. Otherwise, take the moderate identifiers that are COMPARABLE on "
    "both records. If any of them DISAGREES, answer 'not_a_match' and name it. Read date of "
    "birth before place of birth.\n"
    "   d. MODERATE AGREEMENT. Otherwise, if at least %d comparable moderate identifiers AGREE "
    "and none disagrees, answer 'same_party'. Name 'date_of_birth_and_place_of_birth' when both "
    "agree.\n"
    "   e. OTHERWISE answer 'insufficient_information' and set deciding_identifier to 'none'.\n"
    "3. TWO STRONG IDENTIFIERS OF DIFFERENT TYPES ARE NOT COMPARABLE. A passport number on the "
    "customer record and a national identity number on the watchlist entry say NOTHING about each "
    "other. Do not treat that as weak evidence either way -- checks (a) and (b) simply do not "
    "fire, and the rule falls through to the moderate identifiers as though neither record "
    "carried one.\n"
    "4. A PARTIAL DATE OF BIRTH IS NOT COMPARABLE. A date is comparable only when BOTH records "
    "carry a FULL calendar date. A year-only date ('1978') or a year-and-month date ('1978-04') "
    "is a stated fact and is still not comparable -- it neither agrees nor disagrees with "
    "anything, and it contributes nothing in either direction. Copy it verbatim into the field "
    "and do not pad it out.\n"
    "5. NAMES, NATIONALITIES AND THE ANALYST'S NOTE ARE FIELDS TO COPY, NOT EVIDENCE. The alert "
    "exists because the names looked alike, so name similarity settles nothing. A watchlist "
    "record's nationality is routinely stale or secondary and disagrees for the same party all "
    "the time. The analyst's note is one person's impression written before anybody compared the "
    "identifiers, and on these sheets it often points the wrong way. None of the three is an "
    "input to the verdict.\n"
    "6. `insufficient_information` IS A REAL ANSWER AND YOU SHOULD REACH FOR IT WHEN THE FILE "
    "DOES NOT DECIDE. It means these two records do not carry enough to be separated or joined. "
    "It is not a clearance and it is not a match, and guessing one of the other two instead is "
    "the worst thing you can do on this sheet.\n"
    "7. Copy names, places, nationalities and identifier values verbatim from the sheet.\n"
    "8. Use the exact allowed value for a field that lists them. 'none' is a VALUE for the two "
    "identifier-type fields, not a blank.\n"
    "9. Return every field named in the schema, even when the answer is null."
) % MIN_MODERATE


def rulebook_block(r=None):
    """The rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the tiers and the stopping order inside this
    module is a copy that drifts from the file the corpus generator and the scorer both read --
    which would make the model's instructions and the gold labels disagree about the same policy,
    silently, and the disagreement would score as a model failure.
    """
    r = r or R
    t = r["identifier_tiers"]
    lines = ["ADJUDICATION RULEBOOK (the authority for `verdict` and `deciding_identifier`; this "
             "is an ILLUSTRATIVE rulebook shipped with this kit, not any real list, programme, "
             "supervisor's guidance or vendor tuning)", "",
             "IDENTIFIER STRENGTH TIERS"]
    lines.append("  %-10s %s" % ("strong:", ", ".join(t["strong"])))
    lines.append("  %-10s %s" % ("moderate:", ", ".join(t["moderate"])))
    lines.append("  %-10s %s" % ("weak:", ", ".join(t["weak"])))
    lines += ["", "WHAT EACH TIER DOES",
              "  strong    " + r["strong_note"],
              "  moderate  " + r["moderate_note"],
              "  weak      " + r["weak_note"],
              "",
              "WHEN A MODERATE IDENTIFIER IS EVEN COMPARABLE"]
    for field in t["moderate"]:
        lines.append("  %-16s %s" % (field + ":", r["comparable"][field]))
    lines += ["", "IDENTIFIERS OF DIFFERENT TYPES", "  " + r["different_types_note"],
              "", "DECISION ORDER -- stop at the first check that fires"]
    for step in r["decision_order"]:
        lines.append("  " + step)
    lines += ["", "MINIMUM MODERATE AGREEMENTS TO JOIN TWO RECORDS: %d"
              % int(r["min_moderate_agreements"]),
              "", "NAMING THE DECIDING IDENTIFIER", "  " + r["deciding_identifier_note"],
              "", "WHAT THIS RULEBOOK IS NOT", "  " + r["not_an_authority"]]
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
            "Use null for any field the sheet does not state.\n\n"
            "ALERT REVIEW SHEET\n------------------\n%s\n"
            % (RULEBOOK_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "adjudication rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "alert sections", "text": context},
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
