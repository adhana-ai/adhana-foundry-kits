"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

THE TWO QUESTIONS, SCORED SEPARATELY, per (report, field) cell:
  stated   -> EXTRACTION. Did it find the value that is in the report?
              hit / miss (returned nothing) / wrong (returned something else)
  !stated  -> REFUSAL.    The report does not state it. Did it correctly return nothing?
              abstained / HALLUCINATED

Only `extraordinary_assumption_text` has a real not-stated case in this corpus --
`extraordinary_assumption_present` is always a real yes/no, never absent.

⚑ THE SAFETY-CRITICAL FIGURE IS A THIRD THING, SCORED SEPARATELY AGAIN: whether the run's own
PURE-CODE `needs_review` (computed from what the model extracted) agrees with the same
computation run over gold's own true values. See data/SOURCES.md.
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


def score_cell(field, got, want, stated):
    if not stated:
        return "abstained" if norm(got) is None else "hallucinated"
    if norm(got) is None:
        return "miss"
    return "hit" if equal(field, got, want) else "wrong"


def score(fields, records, golds):
    by_field, cells = {}, []
    for stmt_id, rec in sorted(records.items()):
        g = golds.get(stmt_id) or {}
        stated = g.get("stated") or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            st = stated.get(name, True)
            v = score_cell(f, got, g.get(name), st)
            cells.append({"doc": stmt_id, "field": name, "verdict": v,
                          "got": got, "want": g.get(name), "stated": st,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1

    ext_n = sum(1 for c in cells if c["stated"])
    ext_hit = sum(1 for c in cells if c["stated"] and c["verdict"] == "hit")
    ref_n = sum(1 for c in cells if not c["stated"])
    ref_ok = sum(1 for c in cells if not c["stated"] and c["verdict"] == "abstained")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells
                 if c["verdict"] in ("hit", "wrong", "hallucinated") and c["spannable"])

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": ref_n,
            "refusal_accuracy": round(ref_ok / ref_n, 4) if ref_n else None,
            "hallucinations": ref_n - ref_ok,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields if f.get("type") == "enum"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def score_flags(flags, golds):
    """flags: {stmt_id: needs_review_or_None} from the run's own pure code.
    golds: {stmt_id: gold dict}. The TRUE flag is derived by running the same pure-code
    `compute()` over gold's own values.

    `got is None` here means the model failed to return a parseable yes/no on
    extraordinary_assumption_present at all -- ALWAYS a real extraction failure in this corpus
    (the field is never legitimately absent, unlike the sibling kits' optional deposit/bonus
    fields), so every None here counts as a false_negative when gold's true flag is True, never
    as not_applicable.
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
