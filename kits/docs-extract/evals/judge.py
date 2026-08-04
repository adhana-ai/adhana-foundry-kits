"""Score an extraction run. PURE CODE — there is no LLM judge in this kit, on purpose.

⚑ WHY NO JUDGE, WHEN UC001 HAS ONE.
UC001 grades free prose against a reference answer, where "did it say the same thing" genuinely
needs judgement and an LLM is a reasonable instrument for it. Here the gold is exact and the
answer is one value. A judge would add cost, latency and a second source of disagreement to a
comparison that `==` settles. The kit framework's claim is that the evaluation method is
PLUGGABLE; this is the first evidence for that claim rather than a second demonstration of the
same method.

⚑ THE TWO QUESTIONS, SCORED SEPARATELY — see build_corpus.py's `stated` map.
For each (document, field) cell:
  stated   -> EXTRACTION. Did it find the value that is in the document?
              hit / miss (returned nothing) / wrong (returned something else)
  !stated  -> REFUSAL.    The document does not state it. Did it correctly return nothing?
              abstained / HALLUCINATED

⚠︎ THESE MUST NEVER BE AVERAGED INTO ONE NUMBER. A model that invents a value for every unstated
field can post a strong extraction accuracy, and the single blended figure would go UP as it got
less trustworthy. `overall` below reports them side by side and refuses to combine them.
"""
import re


def norm(v):
    """Compare like a careful human, not like a database.

    Case, surrounding whitespace and trailing punctuation never carry meaning in these values.
    Everything else does — no stemming, no fuzzy distance, no substring credit. A judge that is
    generous in ways nobody can predict produces figures nobody can reproduce.
    """
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _num(v):
    m = re.search(r"-?\d+", str(v or ""))
    return m.group(0) if m else None


def equal(field, got, want):
    """Is `got` the same value as `want`, for this field's type?"""
    g, w = norm(got), norm(want)
    if g is None or w is None:
        return g == w
    if g == w:
        return True
    if field.get("type") == "integer":
        return _num(g) is not None and _num(g) == _num(w)
    # "18 Years" vs "18 years" vs "18" — the unit is noise when the field IS an age in years.
    if field["name"] == "minimum_age":
        return _num(g) is not None and _num(g) == _num(w)
    return False


def score_cell(field, got, want, stated):
    """One (document, field) cell -> a verdict string. See the module docstring for the taxonomy."""
    if not stated:
        return "abstained" if norm(got) is None else "hallucinated"
    if norm(got) is None:
        return "miss"
    return "hit" if equal(field, got, want) else "wrong"


def score(fields, records, golds):
    """records: {nct_id: {field: {value, span}}}   golds: {nct_id: gold dict incl. `stated`}"""
    by_field, cells = {}, []
    for nct, rec in sorted(records.items()):
        g = golds.get(nct) or {}
        stated = g.get("stated") or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            # nct_id has no `stated` entry (it keys the record) and is always in the header.
            st = stated.get(name, True) if name != "nct_id" else True
            v = score_cell(f, got, g.get(name), st)
            cells.append({"doc": nct, "field": name, "verdict": v,
                          "got": got, "want": g.get(name), "stated": st,
                          "span": bool((rec.get(name) or {}).get("span"))})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1

    ext_n = sum(1 for c in cells if c["stated"])
    ext_hit = sum(1 for c in cells if c["stated"] and c["verdict"] == "hit")
    ref_n = sum(1 for c in cells if not c["stated"])
    ref_ok = sum(1 for c in cells if not c["stated"] and c["verdict"] == "abstained")
    spanned = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong", "hallucinated"))

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            # Two rates, never one. See the docstring.
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": ref_n,
            "refusal_accuracy": round(ref_ok / ref_n, 4) if ref_n else None,
            "hallucinations": ref_n - ref_ok,
            # The guardrail figure: of every value returned, how many could be located in the
            # document. A value with no span is not necessarily wrong — it may be a paraphrase —
            # but it is a value a reader cannot check, and that is worth a number of its own.
            "values_returned": valued,
            "values_with_span": spanned,
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }
