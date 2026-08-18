"""What regex alone catches, over the same corpus. Free. No key, no dependency, no model call.

    python -m evals.baseline

Every sibling kit publishes this floor — data-match's string-similarity score, docs-verify's
lexical match, docs-comply's b000-label — and this kit's is the same idea applied to extraction:
pull each check's number out of the agreement text with a handful of regexes tuned against the
phrasing this kit's own corpus actually uses, then run the same deterministic comparison
`src/reconcile.py` would run on numbers a model extracted.

⚠︎ THIS IS NOT A COMPETITOR TO THE MODEL, IT IS THE FLOOR THE MODEL HAS TO CLEAR. The corpus's
agreement text is deliberately written in three phrasing variants per clause (see
tools/build_corpus.py::agreement_text) precisely so a fixed set of patterns cannot cover all of
them. Where a pattern only matches the phrasing it was written against, the check comes back
`unverifiable` here even though the agreement does state the clause — that gap, measured per
check below, is what a model reading the sentence is actually for.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import reconcile as R                                # noqa: E402
from evals import scoring as S                                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

_COST_RE = re.compile(r"(SKU-\d+)[^.$]{0,40}?\$([\d,]+\.\d{2})")

# ⚠︎ ONE PATTERN PER FIELD, DELIBERATELY, NOT ONE PER PHRASING VARIANT. tools/build_corpus.py
# writes each clause in one of two or three hand-written phrasings (see agreement_text). A regex
# author who has not read every agreement in the corpus writes the pattern that matches the
# phrasing they saw first and moves on -- which is exactly this list. Widening it to cover every
# variant that ships would make this file the thing it exists to be the honest floor under. The
# cost pattern above is the one exception: it is a loose SKU-then-$ scan with no fixed keyword, so
# it happens to transfer across phrasings without anyone writing it to.
_MINQTY_RE = [re.compile(r"[Mm]inimum order quantity is (\d+) units")]
_PACK_RE = re.compile(r"cartons? of (\d+)")
_LEAD_RE = [re.compile(r"[Ll]ead time is (\d+) business days")]
_REGIONS_RE = [re.compile(r"[Aa]pproved ship-to regions[^:]*:\s*([A-Z0-9, \-]+?)\.")]
_BAND_RE = [re.compile(r"between \$([\d,]+) and \$([\d,]+)")]


def _first(patterns, text, n_groups=1):
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.groups() if n_groups > 1 else m.group(1)
    return None


def extract(agreement_text):
    """Best-effort structured facts out of one agreement's prose. Any field this cannot find
    stays None -- callers treat None as 'no clause found', which is exactly what makes it an
    honest floor rather than a guesser."""
    costs = {sku: float(c.replace(",", "")) for sku, c in _COST_RE.findall(agreement_text)}
    min_qty = _first(_MINQTY_RE, agreement_text)
    pack = _PACK_RE.search(agreement_text)
    lead_time = _first(_LEAD_RE, agreement_text)
    regions_raw = _first(_REGIONS_RE, agreement_text)
    band = _first(_BAND_RE, agreement_text, n_groups=2)
    return {
        "costs": costs,
        "min_qty": int(min_qty) if min_qty else None,
        "pack": int(pack.group(1)) if pack else 1,
        "lead_time_days": int(lead_time) if lead_time else None,
        "regions": ([r.strip() for r in regions_raw.split(",")] if regions_raw else None),
        "value_band": ((float(band[0].replace(",", "")), float(band[1].replace(",", "")))
                       if band else None),
    }


def judge(order, facts):
    """The same deterministic comparison a perfect extractor would run -- this is not where the
    baseline is weak. It is weak in `extract()`, which is the point."""
    out = {}

    cost_defect = False
    for l in order["lines"]:
        known = facts["costs"].get(l["sku"])
        if known is None:
            out["cost"] = "unverifiable"
            break
        if abs(known - l["unit_cost"]) > 0.005:
            cost_defect = True
    else:
        out["cost"] = "defect" if cost_defect else "clean"

    if facts["min_qty"] is None:
        out["min_qty"] = "unverifiable"
    else:
        under = any(l["qty"] < facts["min_qty"] for l in order["lines"])
        out["min_qty"] = "defect" if under else "clean"

    if facts["lead_time_days"] is None:
        out["lead_time"] = "unverifiable"
    else:
        out["lead_time"] = ("defect" if order["requested_ship_days"] < facts["lead_time_days"]
                            else "clean")

    if facts["regions"] is None:
        out["ship_to"] = "unverifiable"
    else:
        out["ship_to"] = "clean" if order["ship_to"] in facts["regions"] else "defect"

    if facts["value_band"] is None:
        out["order_value"] = "unverifiable"
    else:
        lo, hi = facts["value_band"]
        out["order_value"] = ("clean" if lo <= order["total_value"] <= hi else "defect")

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-regex")
    a = ap.parse_args()

    gold = R.load_gold()
    records = []
    for order in R.orders():
        text = R.load_agreement(order["supplier_id"])
        facts = extract(text)
        verdicts = judge(order, facts)
        records.append({"order_id": order["order_id"],
                        "checks": [{"check": c, "verdict": v} for c, v in verdicts.items()]})

    scored = S.score(records, gold)
    out = {"run_id": a.run_id, "baseline": True, "orders": len(records),
          "scores": scored["overall"], "per_check": scored["per_check"]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("regex baseline over %d orders, %d checks" % (len(records), scored["overall"]["checks_scored"]))
    print("overall accuracy: %s%%" % scored["overall"]["accuracy_pct"])
    for c, pc in scored["per_check"].items():
        print("  %-12s accuracy %s%%  (unverifiable-by-baseline: %s of %s)"
              % (c, pc["accuracy_pct"], pc["predicted_unverifiable"], pc["gold_total"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
