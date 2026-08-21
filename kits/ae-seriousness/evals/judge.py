"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Every (record, field) cell is scored as extraction only: hit / miss / wrong.

⚠︎ ONE FIELD IN THIS CORPUS IS LEGITIMATELY NULL, AND THE SIBLING KITS' SCORER WOULD HAVE MARKED
EVERY CORRECT NULL WRONG. `narrative_severity_word` is null on the records whose report reaches
for no severity word at all, and returning null there is the CORRECT answer -- the prompt asks for
it explicitly. The scorer this kit was templated from marked any null extraction a `miss` before
it ever looked at gold, because no field in that corpus was ever null and the branch was never
exercised. Here it would have silently cost the model 7 cells it got right, and it would have
looked like a model failure rather than a scorer bug. Correct abstention is scored as a hit; a
null where gold has a value is still a miss.
"""
import re

from src.extract import compute as _compute


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _num(v):
    m = re.search(r"-?\d+(\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else None


def equal(field, got, want):
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    if g == w:
        return True
    if field.get("type") in ("number", "integer"):
        gn, wn = _num(g), _num(w)
        return gn is not None and wn is not None and abs(gn - wn) < 0.005
    return False


def score(fields, records, golds):
    by_field, cells = {}, []
    for stmt_id, rec in sorted(records.items()):
        g = golds.get(stmt_id) or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            want = g.get(name)
            stated = norm(want) is not None
            if not stated and norm(got) is None:
                v = "hit"                       # correct abstention -- see the module note
            elif norm(got) is None:
                v = "miss"
            elif not stated:
                v = "wrong"                     # invented a value the report never states
            elif equal(f, got, want):
                v = "hit"
            else:
                v = "wrong"
            cells.append({"doc": stmt_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": stated,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1
            if not stated and v == "hit":
                d["abstained"] += 1
            if not stated and v == "wrong":
                d["hallucinated"] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells
                 if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["stated"])
    refusal_cells = sum(1 for c in cells if not c["stated"])
    refusal_hit = sum(1 for c in cells if not c["stated"] and c["verdict"] == "hit")

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            # The subset of cells where the report states nothing and null is the right answer.
            "refusal_cells": refusal_cells,
            "refusal_accuracy": round(refusal_hit / refusal_cells, 4) if refusal_cells else None,
            "hallucinations": sum(1 for c in cells
                                  if not c["stated"] and c["verdict"] == "wrong"),
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields if f.get("type") == "enum"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def score_flags(flags, golds):
    """flags: {stmt_id: needs_review_or_None} from the run's own pure code.
    golds: {stmt_id: gold dict}. The TRUE flag is derived by running the same pure-code
    `compute()` over gold's own values, never separately typed.
    """
    tp = fp = tn = fn_ = not_applicable = 0
    rows = []
    for stmt_id, g in sorted(golds.items()):
        want = _compute(g)
        got = flags.get(stmt_id)
        if got is None:
            got = False
        if want and got:
            tp += 1
            v = "true_positive"
        elif want and not got:
            fn_ += 1
            v = "false_negative"
        elif not want and got:
            fp += 1
            v = "false_positive"
        else:
            tn += 1
            v = "true_negative"
        rows.append({"doc": stmt_id, "want": want, "got": got, "verdict": v})
    total_flagged = tp + fn_
    return {
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn_,
        "not_applicable": not_applicable,
        "recall": round(tp / total_flagged, 4) if total_flagged else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "rows": rows,
    }


def score_seriousness(records, golds):
    """The classification this kit exists to measure, pulled out of the field grid as its own
    figure so it can never be diluted by nine easy structured fields sitting beside it.

    Reported by register, because the corpus's whole design is that the confusable subset is
    where a keyword reader fails -- an aggregate that mixes the two hides exactly the gap.
    """
    out = {"overall": {"n": 0, "correct": 0},
           "by_register": {}, "wrong": []}
    for stmt_id, g in sorted(golds.items()):
        rec = records.get(stmt_id)
        if rec is None:
            continue
        got = norm((rec.get("is_serious") or {}).get("value"))
        want = norm(g.get("is_serious"))
        reg = g.get("_register", "unknown")
        d = out["by_register"].setdefault(reg, {"n": 0, "correct": 0})
        d["n"] += 1
        out["overall"]["n"] += 1
        if got == want:
            d["correct"] += 1
            out["overall"]["correct"] += 1
        else:
            out["wrong"].append({"doc": stmt_id, "got": got, "want": want, "register": reg,
                                 "criterion": g.get("_criterion"),
                                 "severity_word": g.get("narrative_severity_word")})
    for d in list(out["by_register"].values()) + [out["overall"]]:
        d["accuracy"] = round(d["correct"] / d["n"], 4) if d["n"] else None
    return out
