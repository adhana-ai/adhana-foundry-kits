"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Every field in this corpus is always stated -- there is no optional field and no refusal case,
unlike the sibling kits' deposit/bonus/EA fields. Every (file, field) cell is scored as
extraction only: hit / miss / wrong.

⚑ THE SAFETY-CRITICAL FIGURE IS A THIRD THING, SCORED SEPARATELY AGAIN: whether the run's own
PURE-CODE `needs_review` (computed from what the model extracted, across all three checks --
expired license, stale PSV, adverse action) agrees with the same computation run over gold's own
true values. See data/SOURCES.md.
"""
import re

from src.extract import compute as _compute


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def equal(field, got, want):
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    return g == w


def score(fields, records, golds):
    by_field, cells = {}, []
    for stmt_id, rec in sorted(records.items()):
        g = golds.get(stmt_id) or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            want = g.get(name)
            if norm(got) is None:
                v = "miss"
            elif equal(f, got, want):
                v = "hit"
            else:
                v = "wrong"
            cells.append({"doc": stmt_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": True,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"])

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": 0,
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
    """
    tp = fp = tn = fn_ = not_applicable = 0
    rows = []
    for stmt_id, g in sorted(golds.items()):
        want, want_reasons = _compute(g)
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
        rows.append({"doc": stmt_id, "want": want, "want_reasons": want_reasons, "got": got,
                    "verdict": v})
    total_flagged = tp + fn_
    return {
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn_,
        "not_applicable": not_applicable,
        "recall": round(tp / total_flagged, 4) if total_flagged else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "rows": rows,
    }
