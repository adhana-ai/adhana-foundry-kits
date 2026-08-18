"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER MESSAGE, NOT PER CANDIDATE. A message is checked against every one of its blocked
candidates (zero, one or several) in a single call, the same batching discipline data-reconcile
uses for its five checks: the candidates are the expensive, repeated payload, so asking about all
of them at once is what keeps this kit from re-sending them once per candidate for separate
answers.

⚠︎ THE MODEL DOES THE JUDGEMENT; THE CODE DOES THE ARITHMETIC. The model is asked for exactly three
things: which record (if any) the message is about, what kind of change it is asking for, and the
new value stated in the text -- plus a citation, which is not decoration (same discipline as
data-reconcile's citation requirement: a match with no evidence beside it is an assertion, not a
finding). Downstream impact is never asked of the model; src/impact.py computes it from the
record and the extracted new_value alone, so an impact number is only ever as wrong as the
extraction that produced it.

⚑ THREE MATCH OUTCOMES, NOT TWO. `NONE` says none of the candidates are what this message is
about; `UNSURE` says the message could plausibly refer to more than one candidate and nothing in
the text settles it. A model that defaults an unsure case to its best guess converts a genuine gap
into a confident wrong answer -- the same failure the third verdict exists to prevent everywhere
else in this series.
"""
import json

CHANGE_TYPES = ("expedite", "delay", "cancel", "qty_change", "price_change")

CHANGE_MEANINGS = {
    "expedite": "the ship date should move EARLIER than currently recorded",
    "delay": "the ship date should move LATER than currently recorded",
    "cancel": "the record should be cancelled entirely -- no replacement",
    "qty_change": "the quantity should change to a new stated amount",
    "price_change": "the unit cost should change to a new stated amount",
}

_CHANGES_TXT = "".join("  %-14s %s\n" % (c, CHANGE_MEANINGS[c]) for c in CHANGE_TYPES)

SYSTEM = (
    "You read one piece of correspondence that requests a change to a record, plus a list of "
    "candidate records it might be about (all belonging to the same sender). Decide which "
    "candidate, if any, the correspondence refers to, then extract the requested change.\n\n"
    "MATCH\n"
    "  a candidate's record_id   the correspondence clearly names or clearly implies exactly "
    "one candidate\n"
    "  NONE                      none of the listed candidates are what the correspondence is "
    "about\n"
    "  UNSURE                    it could plausibly be more than one candidate and nothing in "
    "the text settles it -- do not guess\n\n"
    "CHANGE TYPE (only if MATCH is a record_id)\n" + _CHANGES_TXT + "\n"
    "NEW VALUE, exactly one of these shapes depending on change_type:\n"
    "  expedite / delay   {\"new_ship_date\": \"YYYY-MM-DD\"}\n"
    "  qty_change         {\"new_qty\": <integer>}\n"
    "  price_change       {\"new_unit_cost\": <number>}\n"
    "  cancel             null\n\n"
    "Read every candidate's fields (product, quantity, ship date) before deciding -- when more "
    "than one candidate is listed, the correspondence usually states the CURRENT value of a "
    "field the change does not touch (a quantity or a date), specifically so you can tell the "
    "candidates apart. If MATCH is NONE or UNSURE, change_type, new_value and citation must all "
    "be null.\n\n"
    "Cite the exact sentence or clause from the correspondence you relied on for your match and "
    "your extraction, verbatim."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _candidate_block(rec):
    return ("  %s -- %s, qty %d @ $%.2f/unit, ship date %s, ships to %s%s"
           % (rec["record_id"], rec["description"], rec["qty"], rec["unit_cost"],
              rec["ship_date"], rec["ship_to"],
              (", live promotion ends %s" % rec["promo_end"]) if rec.get("promo_end") else ""))


def build(message, candidates, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    msg_block = "CORRESPONDENCE\n---------------\n%s\n" % message["text"]
    if candidates:
        cand_block = "CANDIDATES\n----------\n" + "\n".join(_candidate_block(c) for c in candidates) + "\n"
    else:
        cand_block = "CANDIDATES\n----------\n(none -- blocking found no open record for this sender's product)\n"
    user = (
        "%s\n%s\n"
        "Return a JSON object with exactly these keys: "
        "{\"match\": <a record_id, \"NONE\", or \"UNSURE\">, "
        "\"change_type\": <one of %s, or null>, "
        "\"new_value\": <the shape named above for that change_type, or null>, "
        "\"citation\": <verbatim quote from the correspondence, or null>}."
        % (msg_block, cand_block, ", ".join(CHANGE_TYPES))
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "correspondence", "text": msg_block},
        {"name": "candidates", "text": cand_block},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the match/change/new_value/citation out of a model reply, tolerantly but never
    creatively. A reply that does not parse yields all-None -- read as "this call produced no
    answer", never as evidence about the message."""
    out = {"match": None, "change_type": None, "new_value": None, "citation": None}
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    match = obj.get("match")
    if isinstance(match, str) and match.strip():
        out["match"] = match.strip().upper() if match.strip().upper() in ("NONE", "UNSURE") \
            else match.strip()
    ct = obj.get("change_type")
    if isinstance(ct, str):
        ct_norm = ct.strip().lower().replace(" ", "_").replace("-", "_")
        if ct_norm in CHANGE_TYPES:
            out["change_type"] = ct_norm
    nv = obj.get("new_value")
    if isinstance(nv, dict):
        out["new_value"] = nv
    cit = obj.get("citation")
    if isinstance(cit, str):
        out["citation"] = cit
    return out
