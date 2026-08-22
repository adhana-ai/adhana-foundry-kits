"""Score a pre-load check run. PURE CODE -- gold is exact and the answer is one value per cell, so
`==` (with light normalisation) settles it.

Three graders, scored separately and never folded together:

1. per-(sheet, field) exact match, the extraction grade;
2. the VERDICT, scored two ways at once. Four-way exact accuracy across accept / clean_then_load /
   refuse / undetermined, AND a binary confusion matrix on the only distinction that is safety-
   relevant: is this tank CLEAR TO LOAD AS-IS, or is it not. `not accept` is the positive class,
   so recall is "of every tank that must not be loaded as it stands, how many did the run stop".
   THIS IS THE HEADLINE. The expensive direction is a false negative -- a tank the matrix would
   have blocked that the run cleared -- and it is counted and named separately as
   `unsafe_release`;
3. a confusion matrix on the pure-code `needs_hold` flag against the same rule computed from
   GOLD's own values -- "is this the tank somebody has to act on today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the model's stated `verdict` disagrees with the
matrix re-run over the model's OWN extracted values. That needs no gold, so it is the one figure
here a forker can still compute on sheets nobody has labelled -- it is reported, and it is
deliberately not called a guardrail, because this kit's guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE MATRIX IS RIGHT. They grade whether the run applied the matrix
this kit ships. The matrix is illustrative and is not an authority; a run that scores 100 pct here
has agreed with `data/matrix.json`, which is a different and much smaller claim than being right
about a real tank.
"""
import re

from src import matrix as MX
from src.extract import compute as _compute
from src.extract import correct_verdict as _verdict_of


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
    """prior_cargo and two_back_cargo are the two legitimately-null fields in this corpus -- null
    exactly where the sheet says the prior cargo is not recorded, or that the tank was recertified
    and has no cargo before the prior one. Both are a `hit` when the model matches gold, never a
    `miss` by default the way a corpus with no nullable fields would treat any null. A cell is a
    `hit`, a `miss` (returned nothing where gold has a value) or `wrong` (returned something else).
    """
    by_field, cells = {}, []
    for check_id, rec in sorted(records.items()):
        g = golds.get(check_id) or {}
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
            cells.append({"doc": check_id, "field": name, "verdict": v, "got": got, "want": want,
                          "stated": want is not None,
                          "span": bool((rec.get(name) or {}).get("span")),
                          "spannable": (rec.get(name) or {}).get("spannable", True)})
            d = by_field.setdefault(name, {"hit": 0, "miss": 0, "wrong": 0})
            d[v] += 1

    ext_n = len(cells)
    ext_hit = sum(1 for c in cells if c["verdict"] == "hit")
    spanned = sum(1 for c in cells
                  if c["verdict"] in ("hit", "wrong") and c["spannable"] and c["span"])
    valued = sum(1 for c in cells if c["verdict"] in ("hit", "wrong") and c["spannable"]
                 and norm(c["got"]) is not None)
    hallucinated = sum(1 for c in cells
                       if c["verdict"] == "wrong" and not c["stated"])

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
            "non_spannable_fields": sorted({f["name"] for f in fields if f.get("type") == "enum"}),
            "span_rate": round(spanned / valued, 4) if valued else None,
        },
    }


def _matrix(rows, positive):
    """A confusion matrix over rows of {want, got}, with `positive` as the positive class.

    ⚠︎ A REPLY THAT DID NOT ANSWER IS NOT A NEGATIVE. Folding an unanswered row into "true
    negative" would let a model that answers nothing score as a careful one, so an unanswered row
    is counted on its own and never as a correct call -- which on a pre-load check is the whole
    difference between a tank nobody cleared and a tank somebody cleared.
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


def score_verdicts(records, flags, golds):
    """The matrix verdict and the hold flag, both scored against gold, plus the no-gold
    consistency diagnostic.

    records: {check_id: {field: {value,...}}} from the run.
    flags:   {check_id: needs_hold_or_None} from the run's own pure code.
    golds:   {check_id: gold dict}. Gold's verdict is re-derived here by the SAME matrix lookup the
             kit publishes, and gold's needs_hold by the SAME rule src/extract.py applies -- so
             neither truth this grades against is a separately-typed label that could drift from
             the code.
    """
    rows, blocked_rows, flag_rows = [], [], []
    confusion = {}
    inconsistent = 0
    caught = missed = 0
    unsafe_release = []
    over_block = []

    for check_id, g in sorted(golds.items()):
        want = _verdict_of(g)
        rec = records.get(check_id) or {}
        got = (rec.get("verdict") or {}).get("value")
        got = got if got in MX.VERDICTS else None

        rows.append({"doc": check_id, "want": want, "got": got,
                     "correct": (got is not None and got == want)})
        confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
        confusion[want][got or "unanswered"] += 1

        # ⚑ THE SAFETY-RELEVANT BINARY. Everything that is not `accept` means "do not load this
        # tank as it stands" -- clean it, refuse it, or find out what was in it. Collapsing the
        # four classes onto that one distinction is what makes a false negative nameable.
        want_blocked = "yes" if want != "accept" else "no"
        got_blocked = None if got is None else ("yes" if got != "accept" else "no")
        blocked_rows.append({"doc": check_id, "want": want_blocked, "got": got_blocked,
                             "verdict": None})
        if want_blocked == "yes" and got_blocked == "no":
            unsafe_release.append({"doc": check_id, "gold": want, "model": got})
        if want_blocked == "no" and got_blocked == "yes":
            over_block.append({"doc": check_id, "gold": want, "model": got})

        want_flag = _compute({"verdict": want, "load_status": g.get("load_status")})
        got_flag = flags.get(check_id)
        flag_rows.append({"doc": check_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict survive the matrix re-run over the reply's
        # own values? No gold is used here -- that is the whole point of reporting it.
        self_check = _verdict_of({k: (rec.get(k) or {}).get("value")
                                  for k in ("incoming_product", "incoming_grade", "prior_cargo",
                                            "two_back_cargo", "wash_certified_for")})
        if self_check is not None and got is not None and self_check != got:
            inconsistent += 1
            if got != want:
                caught += 1
        elif got != want:
            missed += 1

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    blocked = _matrix(blocked_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    n_must_block = sum(1 for r in blocked_rows if r["want"] == "yes")

    return {
        "verdict_accuracy": round(n_correct / n, 4),
        "verdict_correct": n_correct,
        "verdict_rows": n,
        "verdict_unanswered": n_unanswered,
        "confusion": confusion,
        "blocked": dict(blocked,
                        positive_class="yes (this tank must NOT be loaded as it stands)",
                        note="The four-way verdict collapsed onto the one distinction that is "
                             "safety-relevant. A false negative here is a tank the shipped matrix "
                             "would have stopped and the run cleared.",
                        rows=blocked_rows),
        "unsafe_release": unsafe_release,
        "unsafe_release_count": len(unsafe_release),
        "unsafe_release_rate_pct": round(100.0 * len(unsafe_release) / n_must_block, 2)
                                   if n_must_block else None,
        "over_block": over_block,
        "over_block_count": len(over_block),
        "hold_flag": dict(flag_matrix,
                          positive_class="yes (not clear-to-load and already loaded)",
                          note="needs_hold compares the run's own verdict and load_status against "
                               "the same rule run over GOLD's values. It is a business condition, "
                               "so it needs labels -- unlike the consistency diagnostic below, "
                               "which does not.",
                          rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "verdict_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-runs the matrix lookup over the "
                    "run's OWN extracted values and counts the replies whose stated verdict "
                    "disagrees with it. It uses no gold, so a forker can compute it on unlabelled "
                    "sheets -- but it is blind to a reply that misreads a cargo name or a "
                    "certificate and then reasons correctly from the misreading.",
        },
        "rows": rows,
    }
