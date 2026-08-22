"""Assemble the option-clock prompt. One prompt per register snapshot, all seventeen fields in it.

⚠︎ THE GUARDED FIELDS OF THIS KIT ARE `expiry_date` AND `status`, AND THEY ARE A COUNT WITH AN
ORDER. The count is stated in full, and THE RULEBOOK ITSELF IS SENT WITH IT, because "what starts
the clock" and "what perfects an extension" are facts about a rulebook and a model cannot apply a
rulebook it has never been shown. The alternative -- letting the model answer from whatever it knows
about how options usually work -- is exactly the failure this kit exists to measure: the shipped
rulebook is the authority for this count, and a reading that disagrees with it is wrong here even
where the practice is arguable.

⚑ AND THE PUBLISHED ANSWER IS THE ONE THE CODE COUNTS, NOT THE ONE THE MODEL STATES. The model is
asked for `expiry_date` and `status` anyway, and the gap between its answer and the code's is this
kit's no-gold consistency diagnostic -- the one number a forker can compute on registers nobody has
labelled. See evals/judge.py.

Five things are spelled out that a model left to its own reading gets wrong:

  1. THE REGISTER'S OWN STATUS LINE IS NOT EVIDENCE. It is what somebody last typed into a
     two-value column, and on this corpus it disagrees with the count often. It also has no word
     for "lapsing inside the window" and no word for "the paperwork does not settle it".
  2. "RECORDED: EXERCISED" IS NOT A PERFECTED EXTENSION. A payment-controlled extension needs a
     payment reference AND a payment date; a notice-controlled one needs notice served on the
     GRANTOR OF RECORD. An extension whose act is missing or misdirected does not stack.
  3. A CLOCK THAT HAS NOT STARTED IS NOT A LONG TIME LEFT. A triggering-event option whose event
     has not occurred is `not_determinable`, and reading it as `live` is the comfortable mistake --
     it removes a row from the worklist and looks like good news.
  4. A CONTRADICTION BLOCKS ONLY THE DATE THE CLOCK RUNS FROM. Two disagreeing grant dates settle
     nothing on a grant-date clock; on a triggering-event clock that has started, they are
     irrelevant and flagging the record is a FALSE ALARM.
  5. THE CLERK'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A relaxed note does not add a day to a term
     and a worried one does not remove one.

⚑ ONE CALL PER REGISTER, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.

⚠︎ AND THE ANSWER IS A PROPOSAL. The prompt says so, the UI says so and the kit's own pages say so:
nothing here exercises, renews, lapses, files or releases anything, and nothing in it watches
anything. It reads one snapshot somebody else assembled and proposes a worklist.
"""
import json

from .rulebook import R, WINDOW_DAYS

SYSTEM = (
    "You read a RIGHTS AND OPTION REGISTER SNAPSHOT for one property and extract structured fields "
    "from it. You return JSON and nothing else.\n"
    "\n"
    "You are PROPOSING a worklist for a qualified person to read the agreement against. You never "
    "exercise, renew, lapse, file or release anything, and you are not a substitute for the "
    "executed option agreement or for a lawyer's reading of it. You are not watching this "
    "register: you are reading ONE snapshot of it, as it stood on the date it states.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the register does not state a field, return null for it. Do not infer it and do not use "
    "what you know about how options usually work.\n"
    "2. `expiry_date` and `status` are decided ONLY by the COUNTING RULEBOOK given below, applied "
    "to the register's own values. Work through these four steps IN ORDER:\n"
    "   a. WHAT STARTS THE CLOCK. If the Clock Basis says grant_date, the clock starts on the "
    "grant date. If it says triggering_event, the clock starts on the date the Triggering Event "
    "section records the event as having OCCURRED. If that event has not occurred, the period has "
    "not started, no expiry can be counted, and the answer is 'not_determinable' -- it is NOT "
    "'live'.\n"
    "   b. A CONTRADICTED DATE IS NOT SETTLED. Look at how many dated entries the Option Granted "
    "section carries.\n"
    "      - ONE entry: that is the grant date. Return it in option_granted_date. This is true "
    "whatever the Clock Basis says -- a triggering-event clock does not make a stated grant date "
    "disappear, it just does not count from it. NEVER return null for option_granted_date when the "
    "section states exactly one date.\n"
    "      - TWO entries that disagree: the grant date is not settled, so return null for "
    "option_granted_date. Do NOT pick the earlier entry, the later entry, or the one from the more "
    "official-looking source. Then: if the clock runs from the GRANT DATE, there is nothing to "
    "count from and the answer is 'not_determinable'; if the clock runs from a TRIGGERING EVENT "
    "that has occurred, the grant date is not an input at all, the disagreement changes nothing, "
    "and you carry on counting normally from the trigger date.\n"
    "   c. WHICH EXTENSIONS ACTUALLY COUNT. Only PERFECTED ones. An extension entry saying "
    "'recorded: exercised' is a clerk's entry, not an act. A payment-controlled extension is "
    "perfected only when a payment reference AND a payment date are recorded against it. A "
    "notice-controlled extension is perfected only when notice was served on the GRANTOR OF RECORD "
    "-- the party named in the Rights Holder section. Service on an agent, a co-financier, an "
    "escrow agent or the grantee's own counsel does NOT perfect it, however customary that is.\n"
    "   d. ADD THE MONTHS AND COMPARE. Expiry = the clock start, plus the initial term, plus the "
    "length of each PERFECTED extension. Extensions run consecutively from the end of the period "
    "they extend, NEVER from the date they were exercised. Add the whole term in calendar months "
    "in one step from the clock start, keeping the same day of the month and falling back to the "
    "last day of a shorter month. Then compare against the register's own As Of date and the "
    "window the rulebook names.\n"
    "3. THE REGISTER'S OWN STATUS LINE IS NEVER AN INPUT. `register_status` is what somebody last "
    "typed. Report it as stated and then ignore it. It is often wrong on this kind of record, in "
    "both directions, and it has no word at all for an option lapsing inside the window or for one "
    "the paperwork does not settle.\n"
    "4. THE CLERK'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT THE CLOCK. A note that sounds "
    "worried does not shorten a term and a note that sounds relaxed does not lengthen one. The "
    "count decides; the note is one person's remark and may disagree with it.\n"
    "5. Copy titles, party names and the clerk's note verbatim. Return every date as an ISO date, "
    "YYYY-MM-DD, exactly as the register writes it.\n"
    "6. Use the exact allowed value for a field that lists them.\n"
    "7. Return every field named in the schema, even when the answer is null."
)


def rulebook_block(r=None):
    """The counting rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the rules inside this module is a copy that
    drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold labels disagree about the same count, silently, and the
    disagreement would score as a model failure.
    """
    r = r or R
    lines = ["COUNTING RULEBOOK (the authority for `expiry_date` and `status`; this is an "
             "ILLUSTRATIVE rulebook shipped with this kit, not an agreement and not a standard "
             "form)", "",
             "WHAT STARTS THE CLOCK"]
    for k in ("grant_date", "triggering_event"):
        lines.append("  %-18s %s" % (k + ":", r["clock_start"][k]))
    lines += ["  " + r["clock_start_note"], "",
              "A CONTRADICTED DATE", "  " + r["contradiction_rule"], "",
              "WHAT PERFECTS AN EXTENSION"]
    for k in ("payment", "notice"):
        lines.append("  %-18s %s" % (k + "-controlled:", r["perfection"][k]))
    lines += ["  " + r["perfection_note"], "",
              "HOW EXTENSIONS STACK", "  " + r["stacking_note"], "",
              "HOW MONTHS ARE ADDED", "  " + r["month_arithmetic_note"], "",
              "THE WINDOW", "  %d days. %s" % (int(r["window_days"]), r["window_note"]), "",
              "THE FOUR STATUSES"]
    for k in ("lapsed", "lapsing", "live", "not_determinable"):
        lines.append("  %-18s %s" % (k + ":", r["statuses"][k]))
    lines += ["", "WHAT IS NOT EVIDENCE",
              "  " + r["register_status_is_not_evidence"],
              "  " + r["clerk_note_is_not_evidence"]]
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
            "Use null for any field the register does not state.\n\n"
            "RIGHTS AND OPTION REGISTER\n--------------------------\n%s\n"
            % (RULEBOOK_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "counting rulebook", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "register sections", "text": context},
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


__all__ = ["SYSTEM", "RULEBOOK_TEXT", "WINDOW_DAYS", "rulebook_block", "field_schema", "build",
           "parse"]
