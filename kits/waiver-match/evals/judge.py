"""Score an extraction run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Four graders, scored separately and never folded together:

1. per-(package, field) exact match, the extraction grade -- the REFERENCE standard for field
   values;
2. a confusion matrix on whether the package has ANY uncovered party, against gold's own count.
   A GAP IS THE POSITIVE CLASS: a package with an uncovered party that gets called complete is
   the failure a payment desk actually pays for, so recall is reported on "gap". THIS IS THE
   HEADLINE -- whether the coverage picture is complete is the whole question the kit asks;
3. GAP ATTRIBUTION, scored only on the packages that really have a gap: did the run name the
   right party AND the right reason? A package-level yes/no hides the difference between "found
   the gap" and "found a gap", and on a package with four parties and five possible reasons that
   difference is the entire value of the thing;
4. a confusion matrix on the pure-code `needs_hold` flag against the same flag computed from
   GOLD's own values -- "is this the package somebody has to stop today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the reply disagreed with ITSELF -- named a
party while reporting zero uncovered, reported a reason of 'none' while counting one, or named a
party the package does not list. That needs no gold, so it is the one figure here a forker can
still compute on unlabelled packages -- it is reported, and it is deliberately not called a
guardrail, because this kit's guardrail is the business flag above.
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
    """⚠︎ `str(v or "")` IS WRONG HERE AND THIS KIT CAUGHT IT ON ITS CALIBRATION RUN. The value
    that matters most in this corpus is `parties_uncovered`, and its most common correct answer is
    0 -- which `v or ""` turns into the empty string, so every fully-covered package scored as
    "did not answer". The exact-count figure read 1 of 3 while the extraction grade read 33 of 33
    on the same three replies, which is the contradiction that surfaced it. Test for None."""
    if v is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(v).replace(",", ""))
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
    """`first_gap_party` is legitimately null on every fully-covered package and stated on every
    other one -- both are a `hit` when the model matches gold, never a `miss` by default the way
    a corpus with no nullable fields would treat any null. A cell is a `hit`, a `miss` (returned
    nothing where gold has a value) or `wrong` (returned something else)."""
    from src.extract import spannable as _spannable

    by_field, cells = {}, []
    for pkg_id, rec in sorted(records.items()):
        g = golds.get(pkg_id) or {}
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
            cells.append({"doc": pkg_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": want is not None,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
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


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding a null verdict into "true negative"
    would let a model that answers nothing score as a careful one, so an unanswered row is counted
    on its own and never as a correct call.
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


def _yesno(n):
    """"yes" when a count says there is a gap, "no" when it says there is not, None when the
    reply did not carry a usable count."""
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        return None
    return "yes" if n > 0 else "no"


def score_flags(records, flags, checks, golds):
    """The coverage verdict, the gap attribution and the hold flag, all scored against gold, plus
    the no-gold self-consistency diagnostic.

    records: {pkg_id: {field: {value,...}}} from the run.
    flags:   {pkg_id: needs_hold_or_None} from the run's own pure code.
    checks:  {pkg_id: self_check dict} from the run's own pure code -- no gold involved.
    golds:   {pkg_id: gold dict}. Gold's needs_hold is re-derived here by the SAME rule
             src/extract.py applies to the run's own values, so the truth this grades against is
             not a separately-typed label that could drift from the code.

    Positive class for the coverage matrix is "yes" -- at least one party on this package is not
    covered. Recall is therefore "of every package that really has a gap, how many did the run
    say has one".
    """
    rows, flag_rows, attrib = [], [], []
    reason_confusion = {}
    inconsistent = caught = missed = 0
    invented_party = 0

    for pkg_id, g in sorted(golds.items()):
        rec = records.get(pkg_id) or {}
        got_n = (rec.get("parties_uncovered") or {}).get("value")
        got_party = (rec.get("first_gap_party") or {}).get("value")
        got_reason = (rec.get("first_gap_reason") or {}).get("value")

        want = "yes" if (g.get("parties_uncovered") or 0) > 0 else "no"
        got = _yesno(got_n)
        rows.append({"doc": pkg_id, "want": want, "got": got, "verdict": None,
                     "want_count": g.get("parties_uncovered"), "got_count": got_n})

        # The hold flag, computed from gold's own values by the same rule the run applies to its
        # own. `compute` returns a bool; the matrix reads yes/no, so it is spelled that way.
        want_flag = _compute({"parties_uncovered": g.get("parties_uncovered"),
                              "release_status": g.get("release_status")})
        got_flag = flags.get(pkg_id)
        flag_rows.append({"doc": pkg_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # ⚑ ATTRIBUTION IS SCORED ONLY WHERE THERE IS SOMETHING TO ATTRIBUTE. A package with no
        # gap has no right answer for "which party and why", so scoring it here would pad the
        # denominator with rows nobody can get wrong.
        if want == "yes":
            party_ok = norm(got_party) == norm(g.get("first_gap_party"))
            reason_ok = norm(got_reason) == norm(g.get("first_gap_reason"))
            attrib.append({"doc": pkg_id, "want_party": g.get("first_gap_party"),
                           "got_party": got_party, "party_ok": party_ok,
                           "want_reason": g.get("first_gap_reason"), "got_reason": got_reason,
                           "reason_ok": reason_ok, "both_ok": party_ok and reason_ok})
            if not reason_ok:
                key = "%s -> %s" % (g.get("first_gap_reason"), got_reason)
                reason_confusion[key] = reason_confusion.get(key, 0) + 1

        # The diagnostic: does the reply agree with itself, with no gold involved at all?
        chk = checks.get(pkg_id) or {}
        bad = [k for k in ("party_agrees", "reason_agrees", "party_exists")
               if chk.get(k) is False]
        if chk.get("party_exists") is False:
            invented_party += 1
        if bad:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    matrix = _matrix(rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    n_attrib = len(attrib)
    both = sum(1 for a in attrib if a["both_ok"])
    party_hits = sum(1 for a in attrib if a["party_ok"])
    reason_hits = sum(1 for a in attrib if a["reason_ok"])
    exact_count = sum(1 for r in rows
                      if r["got_count"] is not None
                      and _num(r["got_count"]) == float(r["want_count"] or 0))

    return {
        "positive_class": "yes (at least one party on this package is not covered by a waiver)",
        "true_positive": matrix["true_positive"], "false_positive": matrix["false_positive"],
        "true_negative": matrix["true_negative"], "false_negative": matrix["false_negative"],
        "unanswered": matrix["unanswered"], "not_applicable": 0,
        "accuracy": matrix["accuracy"], "recall": matrix["recall"],
        "precision": matrix["precision"],
        "count_exact": exact_count,
        "count_exact_rate": round(exact_count / len(rows), 4) if rows else None,
        "attribution": {
            "scored_on": n_attrib,
            "note": "Scored only on the packages gold says really have a gap -- a fully covered "
                    "package has no party and no reason to attribute, and padding the denominator "
                    "with rows nobody can get wrong would make this look better than it is.",
            "party_correct": party_hits,
            "reason_correct": reason_hits,
            "both_correct": both,
            "both_correct_rate": round(both / n_attrib, 4) if n_attrib else None,
            "party_correct_rate": round(party_hits / n_attrib, 4) if n_attrib else None,
            "reason_correct_rate": round(reason_hits / n_attrib, 4) if n_attrib else None,
            "reason_confusion": dict(sorted(reason_confusion.items(),
                                            key=lambda kv: -kv[1])),
            "rows": attrib,
        },
        "hold_flag": dict(flag_matrix, positive_class="yes (a gap, and scheduled for release)",
                          note="needs_hold compares the run's own parties_uncovered and "
                               "release_status against the same two-value rule run over GOLD's "
                               "values. It is a business condition, so it needs labels -- unlike "
                               "the extraction grade, which does too, and unlike the consistency "
                               "diagnostic below, which does not.",
                          rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_themselves": inconsistent,
            "replies_naming_a_party_not_in_the_package": invented_party,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. src/extract.py::self_check asks "
                    "three questions of the reply alone: is a party named exactly when the count "
                    "is non-zero, is the reason 'none' exactly when the count is zero, and does "
                    "the package actually list the party named. It uses no gold, so a forker can "
                    "compute it on unlabelled packages -- but it is blind to a reply that applies "
                    "the coverage rule wrongly and then reports that wrong answer consistently.",
        },
        "rows": rows,
    }
