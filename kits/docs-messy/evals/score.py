"""One scorer, used by the free floor and the model alike.

⚑ BOTH HALVES SCORE THROUGH THIS FILE, DELIBERATELY. The whole claim of this kit is a COMPARISON —
rules against model, clean against messy — and a comparison whose two sides are scored by two
pieces of code is not a comparison, it is two numbers next to each other. If the normalisation is
generous, it is generous to both.

THE TWO POPULATIONS, AND WHY THEY ARE NEVER AVERAGED TOGETHER:

  extraction cells   the gold answer is a value. Did we read it correctly?
  refusal cells      the gold answer is NOT STATED. Did we correctly decline to invent one?

Averaging them produces a single flattering number that hides the expensive failure. Reading a
total wrongly is a mistake; inventing a purchase-order number that was never on the page is a
different and worse one, and on a damaged page it is the failure that grows.
"""
import json
import os
import re


def load_gold(root):
    rows = []
    with open(os.path.join(root, "data", "gold.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_fields(root):
    with open(os.path.join(root, "data", "fields.json"), encoding="utf-8") as f:
        return [x["key"] for x in json.load(f)["fields"]]


def norm(key, v):
    """Normalise a value for comparison. Applied to gold and prediction identically."""
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip().strip(".,:;|~^")
    if s == "" or s.lower() in ("not stated", "none", "null", "n/a", "unknown", "-"):
        return None
    if key == "total_amount":
        s = s.replace(",", "").replace(" ", "")
        m = re.search(r"\d+\.\d{2}", s)
        return m.group(0) if m else s
    if key == "currency":
        return s.upper()[:3]
    if key in ("doc_number", "reference"):
        return s.upper().replace(" ", "")
    return s.lower()


def score_all(gold_rows, preds, fields):
    """preds: {doc_id: {field: value}}. Returns the `scores` block plus per-field detail."""
    ext_tot = ext_ok = ref_tot = ref_ok = halluc = returned = 0
    by_field = {}
    cells = []
    for row in gold_rows:
        pred = preds.get(row["doc_id"]) or {}
        for f in fields:
            g = norm(f, row["gold"].get(f))
            p = norm(f, pred.get(f))
            bf = by_field.setdefault(f, {"stated": 0, "correct": 0,
                                         "not_stated": 0, "declined": 0, "invented": 0})
            if p is not None:
                returned += 1
            if g is None:
                ref_tot += 1
                bf["not_stated"] += 1
                if p is None:
                    ref_ok += 1
                    bf["declined"] += 1
                else:
                    halluc += 1
                    bf["invented"] += 1
            else:
                ext_tot += 1
                bf["stated"] += 1
                if p == g:
                    ext_ok += 1
                    bf["correct"] += 1
            cells.append({"doc_id": row["doc_id"], "field": f, "gold": g, "pred": p,
                          "ok": (p == g)})
    return {
        "scores": {
            # ⚑ EVERY RATE SHIPS WITH ITS DENOMINATOR, HEALTHY RUNS INCLUDED. A guard that only
            # appears when something is wrong is a guard nobody learns to read — and a refusal rate
            # over 20 cells is a different claim from the same rate over 340.
            "extraction_cells": ext_tot,
            "extraction_accuracy": round(ext_ok / ext_tot, 4) if ext_tot else None,
            "refusal_cells": ref_tot,
            "refusal_accuracy": round(ref_ok / ref_tot, 4) if ref_tot else None,
            "hallucinations": halluc,
            "values_returned": returned,
        },
        "by_field": by_field,
        "cells": cells,
    }
