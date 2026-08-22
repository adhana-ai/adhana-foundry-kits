"""Score a reconciliation run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it. No LLM judge: the thing being graded is arithmetic, and
arithmetic is the one thing you should never ask a model to adjudicate.

Four graders, scored separately and never folded together:

1. per-(pack, field) exact match, the extraction grade -- which here includes the two fields the
   model had to COMPUTE rather than copy, `trail_hours` and `trail_cycles`;
2. `life_status` against gold's own arithmetic, both as five-class accuracy AND collapsed to the
   binary question a records desk actually asks: did the run CLEAR this component, or not?
   NOT-CLEARED IS THE POSITIVE CLASS. A component the records do not clear that gets called
   `within_limits` is the failure that matters on a pack headed back onto an aircraft, so recall is
   reported on "not cleared". THIS IS THE HEADLINE;
3. `tag_agrees` against the same comparison run over gold's figures -- DISAGREEMENT is the positive
   class, because an unreconciled tag is a discrepancy somebody has to raise;
4. a confusion matrix on the pure-code `escalate` flag -- "is this the pack somebody has to stop
   today". It is a business condition, so unlike a self-consistency check it genuinely needs
   labels, and saying so is half of what makes the number believable.

And two diagnostics that are not grades: how often the reply's stated `life_status` disagreed with
the same rule re-run over the reply's OWN reconstructed totals, and how often its stated
`tag_agrees` disagreed with the same comparison over its own figures. Neither needs gold, so they
are the two figures here a forker can still compute on packs nobody has labelled -- they are
reported, and they are deliberately not called guardrails, because this kit's guardrail is the
business flag above.

⚠︎ NOTHING HERE IS AN AIRWORTHINESS DETERMINATION. Every score below is about whether the kit read
and reconciled a record trail correctly. None of it is evidence that a component may be released to
service.
"""
import re

from src.extract import compute as _compute
from src.extract import life_status as _life
from src.extract import tag_agreement as _tag
from src.extract import LIFE_STATUSES


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
    """A cell is a `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned
    something else). No field in this corpus is legitimately null, so a null is always a miss.

    ⚠︎ THE SPAN DENOMINATOR EXCLUDES THE TWO COMPUTED TOTALS. `trail_hours` and `trail_cycles` are
    sums that appear nowhere in the pack -- see src/extract.py::spannable(). Counting them as
    unspanned would publish a span rate that punishes the kit for doing the arithmetic instead of
    copying a figure.
    """
    from src.extract import spannable as _spannable
    by_field, cells = {}, []
    for rec_id, rec in sorted(records.items()):
        g = golds.get(rec_id) or {}
        for f in fields:
            name = f["name"]
            got = (rec.get(name) or {}).get("value")
            want = g.get(name)
            if equal(f, got, want):
                v = "hit"
            elif norm(got) is None:
                v = "miss"
            else:
                v = "wrong"
            cells.append({"doc": rec_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": want is not None,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", _spannable(f))})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0,
                                           "abstained": 0, "hallucinated": 0})
            d[v] += 1

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
            "hallucinations": 0,
            "values_returned": valued,
            "values_with_span": spanned,
            "non_spannable_fields": sorted({f["name"] for f in fields if not _spannable(f)}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def _matrix(rows, positive, allowed):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding a null verdict into "true negative"
    would let a model that answers nothing score as a careful one, so an unanswered row is counted
    on its own and never as a correct call. On a safety-adjacent kit that distinction is the whole
    difference between "we checked and found nothing" and "we did not check".
    """
    tp = fp = tn = fn_ = unanswered = 0
    for r in rows:
        want, got = r["want"], r["got"]
        if got not in allowed:
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


def _cleared(status):
    """The binary collapse a records desk actually asks for. Anything that is not `within_limits`
    -- including `cannot_determine` -- is NOT cleared. An undeterminable pack is not a pass."""
    if status not in LIFE_STATUSES:
        return None
    return "cleared" if status == "within_limits" else "not_cleared"


def score_flags(records, flags, golds):
    """`life_status`, `tag_agrees` and the escalate flag, all scored against gold, plus the two
    no-gold consistency diagnostics.

    records: {rec_id: {field: {value,...}}} from the run.
    flags:   {rec_id: escalate_or_None} from the run's own pure code.
    golds:   {rec_id: gold dict}. Gold's life status is re-derived here by the SAME rule the kit
             publishes, gold's tag agreement by the SAME comparison, and gold's escalate flag by
             the SAME function src/extract.py applies -- so none of the three truths this grades
             against is a separately-typed label that could drift from the code.
    """
    rows, tag_rows, flag_rows, class_rows = [], [], [], []
    inconsistent_status = inconsistent_tag = 0
    caught = missed = 0

    for rec_id, g in sorted(golds.items()):
        want_status = _life(g.get("trail_hours"), g.get("trail_cycles"),
                            g.get("life_limit_hours"), g.get("life_limit_cycles"),
                            g.get("record_gap"))
        want_tag = _tag(g.get("tag_hours"), g.get("tag_cycles"),
                        g.get("trail_hours"), g.get("trail_cycles"))
        rec = records.get(rec_id) or {}
        got_status = (rec.get("life_status") or {}).get("value")
        got_tag = (rec.get("tag_agrees") or {}).get("value")

        # (a) the exact five-class call, and (b) the binary collapse that is the headline.
        class_rows.append({"doc": rec_id, "want": want_status, "got": got_status,
                           "verdict": "correct" if got_status == want_status else "wrong"})
        rows.append({"doc": rec_id, "want": _cleared(want_status), "got": _cleared(got_status),
                     "want_status": want_status, "got_status": got_status, "verdict": None,
                     "escalate": bool(flags.get(rec_id))})

        tag_rows.append({"doc": rec_id, "want": want_tag, "got": got_tag, "verdict": None})

        # The escalate flag, computed from gold's own values by the same rule the run applies to
        # its own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"life_status": want_status, "tag_agrees": want_tag,
                              "disposition_requested": g.get("disposition_requested")})
        got_flag = flags.get(rec_id)
        flag_rows.append({"doc": rec_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # Diagnostic 1: does the reply's stated life status survive the same rule re-run over the
        # reply's OWN reconstructed totals and limits? No gold is used -- that is the whole point.
        self_status = _life((rec.get("trail_hours") or {}).get("value"),
                            (rec.get("trail_cycles") or {}).get("value"),
                            (rec.get("life_limit_hours") or {}).get("value"),
                            (rec.get("life_limit_cycles") or {}).get("value"),
                            (rec.get("record_gap") or {}).get("value"))
        if self_status is not None and got_status in LIFE_STATUSES and self_status != got_status:
            inconsistent_status += 1
            if got_status != want_status:
                caught += 1
        elif got_status != want_status:
            missed += 1

        # Diagnostic 2: the same question for the tag comparison.
        self_tag = _tag((rec.get("tag_hours") or {}).get("value"),
                        (rec.get("tag_cycles") or {}).get("value"),
                        (rec.get("trail_hours") or {}).get("value"),
                        (rec.get("trail_cycles") or {}).get("value"))
        if self_tag is not None and got_tag in ("yes", "no") and self_tag != got_tag:
            inconsistent_tag += 1

    matrix = _matrix(rows, "not_cleared", ("cleared", "not_cleared"))
    tag_matrix = _matrix(tag_rows, "no", ("yes", "no"))
    flag_matrix = _matrix(flag_rows, "yes", ("yes", "no"))
    class_hits = sum(1 for r in class_rows if r["verdict"] == "correct")

    by_class = {}
    for r in class_rows:
        d = by_class.setdefault(r["want"], {"n": 0, "correct": 0, "answered_as": {}})
        d["n"] += 1
        d["correct"] += 1 if r["verdict"] == "correct" else 0
        if r["verdict"] != "correct":
            d["answered_as"][str(r["got"])] = d["answered_as"].get(str(r["got"]), 0) + 1

    return {
        "positive_class": "not_cleared (the record trail does not put this component inside both "
                          "published limits -- including the case where a records gap means it "
                          "cannot be determined at all)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "life_status_accuracy": round(class_hits / len(class_rows), 4) if class_rows else None,
        "life_status_correct": class_hits,
        "life_status_of": len(class_rows),
        "life_status_by_class": by_class,
        "life_status_rows": class_rows,
        "tag_agrees": dict(tag_matrix,
                           positive_class="no (the component's own tag does not match the total "
                                          "the record trail substantiates)",
                           rows=tag_rows),
        "escalate": dict(flag_matrix,
                         positive_class="yes (a discrepancy on a pack up for return to service)",
                         note="escalate compares the run's own life_status, tag_agrees and "
                              "disposition_requested against the same rule run over GOLD's "
                              "values. It is a business condition, so it needs labels -- unlike "
                              "the two consistency diagnostics below, which do not. It ESCALATES "
                              "and it never clears: a `no` means this rule found nothing to "
                              "raise, not that the component may fly.",
                         rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_life_arithmetic": inconsistent_status,
            "replies_disagreeing_with_own_tag_comparison": inconsistent_tag,
            "life_status_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the life-status rule and "
                    "the tag comparison over the run's OWN reconstructed figures and counts the "
                    "replies whose stated answer disagrees with them. It uses no gold, so a "
                    "forker can compute it on unlabelled packs -- but it is blind to the failure "
                    "that matters most here: a reply that sums the trail WRONG and then reasons "
                    "about its own wrong total perfectly is self-consistent and still wrong.",
        },
        "rows": rows,
    }
