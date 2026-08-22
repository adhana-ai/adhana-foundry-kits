"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ `defects_found` HERE IS A DELIBERATE TONE FLOOR, WRITTEN TO FAIL THE PLANTED AMBIGUITY BY
CONSTRUCTION. It reads the preparer's own note and nothing else: a note carrying one of a fixed list
of anxious-sounding phrases means `missed_aggregation`, and anything else means `none`. That is
precisely the shortcut the prompt's rules forbid -- deciding whether a filing is defective from
prose written by the person whose work is being checked, instead of from the rulebook and the
numbers.

⚑ AND IT IS THE RIGHT FLOOR FOR THIS PARTICULAR KIT, BECAUSE IT IS THE SHORTCUT A REAL QC DESK
ACTUALLY TAKES. Under time pressure, a preparer's confident sign-off is the cheapest signal on the
page, and a team that leans on it is not being lazy -- it is being fast. This floor measures what
that costs: on this corpus the note points the wrong way on 22 of 56 packs, so a tone read both
misses real defects and raises alarms on filings with nothing wrong with them, and the second half
of that is the number this kit leads with.

⚑ NOTE ALSO WHAT A TONE READ CANNOT REACH AT ALL. It can express concern; it cannot name WHICH of
seven defects a filing carries, and it can never distinguish `threshold_not_crossed` (this filing
should not exist) from `identification_gap` (this filing is missing a field). Six of the seven
defect codes are outside what tone can say, by construction, and the floor's per-code breakdown
reports that as zeroes rather than hiding it.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS BASELINE PERFECT, AND THAT IS THE POINT OF NOT DOING IT. The
floor already regexes the totals, the window, the identification block, both records and every
transaction code out of the pack; calling src.rulebook.assess() on them would score 100 pct and tell
you nothing about the model. So the floor is deliberately the SHORTCUT, not the rulebook, and the
gap it opens is the gap between reading prose and doing the arithmetic.

⚠︎ THE KEYWORD LIST WAS CHECKED AGAINST BOTH NOTE REGISTERS BEFORE THIS FLOOR WAS FIRST RUN, NOT
AFTER A DEFECT WAS FOUND LIVE. A sibling kit earlier in this series shipped a keyword that fired on
a negation inside a relaxed note, mis-registering four records for days before it was caught. Every
phrase here is multi-word or a stem that appears in one register only, and evals/check_labels.py
asserts that property before any run may spend.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a tone-derived defect list produces a
tone-derived recompute flag. That is worth publishing rather than hiding -- a business-condition
guardrail is only ever as good as the field it reads.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute

# Anxious-sounding phrases, chosen so none of them is a substring of any CONFIDENT note in
# tools/build_corpus.py -- checked directly against both note lists, not assumed. Multi-word phrases
# are used deliberately where a single word ("review", "checked", "totals") appears in BOTH
# registers on this corpus and would misfire either way.
ANXIOUS_KEYWORDS = ("not confident", "re-add", "looked off", "second review", "disputed",
                    "manual audit", "escalated", "rather someone else")


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _int(raw):
    if raw is None:
        return None
    m = re.search(r"(-?[\d,]+)\s*CU", raw)
    return int(m.group(1).replace(",", "")) if m else None


def _window(raw):
    low = (raw or "").lower()
    if low.startswith("gaming day"):
        return "gaming_day"
    if low.startswith("calendar day"):
        return "calendar_day"
    return "other" if low else None


def _identification(raw):
    """(missing_elements, captured_on) read straight off the draft's identification block."""
    if raw is None:
        return None, None
    present = set()
    captured = None
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "identification captured on":
            captured = v or None
        elif v:
            present.add(k)
    missing = [e for e in RB.ID_ELEMENTS if e not in present]
    return (", ".join(missing) or None), captured


def _log_rows(raw):
    """[(id, date, time, record, code, amount_or_None)] off the cage log."""
    out = []
    for line in (raw or "").splitlines():
        m = re.match(r"(TXN-\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(\S+)\s+(\S+)\s+(.*)$",
                     line.strip())
        if not m:
            continue
        tid, date, time, record, code, amount = m.groups()
        a = None if "not captured" in amount else _int(amount)
        out.append((tid, date, time, record, code, a))
    return out


def _draft_rows(raw):
    """[(id, code)] off the draft's included-transactions table."""
    out = []
    for line in (raw or "").splitlines():
        m = re.match(r"(TXN-\d+)\s+(\S+)\s", line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _linked(raw):
    m = re.search(r"(PR-\S+)\s+--", raw or "")
    return m.group(1) if m else None


def extract_one(text, fields):
    filing_id = _section(text, "Draft Filing")
    patron_record_id = _section(text, "Patron Record")
    gaming_day = _section(text, "Gaming Day")
    draft_direction = _section(text, "Direction Reported")
    draft_reported_total = _int(_section(text, "Reported Total"))
    draft_window_applied = _window(_section(text, "Window Applied"))
    missing_elements, captured_on = _identification(
        _section(text, "Patron Identification On The Draft"))
    preparer_note = _section(text, "Preparer Note")

    log = _log_rows(_section(text, "Cage Transaction Log"))
    draft = _draft_rows(_section(text, "Transactions Included On The Draft"))
    linked_record_id = _linked(_section(text, "Other Patron Records In This Log"))

    entries = [{"id": t, "date": d, "time": tm, "record": r, "code": c, "amount": a,
                "gaming_day": _gaming_day_of(d, tm)} for (t, d, tm, r, c, a) in log]
    log_qualifying_total = RB.qualifying_total(entries, draft_direction, gaming_day)

    draft_ids = {t for t, _c in draft}
    linked_ids = {e["id"] for e in entries if linked_record_id and e["record"] == linked_record_id
                  and RB.qualifies(e, draft_direction, gaming_day)}
    if not linked_record_id:
        includes_linked = "not_applicable"
    elif linked_ids and linked_ids <= draft_ids:
        includes_linked = "yes"
    else:
        includes_linked = "no"

    by_id = {t: c for (t, d, tm, r, c, a) in log}
    miscoded = [t for (t, c) in draft if by_id.get(t) and by_id[t] != c]

    # ⚑ THE SHORTCUT, AND THE ONLY PLACE THIS FLOOR DIFFERS FROM A CORRECT CHECKER.
    low = (preparer_note or "").lower()
    defects = "missed_aggregation" if any(k in low for k in ANXIOUS_KEYWORDS) else "none"

    values = {
        "filing_id": filing_id, "patron_record_id": patron_record_id, "gaming_day": gaming_day,
        "draft_direction": draft_direction, "draft_reported_total": draft_reported_total,
        "log_qualifying_total": log_qualifying_total,
        "draft_window_applied": draft_window_applied,
        "linked_record_id": linked_record_id,
        "draft_includes_linked_record": includes_linked,
        "missing_identification_elements": missing_elements,
        "identification_captured_on": captured_on,
        "miscoded_transaction_ids": ", ".join(miscoded) or None,
        "preparer_note": preparer_note, "defects_found": defects,
    }
    out = {f["name"]: {"value": values.get(f["name"]),
                       "spannable": f.get("spannable", f.get("type") != "enum"),
                       "span": None} for f in fields}
    return {"fields": out, "needs_recompute": _compute(values), "recomputed_defects": [],
            "recomputed_reasons": {}, "sections_used": [], "prompt_parts": [],
            "input_tokens": 0, "output_tokens": 0, "parsed": True}


def _gaming_day_of(date_str, time_str):
    import datetime
    d = datetime.date(*(int(x) for x in date_str.split("-")))
    hh = int(time_str.split(":")[0])
    return (d if hh >= 6 else d - datetime.timedelta(days=1)).isoformat()


def extract(text, fields):
    return extract_one(text, fields)
