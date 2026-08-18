"""What blocking plus string similarity catches, with no model anywhere. Free. No key, no
dependency, no network.

    python -m evals.baseline

Every sibling kit publishes this floor -- data-match's weighted field score, data-reconcile's
regex extraction -- and this one is the same idea applied to a match-and-extract task: reuse
src/block.py's own candidate generation (the SAME code the real pipeline runs), resolve ties with
a numeric read of the disambiguating hint this corpus plants, fall back to string similarity when
that fails, and pull the change type and its new value out with a handful of regexes tuned
against the phrasing this kit's own corpus actually uses.

⚠︎ THIS IS NOT A COMPETITOR TO THE MODEL, IT IS THE FLOOR THE MODEL HAS TO CLEAR. Where it wins
for free (an explicit record id or SKU code makes the match trivial), the model should win too --
that is not where the interesting gap is. The gap this kit exists to measure is the ~40% of
messages with no explicit id: string similarity cannot read "currently at 100 units" as a
disambiguating clue about a field the model was told to compare numerically, and that is measured
below, not asserted.
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import block, impact as I, match as M, normalise, similarity as SIM  # noqa: E402
from evals import scoring as S                                            # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

SIM_THRESHOLD = 0.35            # below this, the floor declines rather than guesses -- see UNSURE

_HINT_QTY_RE = re.compile(r"currently at (\d+) units")
_HINT_DATE_RE = re.compile(r"currently scheduled to ship ([A-Za-z]+ \d{1,2})")
_QTY_RE = re.compile(r"(\d+) units")
_PRICE_RE = re.compile(r"\$(\d+\.\d+)")
_MONTH_DAY_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|"
                           r"October|November|December) (\d{1,2})")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"])}


def _strip_hint(text):
    """Drop the parenthetical disambiguating clue before extracting the REQUESTED value, so a
    baseline reading the corpus's own hint format does not confuse 'currently at 100 units' with
    the number actually being asked for."""
    return re.sub(r"\([^)]*\)", "", text)


def classify(text):
    """Change type by keyword, checked in an order that resolves the corpus's own overlaps (a
    price message also says 'per unit'; a qty message also says 'order to N units')."""
    t = text.lower()
    if "cancel" in t:
        return "cancel"
    if "$" in t or "unit cost" in t or "pricing" in t:
        return "price_change"
    if ("expedite" in t or ("pull" in t and "forward" in t) or "sooner" in t
            or "earlier than scheduled" in t):
        return "expedite"
    if ("delay" in t or "push the ship date" in t or "reschedule" in t or "hold the" in t
            or "won't be able to receive" in t):
        return "delay"
    if "quantity" in t or "adjust the" in t or re.search(r"\d+ units", t):
        return "qty_change"
    return None


def extract_new_value(text, change_type):
    stripped = _strip_hint(text)
    if change_type in ("expedite", "delay"):
        m = _MONTH_DAY_RE.search(stripped)
        if not m:
            return None
        month, day = _MONTHS[m.group(1)], int(m.group(2))
        # Honest floor, not a clever one: this kit's whole corpus sits in one calendar year, and a
        # quick script that has read a handful of examples would hardcode that rather than solve
        # general date math for a one-shot extractor.
        year = 2026
        try:
            return {"new_ship_date": datetime.date(year, month, day).isoformat()}
        except ValueError:
            return None
    if change_type == "qty_change":
        m = _QTY_RE.search(stripped)
        return {"new_qty": int(m.group(1))} if m else None
    if change_type == "price_change":
        m = _PRICE_RE.search(stripped)
        return {"new_unit_cost": float(m.group(1))} if m else None
    return None


def resolve_match(message, candidates):
    if not candidates:
        return "NONE"
    if len(candidates) == 1:
        return candidates[0]["record_id"]

    # An explicit record id in the text is the strongest signal there is -- a quick script would
    # obviously regex for it before falling back to anything fuzzy. Blocking's own candidate set
    # is a UNION over several keys (recid, SKU code, product description), so an explicit id can
    # still arrive alongside 1-2 sibling records that share the same product; check for the id
    # itself before treating this as a genuinely undetermined case.
    ids = normalise.find_recid(message["text"])
    if ids:
        hit = next((c for c in candidates if c["record_id"] == ids), None)
        if hit:
            return hit["record_id"]

    hm = _HINT_QTY_RE.search(message["text"])
    if hm:
        want = int(hm.group(1))
        hits = [c for c in candidates if c["qty"] == want]
        if len(hits) == 1:
            return hits[0]["record_id"]

    dm = _HINT_DATE_RE.search(message["text"])
    if dm:
        month, day = _MONTHS[dm.group(1).split()[0]], int(dm.group(1).split()[1])
        hits = [c for c in candidates
               if datetime.date.fromisoformat(c["ship_date"]).month == month
               and datetime.date.fromisoformat(c["ship_date"]).day == day]
        if len(hits) == 1:
            return hits[0]["record_id"]

    best, sim = SIM.best_candidate(message["text"], candidates)
    return best["record_id"] if sim >= SIM_THRESHOLD else "UNSURE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-blocking-similarity")
    a = ap.parse_args()

    vendors = M.vendors_by_id()
    vsku = M.records_by_vendor_sku()
    records = M.records_by_id()
    gold = M.load_gold()

    rows = []
    for msg in M.load_messages():
        v = vendors[msg["vendor_id"]]
        cand = block.candidates(msg, v, vsku)["candidates"]
        match = resolve_match(msg, cand)
        ct = classify(msg["text"]) if match not in ("NONE", "UNSURE") else None
        nv = extract_new_value(msg["text"], ct) if ct else None
        rows.append({"message_id": msg["message_id"], "vendor_id": msg["vendor_id"],
                    "candidates": [c["record_id"] for c in cand], "match": match,
                    "change_type": ct, "new_value": nv})

    scored = S.score(rows, gold, records)
    out = {"run_id": a.run_id, "baseline": True, "messages": len(rows),
          "scores": scored["overall"], "per_change_type": scored["per_change_type"]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("blocking+similarity baseline over %d messages" % len(rows))
    print("match accuracy   : %s%%" % o["match_accuracy_pct"])
    print("impact accuracy  : %s%% (of correctly matched, real-record cases)" % o["impact_accuracy_pct"])
    print("false NONE       : %s (%s%% of gold real matches)" % (o["false_none"], o["false_none_rate_pct"]))
    print("false match      : %s (%s%% of gold NONE cases)" % (o["false_match"], o["false_match_rate_pct"]))
    print("abstained UNSURE : %s" % o["abstained_unsure"])
    for ct, pc in scored["per_change_type"].items():
        print("  %-14s match %s%%  impact %s%%  (n=%d)"
              % (ct, pc["match_accuracy_pct"], pc["impact_accuracy_pct"], pc["n"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
