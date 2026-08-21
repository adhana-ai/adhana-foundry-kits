"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

THE TWO QUESTIONS, SCORED SEPARATELY, per (stub, field) cell:
  stated   -> EXTRACTION. Did it find the value that is in the stub?
              hit / miss (returned nothing) / wrong (returned something else)
  !stated  -> REFUSAL.    The stub does not state it. Did it correctly return nothing?
              abstained / HALLUCINATED

⚠︎ THESE MUST NEVER BE AVERAGED INTO ONE NUMBER.

⚑ THE SAFETY-CRITICAL FIGURE IS A THIRD THING, SCORED SEPARATELY AGAIN: whether the run's own
PURE-CODE `needs_review` flag (computed from what the model extracted) agrees with the SAME
computation run over gold's own true values. A model that never excludes a bonus, or never flags
one, can still post a respectable extraction accuracy on the other nine fields -- this figure is
reported separately and never folded into it.
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
    """records: {stmt_id: {field: {value, span}}}   golds: {stmt_id: gold dict incl. `stated`}"""
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
    `compute()` over gold's own values -- never a separately-typed truth, so the two can never
    drift apart by a transcription error.

    `got is None` happens for two DIFFERENT reasons and they must not be folded together:
      - the stub genuinely has no bonus this year (gold's own ytd_bonus_pay is not stated
        either) -- there is nothing to flag, not a run failure. Excluded as not_applicable.
      - the model failed to extract ytd_bonus_pay on a stub that DOES have one -- the review
        this kit exists to trigger never fires. Counted as a false_negative when gold's true
        flag is True.
    """
    tp = fp = tn = fn_ = not_applicable = 0
    rows = []
    for stmt_id, g in sorted(golds.items()):
        _income, want = _compute(g)
        got = flags.get(stmt_id)
        if got is None:
            if not (g.get("stated") or {}).get("ytd_bonus_pay"):
                not_applicable += 1
                rows.append({"doc": stmt_id, "want": want, "got": None,
                             "verdict": "not_applicable"})
                continue
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
