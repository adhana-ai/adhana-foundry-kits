"""Score a label-restriction run. PURE CODE -- gold is exact and the answer is one value per cell,
so `==` (with light normalisation, and numeric comparison where the field is a number) settles it.

Four graders, scored separately and never folded together:

1. per-(case, field) exact match, the extraction grade;

2. the VERDICT, scored two ways at once. Four-way exact accuracy across within_label /
   wait_required / outside_label / insufficient_information, AND a binary confusion matrix on the
   only distinction that decides whether a sprayer goes out: MAY THIS APPLICATION BE MADE AS
   PROPOSED, OR MUST IT NOT. `not within_label` is the positive class, so recall is "of every
   proposal that must not go ahead as it stands, how many did the run stop". The expensive
   direction is a false negative -- a proposal the check set would have stopped that the run
   cleared -- and it is counted and named separately as `unsafe_clearance`;

3. ⚑ THE DECIDING RESTRICTION, which is this kit's own grader and the reason it exists. A verdict
   is one of four words; a deciding restriction is the actual answer to "so what do I do". A
   `wait_required` naming the pre-harvest interval on a case that turns on the re-entry interval is
   RIGHT ON THE FIRST GRADER AND USELESS IN THE FIELD -- the grower waits the wrong number of the
   wrong unit from the wrong date. That case is counted on its own as
   `right_verdict_wrong_reason`, never averaged into the verdict figure where it disappears;

4. a confusion matrix on the pure-code `needs_hold` flag against the same rule computed from
   GOLD's own values -- "is this the field somebody has to act on today". It is a business
   condition, so unlike a self-consistency check it genuinely needs labels, and saying so is half
   of what makes the number believable.

And one diagnostic that is not a grade: how often the reply's stated verdict or deciding
restriction disagrees with the check set re-walked over the reply's OWN extracted values. That
needs no gold, so it is the one figure here a forker can still compute on cases nobody has
labelled -- it is reported, and it is deliberately not called a guardrail, because this kit's
guardrail is the business flag above.

⚠︎ NONE OF THESE GRADE WHETHER THE CHECK SET IS RIGHT. They grade whether the run walked the check
set this kit ships. That set is illustrative and is not an authority; a run that scores 100 pct
here has agreed with `data/checks.json`, which is a different and much smaller claim than being
right about a real label.
"""
import re

from src import checks as CK
from src.extract import compute as _compute
from src.extract import correct_restriction as _restriction_of
from src.extract import correct_verdict as _verdict_of

NUMERIC_FIELDS = set()


def norm(v):
    if v is None:
        return None
    s = str(v).strip().strip(".,;:").strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower() or None


def _as_number(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    head = s.split()[0].rstrip(",")
    try:
        return float(head)
    except ValueError:
        return None


def equal(field, got, want):
    """⚑ NUMERIC FIELDS COMPARE AS NUMBERS, AND THAT IS A JUDGEMENT THIS FILE MAKES ON PURPOSE.
    A reply that returns `3` where gold holds `3.0`, or `2.5 L/ha` where gold holds `2.5`, has read
    the page correctly and formatted it differently. Scoring that as a misreading would publish a
    JSON serialisation difference as a model failure -- and this kit has fourteen numeric fields,
    so it would publish it fourteen times per case. String fields are still exact after trimming.
    """
    if (field or {}).get("type") == "number":
        a, b = _as_number(got), _as_number(want)
        if a is None or b is None:
            return a is None and b is None
        return abs(a - b) < 1e-9
    return norm(got) == norm(want)


def score(fields, records, golds):
    """Five fields are legitimately null in this corpus -- three label intervals the extract does
    not state, the days-since-last-application of a crop with no application this season, and the
    days-to-harvest a proposal omits. Each null is a STATED fact with its own sentence on the page,
    so a null is a `hit` when gold agrees, never a `miss` by default. A cell is a `hit`, a `miss`
    (returned nothing where gold has a value) or `wrong` (returned something else).
    """
    by_field, cells = {}, []
    for case_id, rec in sorted(records.items()):
        g = golds.get(case_id) or {}
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
            cells.append({"doc": case_id, "field": name, "verdict": v, "got": got, "want": want,
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
    hallucinated = sum(1 for c in cells if c["verdict"] == "wrong" and not c["stated"])

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
    is counted on its own and never as a correct call -- which on a label check is the whole
    difference between an application nobody cleared and one somebody cleared.
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
    """The verdict, the deciding restriction and the hold flag, all scored against gold, plus the
    no-gold consistency diagnostic.

    records: {case_id: {field: {value,...}}} from the run.
    flags:   {case_id: needs_hold_or_None} from the run's own pure code.
    golds:   {case_id: gold dict}. Gold's verdict and deciding restriction are BOTH re-derived here
             by the same walk the kit publishes, and gold's needs_hold by the same rule
             src/extract.py applies -- so no truth this grades against is a separately-typed label
             that could drift from the code.
    """
    rows, blocked_rows, flag_rows, restriction_rows = [], [], [], []
    confusion = {}
    restriction_confusion = {}
    inconsistent = 0
    caught = missed = 0
    unsafe_clearance = []
    over_block = []
    right_verdict_wrong_reason = []

    for case_id, g in sorted(golds.items()):
        want = _verdict_of(g)
        want_restriction = _restriction_of(g)
        rec = records.get(case_id) or {}
        got = (rec.get("verdict") or {}).get("value")
        got = got if got in CK.VERDICTS else None
        got_restriction = (rec.get("deciding_restriction") or {}).get("value")
        got_restriction = got_restriction if got_restriction in CK.RESTRICTIONS else None

        verdict_ok = (got is not None and got == want)
        restriction_ok = (got_restriction is not None and got_restriction == want_restriction)

        rows.append({"doc": case_id, "want": want, "got": got, "correct": verdict_ok})
        confusion.setdefault(want, {}).setdefault(got or "unanswered", 0)
        confusion[want][got or "unanswered"] += 1

        restriction_rows.append({"doc": case_id, "want": want_restriction, "got": got_restriction,
                                 "correct": restriction_ok, "verdict_correct": verdict_ok})
        restriction_confusion.setdefault(want_restriction, {}).setdefault(
            got_restriction or "unanswered", 0)
        restriction_confusion[want_restriction][got_restriction or "unanswered"] += 1

        # ⚑ THE NUMBER THIS KIT EXISTS TO PUBLISH. The verdict is right and the restriction it is
        # attributed to is not -- a right answer nobody can act on correctly. Counted only where
        # there IS a restriction to name, so a `within_label` case (gold `none`) can never land
        # here by returning nothing.
        if verdict_ok and want_restriction != CK.NO_RESTRICTION and not restriction_ok:
            right_verdict_wrong_reason.append({"doc": case_id, "verdict": want,
                                               "gold_restriction": want_restriction,
                                               "model_restriction": got_restriction})

        # ⚑ THE FIELD-RELEVANT BINARY. Everything that is not `within_label` means "do not make
        # this application as it stands" -- change it, wait, or find out what the label says.
        # Collapsing the four classes onto that one distinction is what makes a false negative
        # nameable.
        want_go = "yes" if want != "within_label" else "no"
        got_go = None if got is None else ("yes" if got != "within_label" else "no")
        blocked_rows.append({"doc": case_id, "want": want_go, "got": got_go, "verdict": None})
        if want_go == "yes" and got_go == "no":
            unsafe_clearance.append({"doc": case_id, "gold": want, "model": got})
        if want_go == "no" and got_go == "yes":
            over_block.append({"doc": case_id, "gold": want, "model": got})

        want_flag = _compute({"verdict": want, "application_status": g.get("application_status")})
        got_flag = flags.get(case_id)
        flag_rows.append({"doc": case_id,
                          "want": None if want_flag is None else ("yes" if want_flag else "no"),
                          "got": None if got_flag is None else ("yes" if got_flag else "no"),
                          "verdict": None})

        # The diagnostic: does the reply's own verdict AND deciding restriction survive the check
        # set re-walked over the reply's own values? No gold is used here -- that is the whole
        # point of reporting it.
        own = {k: (rec.get(k) or {}).get("value") for k in _SELF_FIELDS}
        self_v = _verdict_of(own)
        self_r = _restriction_of(own)
        disagrees = ((self_v is not None and got is not None and self_v != got)
                     or (self_r is not None and got_restriction is not None
                         and self_r != got_restriction))
        wrong = (not verdict_ok) or (not restriction_ok)
        if disagrees:
            inconsistent += 1
            if wrong:
                caught += 1
        elif wrong:
            missed += 1

    n = len(rows) or 1
    n_correct = sum(1 for r in rows if r["correct"])
    n_unanswered = sum(1 for r in rows if r["got"] is None)
    n_restriction_correct = sum(1 for r in restriction_rows if r["correct"])
    blocked = _matrix(blocked_rows, "yes")
    flag_matrix = _matrix(flag_rows, "yes")
    n_must_stop = sum(1 for r in blocked_rows if r["want"] == "yes")
    n_nameable = sum(1 for r in restriction_rows if r["want"] != CK.NO_RESTRICTION)

    return {
        "verdict_accuracy": round(n_correct / n, 4),
        "verdict_correct": n_correct,
        "verdict_rows": n,
        "verdict_unanswered": n_unanswered,
        "confusion": confusion,
        "restriction_accuracy": round(n_restriction_correct / n, 4),
        "restriction_correct": n_restriction_correct,
        "restriction_rows": n,
        "restriction_confusion": restriction_confusion,
        "restriction_rows_detail": restriction_rows,
        "right_verdict_wrong_reason": right_verdict_wrong_reason,
        "right_verdict_wrong_reason_count": len(right_verdict_wrong_reason),
        "right_verdict_wrong_reason_rate_pct": (
            round(100.0 * len(right_verdict_wrong_reason) / n_nameable, 2) if n_nameable else None),
        "nameable_rows": n_nameable,
        "blocked": dict(blocked,
                        positive_class="yes (this application must NOT be made as proposed)",
                        note="The four-way verdict collapsed onto the one distinction that decides "
                             "whether a sprayer goes out. A false negative here is a proposal the "
                             "shipped check set would have stopped and the run cleared.",
                        rows=blocked_rows),
        "unsafe_clearance": unsafe_clearance,
        "unsafe_clearance_count": len(unsafe_clearance),
        # ⚠︎ THE DENOMINATOR IS GOLD'S OWN COUNT, NOT THE MATRIX'S TP+FN. Those two differ exactly
        # when a reply did not answer: an unanswered row is neither a stop nor a clearance, so it
        # leaves the matrix's cells and would silently shrink the denominator a rate is quoted
        # against. A run that answers nothing would then report "0 unsafe clearances of 0", which
        # reads as a clean sheet and is the opposite of one.
        "must_stop_rows": n_must_stop,
        "unsafe_clearance_rate_pct": round(100.0 * len(unsafe_clearance) / n_must_stop, 2)
                                     if n_must_stop else None,
        "over_block": over_block,
        "over_block_count": len(over_block),
        "hold_flag": dict(flag_matrix,
                          positive_class="yes (not inside the label and already applied)",
                          note="needs_hold compares the run's own verdict and application_status "
                               "against the same rule run over GOLD's values. It is a business "
                               "condition, so it needs labels -- unlike the consistency diagnostic "
                               "below, which does not.",
                          rows=flag_rows),
        "consistency": {
            "replies_disagreeing_with_own_values": inconsistent,
            "answer_errors": caught + missed,
            "errors_visible_without_gold": caught,
            "errors_invisible_without_gold": missed,
            "note": "A DIAGNOSTIC, NOT THIS KIT'S GUARDRAIL. It re-walks data/checks.json over the "
                    "run's OWN extracted values and counts the replies whose stated verdict or "
                    "deciding restriction disagrees with it. It uses no gold, so a forker can "
                    "compute it on unlabelled cases -- but it is blind to a reply that misreads a "
                    "number and then walks the checks correctly from the misreading.",
        },
        "rows": rows,
    }


# The twenty values the check set actually reads. Named here rather than "every field" so that a
# reply mangling a decoy -- the note, the previous season's count -- cannot make the diagnostic
# fire on a case where nothing that decides anything moved.
_SELF_FIELDS = tuple(sorted(
    {c["label_field"] for c in CK.CHECKS} | {c["proposal_field"] for c in CK.CHECKS}
    | {clause["field"] for c in CK.CHECKS for clause in (c.get("skip_when") or [])}))
