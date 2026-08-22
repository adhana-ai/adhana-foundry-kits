"""Assemble the scheduling-order prompt. One prompt per order, every obligation in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `due_date`, AND IT IS ARITHMETIC, NOT A READING. The counting
rules are stated in full AND THE RULEBOOK ITSELF IS SENT WITH THEM, because what a business day is,
whether the trigger day counts and what happens when a period lands on a closed day are answers a
model cannot look up in a file it has never been shown. The alternative -- letting the model count
by whatever convention it has absorbed -- is exactly the failure this kit exists to measure: the
shipped rulebook is the authority here, and a count that disagrees with it is wrong on this corpus
even where the convention is arguable somewhere else.

Five things are spelled out that a reader left to their own habits gets wrong:

  1. THE TRIGGER DAY IS DAY ZERO. The day the Order was entered, or the day the event happened, is
     not counted. Counting begins the next day. Inclusive counting is the commonest desk error and
     it is off by one on every period.
  2. BUSINESS DAYS ARE NOT CALENDAR DAYS. A ten-business-day period is fourteen calendar days at
     best and more across a court holiday. Counting them alike is the second commonest error, and
     it is wrong by two days a week.
  3. A CALENDAR PERIOD ROLLS; A STATED DATE DOES NOT. A period counted in calendar days that ends
     on a weekend or a court holiday moves forward to the next business day -- sometimes two days,
     when the neighbouring Monday or Friday is itself a holiday. A date the Order names IN WORDS is
     the date the Order names, weekend or not. A reader who has learned to roll rolls both.
  4. AN UNDATED TRIGGER HAS NO DATE. If the Recorded Events table says the triggering event is not
     recorded, `due_date` is null. It is not the Order date, it is not zero days, it is not a
     guess. A confident wrong date on a docketing queue is worse than a blank, because a blank gets
     chased and a date gets diarised.
  5. THE PARENTHETICAL IS A FIELD TO COPY, NOT THE ANSWER. Somebody's own arithmetic written next
     to the obligation is extracted as `party_calculated_date` and decides nothing. On this corpus
     it is wrong often enough to matter.

⚑ ONE CALL PER ORDER, NOT ONE PER OBLIGATION -- same reasoning as every sibling extraction kit,
and sharper here: the obligations of one order share an Order date and one events table, so
splitting them would pay for both again on every paragraph.

⚠︎ AND THE CALENDAR IS A PROPOSAL. The prompt says so, the UI says so and the kit's own pages say
so: nothing here files, serves, dockets or waives anything.
"""
import json

from .calendar_rules import R

SYSTEM = (
    "You read a SCHEDULING ORDER and return, for every paragraph that sets a deadline, the "
    "structured facts of that deadline and the calendar date it falls due. You return JSON and "
    "nothing else.\n"
    "\n"
    "You are PROPOSING a calendar for a person to check. You do not file, serve, docket, waive or "
    "extend anything, and nothing you return is legal advice or a substitute for the file and the "
    "rules that actually govern it.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the Order does not state a value, return null for it. Do not infer it and do not use "
    "what you know about how courts usually count.\n"
    "2. RETURN A ROW ONLY FOR A PARAGRAPH THAT SETS A DEADLINE. A paragraph that merely mentions a "
    "date, sets a page limit, vacates a trial date, supersedes an earlier order, or states a "
    "deadline and then STRIKES, WITHDRAWS or disapplies it, sets no date and gets NO row. A row "
    "for one of those is a diary entry nobody owes.\n"
    "3. `due_date` is computed ONLY by the COUNTING RULES given below, applied to the paragraph's "
    "own basis, its period and the date it runs from. Work through it in this order:\n"
    "   a. EXPLICIT. If the paragraph names a date ('on or before', 'no later than'), that date IS "
    "the answer. It is NEVER moved, not even when it falls on a weekend or a court holiday.\n"
    "   b. WHAT IT RUNS FROM. 'the date of this Order' is the Order date. Anything else named after "
    "'after' is a triggering event, and its date comes from the RECORDED EVENTS table. If that "
    "table says the event is not recorded, STOP: `due_date` is null and `trigger_event_date` is "
    "null. Never substitute the Order date for an event the Order does not date.\n"
    "   c. COUNT. The day it runs from is DAY ZERO and is not counted; counting starts the next "
    "day. A period stated in DAYS counts every day including weekends and court holidays. A period "
    "stated in BUSINESS DAYS counts only business days -- Monday to Friday, excluding every court "
    "holiday on the list below.\n"
    "   d. ROLL. If a period counted in DAYS ends on a day that is not a business day, move it "
    "FORWARD to the next business day, and keep moving until you reach one. A period counted in "
    "BUSINESS days cannot end on a non-business day, so it never rolls.\n"
    "4. THE PARTY'S OWN CALCULATION IS A FIELD, NOT EVIDENCE. A parenthetical such as \"(counsel's "
    "calendar: 19 March 2027)\" is copied into `party_calculated_date` and is NEVER copied into "
    "`due_date`. It is somebody's arithmetic and on these orders it is sometimes wrong.\n"
    "5. Every date you return is ISO, YYYY-MM-DD. The Order writes dates in words.\n"
    "6. Copy `item` and `trigger_event` verbatim from the Order, in the lower case it states them.\n"
    "7. Use the exact allowed value for a field that lists them, and return every field named in "
    "the schema, even when the answer is null."
)


def rulebook_block(r=None):
    """The counting rules, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the holiday list inside this module is a copy
    that drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold dates disagree about the same calendar, silently, and the
    disagreement would score as a model failure.
    """
    r = r or R
    lines = ["COUNTING RULES (%s, the authority for `due_date`; this is an ILLUSTRATIVE rulebook "
             "written for this kit, not any real jurisdiction's rules)" % r["code"], "",
             "BUSINESS DAY",
             "  Monday to Friday, excluding every court holiday listed below.",
             "  %s and %s are not business days." % (r["weekend"][0], r["weekend"][1]), "",
             "WHEN COUNTING STARTS",
             "  " + r["trigger_day_note"], "",
             "HOW EACH BASIS IS COUNTED"]
    for b in r["bases"]:
        lines.append("  %-26s %s" % (b["code"] + ":", b["counts"]))
        lines.append("  %-26s wording: %s" % ("", b["wording"]))
        lines.append("  %-26s rolls to the next business day: %s"
                     % ("", "YES" if b["rolls"] else "NO"))
    lines += ["", "ROLLING", "  " + r["roll"]["note"], "",
              "WHEN NO DATE CAN BE COMPUTED", "  " + r["undatable_note"], "",
              "COURT HOLIDAYS -- not business days, and they are counted through by a period "
              "stated in DAYS and skipped by a period stated in BUSINESS DAYS"]
    for h in r["holidays"]:
        lines.append("  %s  %s" % (h["date"], h["name"]))
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
        for sub in f.get("subfields") or []:
            s = "    - %s (%s)" % (sub["name"], sub["type"])
            if sub.get("values"):
                s += " one of: %s" % ", ".join(sub["values"])
            s += " -- %s" % sub.get("hint", "")
            out.append(s)
    return "\n".join(out)


def _shape(fields):
    """The exact JSON shape wanted, written out once so a reply cannot be structurally surprising."""
    top = [f["name"] for f in fields]
    arr = [f for f in fields if f.get("subfields")]
    sub = [s["name"] for s in (arr[0]["subfields"] if arr else [])]
    return ("Return a JSON object with exactly these keys: %s\n"
            "`%s` is an ARRAY. Each element is an object with exactly these keys: %s\n"
            "Return an empty array only if the Order sets no deadline at all.\n"
            "Use null for any value the Order does not state."
            % (", ".join(top), arr[0]["name"] if arr else "deadlines", ", ".join(sub)))


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

    # ⚑ THE SCHEMA PART CARRIES THE SHAPE BLOCK WITH IT, so the four `parts` below CONCATENATE to
    # exactly the prompt that is sent. evals/prompt_tokens.py measures each part as the difference
    # between two consecutive nested prefixes; a part list that does not sum to the whole prompt
    # would publish a token split whose remainder nobody notices.
    schema = field_schema(fields) + "\n\n" + _shape(fields)
    user = ("%s\n\n"
            "Extract these fields:\n%s\n\n"
            "SCHEDULING ORDER\n----------------\n%s\n"
            % (RULEBOOK_TEXT, schema, context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "counting rules", "text": RULEBOOK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "order sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    """The reply as {matter_number, order_date, deadlines:[...]}, or {} when nothing parses.

    ⚠︎ FAILS CLOSED, AND THE ARRAY FAILS CLOSED SEPARATELY. A reply whose top level parses but
    whose `deadlines` is a string, a dict or a list of strings is not half an answer -- it is an
    answer this kit cannot score, and returning an empty array for it would record "the Order sets
    no deadlines", which is a claim the model never made.
    """
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

    arr = [f for f in fields if f.get("subfields")]
    array_name = arr[0]["name"] if arr else "deadlines"
    subnames = [x["name"] for x in (arr[0]["subfields"] if arr else [])]

    out = {}
    for f in fields:
        if f["name"] == array_name:
            continue
        out[f["name"]] = obj.get(f["name"])

    rows = obj.get(array_name)
    if not isinstance(rows, list):
        return {}
    clean = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        clean.append({k: r.get(k) for k in subnames})
    out[array_name] = clean
    return out
