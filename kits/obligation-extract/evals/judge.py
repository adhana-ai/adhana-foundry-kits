"""Score an obligation-worksheet run. PURE CODE -- gold is exact and every answer is one value, so
`==` (with light normalisation) settles it.

FOUR GRADERS, SCORED SEPARATELY AND NEVER FOLDED TOGETHER. The reason they are separate is that a
worksheet can fail in four different ways and three of them are invisible inside one accuracy
number:

1. IDENTIFICATION -- which lines reached the worksheet at all. Micro precision and recall over
   line codes, with the two directions named: a MISSED obligation (a real line left off) and a
   PHANTOM obligation (a line on the worksheet that is not one). Phantoms are broken down by which
   decoy produced them -- a struck line, a rate card, an item continuing under an earlier order
   form, or a code that appears nowhere in the pack at all.
2. THE SEPARATION CALL -- distinct / bundled / not_determined, on the lines BOTH sides list. Scored
   on matched lines only, deliberately: a call about a line the run never found is an
   identification failure, and counting it twice would let one mistake sink two graders.
3. THE DELIVERY PATTERN -- over_time / point_in_time / not_determined, same population.
4. DETERMINACY -- ⚑ THE HEADLINE. Of the calls the paperwork does NOT settle, how many did the run
   answer with a confident value anyway? That is `overconfident`, and it is the failure worth
   exposing on this shape of work: a call recorded as settled is a call nobody re-reads, so an
   over-confident worksheet quietly removes the reviewer it exists to serve. Its mirror,
   `overcautious` -- saying not_determined where the contract does settle it -- is counted and
   published too, because the two costs are different and do not net against each other.

And one diagnostic that is not a grade: how often a row's stated `separation`/`pattern` disagrees
with the rulebook re-run over that row's OWN extracted facts. That needs no gold, so it is the one
figure here a forker can compute on contracts nobody has labelled -- it is reported, and it is
deliberately not called a guardrail, because this kit's guardrail is the business flag below it.

⚠︎ NONE OF THESE GRADE WHETHER THE RULEBOOK IS RIGHT. They grade whether the run applied the
rulebook this kit ships. It is illustrative, it reproduces no accounting standard, and a run that
scores 100 pct here has agreed with `data/rulebook.json` -- a different and much smaller claim than
being right about a real contract. The determination is the controller's.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute
from src.extract import decide as _decide


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def code_norm(v):
    if v is None:
        return None
    s = re.sub(r"\s+", "", str(v)).upper()
    return s or None


def equal(got, want):
    return norm(got) == norm(want)


def _rows_of(rec):
    """{code: {field: value}} for one reply. A row with no usable code is kept under a synthetic
    key so it still counts as a phantom rather than vanishing -- a reply that invents a line and
    forgets to code it is worse than one that codes it wrongly, not better."""
    out = {}
    for i, row in enumerate(rec.get("obligations") or []):
        vals = {n: c.get("value") for n, c in row.items() if n != "_recomputed"}
        key = code_norm(vals.get("item_code")) or "__uncoded_%d" % i
        if key in out:
            key = "%s__dup_%d" % (key, i)
        out[key] = vals
    return out


# --------------------------------------------------------------------------------------------
# 1. identification
# --------------------------------------------------------------------------------------------

def score_identification(records, golds):
    """Which lines reached the worksheet. Micro over every gold line and every returned row.

    ⚑ A PHANTOM IS CLASSIFIED BY WHICH DECOY PRODUCED IT, not just counted. "It listed the struck
    line" and "it invented a code" are different defects with different fixes, and a single
    precision figure hides which one a run has.
    """
    per_doc = []
    tp = fp = fn_ = 0
    by_kind = {"withdrawn": 0, "rate_card": 0, "carryover": 0, "not_in_pack": 0}
    missed_rows, phantom_rows = [], []

    for cid, g in sorted(golds.items()):
        gold_codes = {code_norm(o["item_code"]) for o in g["obligations"]}
        decoys = {code_norm(d["item_code"]): d["kind"] for d in (g.get("decoys") or [])}
        got = _rows_of(records.get(cid) or {})
        got_codes = set(got)

        matched = gold_codes & got_codes
        missed = gold_codes - got_codes
        phantom = got_codes - gold_codes

        tp += len(matched)
        fn_ += len(missed)
        fp += len(phantom)
        for c in sorted(missed):
            missed_rows.append({"doc": cid, "item_code": c})
        for c in sorted(phantom):
            kind = decoys.get(c, "not_in_pack")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            phantom_rows.append({"doc": cid, "item_code": c, "kind": kind})

        per_doc.append({"doc": cid, "gold": len(gold_codes), "returned": len(got_codes),
                        "matched": len(matched), "missed": len(missed),
                        "phantom": len(phantom)})

    prec = round(tp / (tp + fp), 4) if (tp + fp) else None
    rec = round(tp / (tp + fn_), 4) if (tp + fn_) else None
    f1 = round(2 * prec * rec / (prec + rec), 4) if (prec and rec) else None
    return {
        "gold_lines": tp + fn_,
        "returned_lines": tp + fp,
        "matched": tp,
        "missed_obligation": fn_,
        "phantom_obligation": fp,
        "phantom_by_kind": by_kind,
        "precision": prec, "recall": rec, "f1": f1,
        "missed_rows": missed_rows,
        "phantom_rows": phantom_rows,
        "per_doc": per_doc,
        "note": "Scored over LINE CODES. A phantom is a line on the worksheet that the order form "
                "does not order -- a line struck by an amendment, a rate card, an item continuing "
                "under an earlier order form, or a code that is nowhere in the pack.",
    }


# --------------------------------------------------------------------------------------------
# 2. extraction cells
# --------------------------------------------------------------------------------------------

CELL_FIELDS = ("item_label", "item_type", "charge", "dependency", "timing",
               "separation", "pattern")


def score(fields, records, golds):
    """Per-(line, field) exact match over every GOLD line, plus one contract_id cell per pack.

    ⚑ THE DENOMINATOR IS GOLD'S LINES, NOT THE RUN'S. A gold line the run never returned scores as
    a `miss` on all seven of its cells rather than disappearing from the denominator, so a run
    cannot raise this number by returning less. That is the same trap `answered_pct` exists to
    catch in the sibling kits, one level lower down.

    ⚠︎ `hallucinations` MEANS SOMETHING SPECIFIC HERE. Every gold cell on this corpus has a value,
    so the sibling kits' definition -- a value returned where gold carries none -- would be
    structurally zero and would read as a certificate. It is counted instead as the non-null cells
    belonging to PHANTOM lines: facts asserted about a promise that does not exist.
    """
    by_field, cells = {}, []
    for cid, g in sorted(golds.items()):
        rec = records.get(cid) or {}
        got_rows = _rows_of(rec)

        want_cid = g.get("contract_id")
        got_cid = ((rec.get("contract") or {}).get("contract_id") or {}).get("value")
        v = "hit" if equal(got_cid, want_cid) else ("miss" if norm(got_cid) is None else "wrong")
        cells.append({"doc": cid, "item_code": None, "field": "contract_id", "verdict": v,
                      "got": got_cid, "want": want_cid, "stated": True,
                      "span": bool(((rec.get("contract") or {}).get("contract_id")
                                    or {}).get("span")),
                      "spannable": True, "phantom": False})
        d = by_field.setdefault("contract_id", {"hit": 0, "miss": 0, "wrong": 0})
        d[v] += 1

        spans = {}
        for row in (rec.get("obligations") or []):
            key = code_norm((row.get("item_code") or {}).get("value"))
            if key:
                spans[key] = {n: bool((c or {}).get("span")) for n, c in row.items()
                              if n != "_recomputed"}

        for o in g["obligations"]:
            key = code_norm(o["item_code"])
            row = got_rows.get(key)
            for name in CELL_FIELDS:
                want = o.get(name)
                got = (row or {}).get(name)
                if equal(got, want):
                    v = "hit"
                elif norm(got) is None:
                    v = "miss"
                else:
                    v = "wrong"
                cells.append({"doc": cid, "item_code": o["item_code"], "field": name,
                              "verdict": v, "got": got, "want": want, "stated": True,
                              "span": bool((spans.get(key) or {}).get(name)),
                              "spannable": name in ("item_label",), "phantom": False})
                d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
                d[v] += 1

    ident = score_identification(records, golds)
    phantom_keys = {(p["doc"], p["item_code"]) for p in ident["phantom_rows"]}
    hallucinated = 0
    for cid, g in sorted(golds.items()):
        for key, vals in _rows_of(records.get(cid) or {}).items():
            if (cid, key) in phantom_keys:
                hallucinated += sum(1 for n in CELL_FIELDS if norm(vals.get(n)) is not None)

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)

    return {
        "by_field": by_field,
        "cells": cells,
        "overall": {
            "extraction_cells": ext_n,
            "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
            "refusal_cells": 0,
            "refusal_accuracy": None,
            "hallucinations": hallucinated,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields["fields"]
                                            if f["name"] not in ("item_label", "item_code")}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


# --------------------------------------------------------------------------------------------
# 3 + 4. the two calls, and determinacy
# --------------------------------------------------------------------------------------------

CALLS = {"separation": RB.SEPARATIONS, "pattern": RB.PATTERNS}


def _confusion(rows):
    out = {}
    for r in rows:
        out.setdefault(r["want"], {}).setdefault(r["got"] or "unanswered", 0)
        out[r["want"]][r["got"] or "unanswered"] += 1
    return out


def score_calls(records, golds):
    """The separation call and the delivery pattern, on the lines BOTH sides list.

    ⚑ MATCHED LINES ONLY, AND SAYING SO IS HALF OF WHAT MAKES THE NUMBER HONEST. A line the run
    never returned has no call to score; it is already counted, once, as a missed obligation. The
    `scored` count beside every figure here is what a reader needs to see it is not the corpus.
    """
    out = {}
    det_rows = []
    for call, allowed in CALLS.items():
        rows = []
        for cid, g in sorted(golds.items()):
            got_rows = _rows_of(records.get(cid) or {})
            for o in g["obligations"]:
                key = code_norm(o["item_code"])
                if key not in got_rows:
                    continue                       # an identification failure, counted there
                got = got_rows[key].get(call)
                got = got if got in allowed else None
                rows.append({"doc": cid, "item_code": o["item_code"],
                             "want": o[call], "got": got,
                             "correct": got is not None and got == o[call]})
        n = len(rows)
        correct = sum(1 for r in rows if r["correct"])
        unanswered = sum(1 for r in rows if r["got"] is None)

        # ⚑ THE DETERMINACY SPLIT. Two directions, never netted:
        #   overconfident -- gold says the paperwork does not settle it, the run answered anyway;
        #   overcautious  -- gold says it IS settled, the run declined.
        gold_und = [r for r in rows if r["want"] == "not_determined"]
        gold_det = [r for r in rows if r["want"] != "not_determined"]
        overconfident = [r for r in gold_und if r["got"] in ("distinct", "bundled", "over_time",
                                                             "point_in_time")]
        overcautious = [r for r in gold_det if r["got"] == "not_determined"]
        nd_hit = sum(1 for r in gold_und if r["got"] == "not_determined")

        out[call] = {
            "scored": n,
            "correct": correct,
            "accuracy": round(correct / n, 4) if n else None,
            "unanswered": unanswered,
            "confusion": _confusion(rows),
            "not_determined_in_gold": len(gold_und),
            "not_determined_correct": nd_hit,
            "not_determined_recall": round(nd_hit / len(gold_und), 4) if gold_und else None,
            "overconfident": len(overconfident),
            "overconfident_rate_pct": (round(100.0 * len(overconfident) / len(gold_und), 2)
                                       if gold_und else None),
            "overcautious": len(overcautious),
            "overcautious_rate_pct": (round(100.0 * len(overcautious) / len(gold_det), 2)
                                      if gold_det else None),
            "overconfident_rows": overconfident[:40],
            "rows": rows,
        }
        det_rows.extend(rows)

    # The headline, across both calls at once: of every call this corpus's contracts do not settle,
    # how many did the run settle anyway.
    und = [r for r in det_rows if r["want"] == "not_determined"]
    conf = [r for r in und if r["got"] is not None and r["got"] != "not_determined"]
    det = [r for r in det_rows if r["want"] != "not_determined"]
    cautious = [r for r in det if r["got"] == "not_determined"]
    out["determinacy"] = {
        "calls_scored": len(det_rows),
        "not_determined_in_gold": len(und),
        "not_determined_correct": len(und) - len(conf) - sum(1 for r in und if r["got"] is None),
        "not_determined_recall": (round((len(und) - len(conf)
                                         - sum(1 for r in und if r["got"] is None)) / len(und), 4)
                                  if und else None),
        "overconfident": len(conf),
        "overconfident_rate_pct": round(100.0 * len(conf) / len(und), 2) if und else None,
        "overcautious": len(cautious),
        "overcautious_rate_pct": round(100.0 * len(cautious) / len(det), 2) if det else None,
        "note": "⚑ THE HEADLINE. `overconfident` is a call the paperwork does not settle, answered "
                "with a confident value anyway. On a reviewer's worksheet that is the expensive "
                "direction: a call recorded as settled is a call nobody re-reads. `overcautious` "
                "is the mirror and is published beside it because the two costs are different and "
                "do not net against each other.",
    }
    return out


# --------------------------------------------------------------------------------------------
# 5. the business flag, and the no-gold diagnostic
# --------------------------------------------------------------------------------------------

def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a run that returns nothing score as a careful one.
    """
    tp = fp = tn = fn_ = unanswered = 0
    for r in rows:
        want, got = r["want"], r["got"]
        if got not in ("yes", "no"):
            unanswered += 1
            r["verdict"] = "unanswered"
            continue
        if want == positive and got == positive:
            tp += 1
            r["verdict"] = "true_positive"
        elif want == positive:
            fn_ += 1
            r["verdict"] = "false_negative"
        elif got == positive:
            fp += 1
            r["verdict"] = "false_positive"
        else:
            tn += 1
            r["verdict"] = "true_negative"
    n = len(rows) or 1
    total_positive = sum(1 for r in rows if r["want"] == positive)
    return {
        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn_,
        "unanswered": unanswered,
        "not_applicable": 0,
        "accuracy": round((tp + tn) / n, 4),
        "recall": round(tp / total_positive, 4) if total_positive else None,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
    }


def score_flag(records, flags, golds):
    """`needs_drafting_review` against the same rule run over GOLD's own lines, plus the no-gold
    consistency diagnostic over the run's own facts."""
    flag_rows = []
    inconsistent = 0
    caught = missed = 0
    call_errors = 0

    for cid, g in sorted(golds.items()):
        want_flag = _compute(g["obligations"])
        got_flag = flags.get(cid)
        flag_rows.append({"doc": cid,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        gold_by_code = {code_norm(o["item_code"]): o for o in g["obligations"]}
        for key, vals in _rows_of(records.get(cid) or {}).items():
            self_check = _decide(vals)
            said = {"separation": vals.get("separation"), "pattern": vals.get("pattern")}
            bad = any(self_check[c] is not None and said[c] is not None
                      and self_check[c] != said[c] for c in CALLS)
            gold_row = gold_by_code.get(key)
            wrong = bool(gold_row) and any(said[c] != gold_row[c] for c in CALLS)
            if bad:
                inconsistent += 1
                if wrong:
                    caught += 1
            elif wrong:
                missed += 1
            if wrong:
                call_errors += 1

    m = _matrix(flag_rows, "yes")
    return {
        "review_flag": dict(m,
                            positive_class="yes (a PRICED line whose separation AND delivery "
                                           "pattern the paperwork settles neither of)",
                            note="needs_drafting_review compares the run's own lines against the "
                                 "same rule run over GOLD's. It is a business condition, so it "
                                 "needs labels -- unlike the consistency diagnostic below, which "
                                 "does not.",
                            rows=flag_rows),
        "consistency": {
            "rows_disagreeing_with_own_facts": inconsistent,
            "call_errors": call_errors,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the shipped rulebook over "
                    "each returned row's OWN charge/dependency/timing and counts the rows whose "
                    "stated calls disagree with it. It uses no gold, so a forker can compute it "
                    "on unlabelled contracts -- but it is blind to a row that misreads a clause "
                    "and then applies the rulebook correctly to the misreading, which on this "
                    "corpus is the commonest way to be wrong.",
        },
    }
