"""THE RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. The check this kit makes is
an arithmetic pass over a transaction log against a set of stated rules, so the rules have to be a
thing a reader can open, read, disagree with and replace -- not a dict buried in a Python module.
`data/rulebook.json` is that file. Everything below is the arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS INVENTED AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no real reporting regulation, no real filing form, no filing instruction, no supervisory
guidance and no operator's own compliance manual. The threshold, the aggregation window, the
staleness horizon, the element list and the transaction-code table were all made up. Amounts are in
CU, an invented unit that is not a currency. See data/SOURCES.md, and the same sentence is printed
on the kit's own UI where a reader actually reads the answer.

⚠︎ AND THIS KIT FILES NOTHING AND CLEARS NOTHING. `assess()` returns a list of defects with the
reasoning that produced each one, and names what it could not determine. It does not submit, lodge,
transmit, sign off, approve, clear or close anything, and no code path in this kit writes to any
system.

⚑ THE STOPPING ORDER IS THE WHOLE DIFFICULTY, AND IT EXISTS TO PROTECT THE FALSE-ALARM RATE.
Three of the seven defects surface identically -- the drafted total is lower than it should be --
so a checker with no stopping order reports one difference three times, and the false-alarm rate
becomes a property of the checker rather than of the filing. `assess()` names ONE cause per
difference:

  1. INSUFFICIENT INFORMATION. A qualifying entry whose amount was never captured, or a draft with
     no gaming day, means no total can be computed. Stop. This is a first-class answer, not a
     failure to produce one -- a QC pass that guesses here is worse than one that says it cannot
     tell, because the guess reaches the queue wearing the same confidence as a real finding.
  2. THRESHOLD NOT CROSSED. If the qualifying total never crossed the threshold, no filing is due
     at all and the draft should not exist. Stop -- the address block on a filing that should not
     exist is not the finding worth reporting.
  3. WINDOW MISAPPLIED. A draft that aggregated a calendar day rather than the gaming day has a
     named cause for its total difference. Do NOT also report missed_aggregation for it.
  4. IDENTITY SPLIT. Else, a second patron record that is the same person by the link keys, left
     out of the draft, is the named cause.
  5. MISSED AGGREGATION. Else, qualifying entries on the patron's own record were left out.
  6. CONTENT DEFECTS -- identification_gap and type_miscode -- are checked independently. They
     change what the filing SAYS, not what it FILES.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

THRESHOLD = R["threshold"]
UNIT = R["unit"]
STALE_DAYS = R["identification_stale_days"]
CODES = R["transaction_codes"]
ID_ELEMENTS = list(R["identification_elements"])

# The closed defect vocabulary. A code outside this set is not a finding, it is a parse failure.
DEFECTS = tuple(R["defect_codes"])
RECOMPUTE_DEFECTS = frozenset(R["recompute_defects"])

WINDOWS = ("gaming_day", "calendar_day", "other")
DIRECTIONS = ("cash_in", "cash_out")


def direction_of(code):
    """`in` / `out` for a transaction code, or None when the rulebook does not carry the code.

    None is a real answer and is deliberately NOT folded into "probably fine". A code the shipped
    rulebook has never heard of is exactly the entry a QC pass must escalate rather than quietly
    drop out of a total.
    """
    c = CODES.get(str(code or "").strip().lower())
    return c["direction"] if c else None


def reportable(code):
    """Is this code part of a CURRENCY total at all? A wire and a promotional credit are not."""
    c = CODES.get(str(code or "").strip().lower())
    return bool(c and c["reportable"])


def qualifies(entry, direction, gaming_day):
    """Does one log entry belong in this filing's total?

    Four conditions, all four required: the code is reportable, its direction is the filing's
    direction, the entry falls inside the gaming day, and the amount was actually captured.
    """
    want = "in" if direction == "cash_in" else "out"
    if not reportable(entry.get("code")):
        return False
    if direction_of(entry.get("code")) != want:
        return False
    if entry.get("gaming_day") != gaming_day:
        return False
    return True


def qualifying_total(entries, direction, gaming_day):
    """The total the filing SHOULD state, or None when an amount was never captured.

    ⚠︎ None IS NOT ZERO AND MUST NEVER BE TREATED AS ZERO. An entry whose amount the log never
    recorded makes the whole total unknowable, not smaller. Returning 0 here would turn every
    incomplete record into a `threshold_not_crossed` finding -- a confident, wrong "do not file"
    on a record nobody can actually read.
    """
    total = 0
    for e in entries:
        if not qualifies(e, direction, gaming_day):
            continue
        if e.get("amount") is None:
            return None
        total += e["amount"]
    return total


def _days_between(earlier, later):
    """Whole days between two YYYY-MM-DD strings, without importing a date library for one sum."""
    import datetime
    a = datetime.date(*(int(x) for x in earlier.split("-")))
    b = datetime.date(*(int(x) for x in later.split("-")))
    return (b - a).days


def identification_defect(missing_elements, captured_on, gaming_day):
    """(is_defect, reason). Missing element, or identification older than the staleness horizon."""
    missing = [m.strip() for m in (missing_elements or "").split(",") if m.strip()]
    if missing:
        return True, ("the draft does not carry %s, and the rulebook requires all %d elements"
                      % (" and ".join(missing), len(ID_ELEMENTS)))
    if captured_on and gaming_day:
        try:
            age = _days_between(captured_on, gaming_day)
        except (ValueError, TypeError):
            return False, None
        if age > STALE_DAYS:
            return True, ("the identification on the draft was captured %d days before the gaming "
                          "day, past the %d-day staleness horizon" % (age, STALE_DAYS))
    return False, None


def assess(draft_reported_total, log_qualifying_total, draft_window_applied,
           linked_record_id, draft_includes_linked_record, missing_identification_elements,
           identification_captured_on, gaming_day, miscoded_transaction_ids):
    """THE RULE, in one place. Returns {defects: [...], reasons: {...}, needs_recompute: bool}.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    values for the no-gold consistency diagnostic. They cannot drift about what a defect means.

    ⚠︎ IT PRE-CHECKS. IT NEVER FILES AND NEVER CLEARS. The return value is a worklist with its
    reasoning attached; a qualified person decides what is submitted. Nothing in this kit writes,
    transmits or signs anything.
    """
    out = {"defects": [], "reasons": {}, "needs_recompute": None}

    def add(code, why):
        if code not in out["defects"]:
            out["defects"].append(code)
            out["reasons"][code] = why

    # 1. Can the total be computed at all? Everything below depends on it.
    if gaming_day in (None, "") or log_qualifying_total is None:
        add("insufficient_information",
            "The qualifying total cannot be computed from this record -- an amount was never "
            "captured, or the draft does not state which gaming day it covers. Nothing about the "
            "total can be concluded, and this is not a clearance.")
        out["needs_recompute"] = True
        return out

    # 2. Should this filing exist at all?
    if log_qualifying_total <= THRESHOLD:
        add("threshold_not_crossed",
            "The qualifying total is %s %s, which does not cross the %s %s threshold. No filing "
            "is due for this patron and this gaming day."
            % (_fmt(log_qualifying_total), UNIT, _fmt(THRESHOLD), UNIT))
        out["needs_recompute"] = True
        return out

    # 3-5. ONE named cause for a total difference, in order.
    if draft_window_applied not in (None, "", "gaming_day"):
        add("window_misapplied",
            "The draft aggregated the %s rather than the gaming day, which runs from %s to %s the "
            "next date. Entries either side of that boundary are counted or dropped wrongly, and "
            "the drafted total of %s %s does not match the %s %s the gaming day produces."
            % (str(draft_window_applied).replace("_", " "), R["gaming_day_start"],
               R["gaming_day_start"], _fmt(draft_reported_total), UNIT,
               _fmt(log_qualifying_total), UNIT))
    elif linked_record_id and draft_includes_linked_record == "no":
        add("identity_split",
            "Record %s in the log matches this patron on both link keys, so it is the same person, "
            "and the draft aggregated only one of the two records. Together they total %s %s "
            "against the drafted %s %s."
            % (linked_record_id, _fmt(log_qualifying_total), UNIT,
               _fmt(draft_reported_total), UNIT))
    elif draft_reported_total is not None and log_qualifying_total > draft_reported_total:
        add("missed_aggregation",
            "Qualifying entries on this patron's own record are not in the drafted total: the log "
            "supports %s %s and the draft states %s %s, a shortfall of %s %s."
            % (_fmt(log_qualifying_total), UNIT, _fmt(draft_reported_total), UNIT,
               _fmt(log_qualifying_total - draft_reported_total), UNIT))

    # 6. Content defects, independent of the arithmetic above.
    is_id_defect, why = identification_defect(missing_identification_elements,
                                              identification_captured_on, gaming_day)
    if is_id_defect:
        add("identification_gap", why)

    miscoded = [m.strip() for m in (miscoded_transaction_ids or "").split(",") if m.strip()]
    if miscoded:
        add("type_miscode",
            "The draft codes %s differently from the log's own entry for it. The code decides "
            "which direction an entry belongs to and whether it is a currency movement at all."
            % (" and ".join(miscoded)))

    out["needs_recompute"] = bool(set(out["defects"]) & RECOMPUTE_DEFECTS)
    return out


def _fmt(n):
    if n is None:
        return "an unknown amount"
    return "{:,}".format(int(n))


def defects_of(values):
    """Just the defect list, sorted, from a dict of extracted values. `None` when the values are
    outside the vocabulary the rulebook carries."""
    d = assess(values.get("draft_reported_total"), values.get("log_qualifying_total"),
               values.get("draft_window_applied"), values.get("linked_record_id"),
               values.get("draft_includes_linked_record"),
               values.get("missing_identification_elements"),
               values.get("identification_captured_on"), values.get("gaming_day"),
               values.get("miscoded_transaction_ids"))
    return sorted(d["defects"])
