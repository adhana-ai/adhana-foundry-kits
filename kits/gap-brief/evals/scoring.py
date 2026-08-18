"""Score a set of drafted briefs against gold. Pure code, shared by evals/baseline.py and
evals/run.py so the free floor and the real run are graded by the identical function -- a baseline
and a model scored by two different scorers cannot be compared honestly. Same discipline
param-drift's evals/scoring.py and data-reconcile's evals/scoring.py both state for their own
scorers.

Three axes, per src/rubric.py's RUBRIC_AXES, plus one guardrail metric reported on its own:

    gap_completeness         recall/precision of the ITEM SET the brief covers, against the
                             material gaps it was actually handed.
    cause_tag_agreement      for items both gold and the brief cover, does the cause match --
                             split by whether gold's own cause was 'unknown' or traceable.
    narrative_faithfulness   does every quantified claim in the narrative trace to a number
                             actually present in the packed gap list.
    fabricated_cause         (guardrail, not an axis) a non-'unknown' cause whose citations are
                             not both real, item-relevant lines from that cycle's own notes.

⚑ A CITATION MUST BE BOTH REAL AND RELEVANT, NOT MERELY REAL. Every planted cause-note line in
this corpus opens with "<item_label>: ..." (see tools/build_corpus.py), so a citation that is a
genuine substring of the notes log but does not name the item it is cited for is citing someone
else's evidence -- caught here, not folded into the plain substring check data-reconcile's
_citation_is_real uses, because that check alone would pass a real-but-wrong-item citation.
"""
import re
from collections import Counter

NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _norm(s):
    return " ".join((s or "").split()).lower()


def citation_is_real(citation, notes_text):
    if not citation:
        return False
    return _norm(citation) in _norm(notes_text)


def citation_is_relevant(citation, item_label):
    if not citation or not item_label:
        return False
    return _norm(item_label) in _norm(citation)


def _extract_numbers(text):
    out = []
    if not text:
        return out
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        is_pct = tok.endswith("%")
        raw = tok[:-1] if is_pct else tok
        raw = raw.lstrip("$").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if val == 0:
            continue
        out.append((val, is_pct))
    return out


def _allowed_pool(packed):
    """The numbers a faithful narrative is allowed to state: every dollar figure and percentage
    in the packed gap list, the count of gaps, and any digit run in the cycle's own metadata
    (period, cycle_id) that the model was also handed as input.

    ⚑ THE PERIOD/CYCLE_ID CARVE-OUT WAS ADDED AFTER READING r001-gap-brief's OWN RESULT, NOT
    BEFORE. Two of 40 real replies restated the cycle's period ("2026-Q1") in the narrative, and a
    first version of this pool -- built from the gap list alone -- flagged "2026" as an unmatched,
    seemingly-invented number. It is not invented; it is the `period` field the model was already
    given as context. Widening the pool to cover what the model was actually handed is a scorer
    correctness fix, not a loosening of the guardrail: a narrative number still fails here the
    moment it is not traceable to ANYTHING in the packed input, which is the property this check
    exists to guarantee.
    """
    dollars, pcts = set(), set()
    for g in packed["gaps"]:
        dollars.add(round(g["delta_usd"]))
        if g.get("delta_pct") is not None:
            pcts.add(round(g["delta_pct"], 1))
        for v in g["views"].values():
            if v is not None:
                dollars.add(round(v))
    dollars.add(len(packed["gaps"]))          # "N gaps" is a legitimate narrative claim
    for field in ("period", "cycle_id", "business_unit"):
        for tok in re.findall(r"\d+", str(packed.get(field, ""))):
            dollars.add(int(tok))
    return dollars, pcts


def _amount_matches(val, is_pct, dollars, pcts):
    pool = pcts if is_pct else dollars
    for allowed in pool:
        tol = 1.5 if is_pct else max(50.0, 0.02 * abs(allowed))
        if abs(val - allowed) <= tol:
            return True
    return False


def narrative_faithfulness(narrative, packed):
    """Returns (faithful: bool or None, unmatched: [(val, is_pct), ...]). None means no narrative
    was produced at all -- a distinct, worse state than an unfaithful one, never folded in as a
    pass."""
    if not narrative:
        return None, []
    dollars, pcts = _allowed_pool(packed)
    nums = _extract_numbers(narrative)
    unmatched = [n for n in nums if not _amount_matches(n[0], n[1], dollars, pcts)]
    return (len(unmatched) == 0), unmatched


def score(records, gold, notes_by_id):
    """`records` are evals/run.py's per-cycle output dicts (record["answer"]["gaps"/"narrative"],
    record["packed"]). `gold` and `notes_by_id` are keyed by cycle_id."""
    tp_total = fp_total = fn_total = 0
    cause_correct = cause_total = 0
    unknown_correct = unknown_total = 0
    traceable_correct = traceable_total = 0
    fabricated = 0
    fabricated_examples = []
    missing_view_correct = missing_view_total = 0
    narratives_faithful = narratives_scored = narratives_missing = 0
    per_cycle = []

    for rec in records:
        cid = rec["cycle_id"]
        g = gold.get(cid)
        if not g:
            continue
        notes_text = "\n".join(notes_by_id.get(cid, []))
        gold_material = {gg["item_id"]: gg for gg in g["gaps"] if gg["material"]}
        model_gaps = {mg["item_id"]: mg for mg in rec["answer"]["gaps"] if mg.get("item_id")}

        gold_ids = set(gold_material)
        model_ids = set(model_gaps)
        tp = gold_ids & model_ids
        fp = model_ids - gold_ids
        fn = gold_ids - model_ids
        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        cyc_cause_correct = 0
        cyc_fabricated = 0
        for item_id in tp:
            gg, mg = gold_material[item_id], model_gaps[item_id]
            gold_cause = gg["true_cause"]
            model_cause = mg.get("cause")
            cause_total += 1
            is_correct = model_cause == gold_cause
            if is_correct:
                cause_correct += 1
                cyc_cause_correct += 1
            if gold_cause == "unknown":
                unknown_total += 1
                if is_correct:
                    unknown_correct += 1
            else:
                traceable_total += 1
                if is_correct:
                    traceable_correct += 1

            if model_cause and model_cause != "unknown":
                c1_ok = (citation_is_real(mg.get("citation_1"), notes_text)
                        and citation_is_relevant(mg.get("citation_1"), gg["item_label"]))
                c2_ok = (citation_is_real(mg.get("citation_2"), notes_text)
                        and citation_is_relevant(mg.get("citation_2"), gg["item_label"]))
                if not (c1_ok and c2_ok):
                    fabricated += 1
                    cyc_fabricated += 1
                    if len(fabricated_examples) < 10:
                        fabricated_examples.append({
                            "cycle_id": cid, "item_id": item_id, "cause": model_cause,
                            "citation_1": mg.get("citation_1"), "citation_2": mg.get("citation_2"),
                            "citation_1_ok": c1_ok, "citation_2_ok": c2_ok,
                        })

            if gg["missing_view"] is not None:
                missing_view_total += 1
                if mg.get("missing_view") is True:
                    missing_view_correct += 1

        faithful, unmatched = narrative_faithfulness(rec["answer"].get("narrative"), rec["packed"])
        if faithful is None:
            narratives_missing += 1
        else:
            narratives_scored += 1
            if faithful:
                narratives_faithful += 1

        per_cycle.append({
            "cycle_id": cid, "gold_material": len(gold_ids), "model_covered": len(model_ids),
            "true_positive": len(tp), "false_positive": len(fp), "false_negative": len(fn),
            "cause_correct": cyc_cause_correct, "fabricated_cause": cyc_fabricated,
            "narrative_faithful": faithful, "narrative_unmatched": unmatched,
        })

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    overall = {
        "cycles_scored": len(per_cycle),
        "gold_material_total": tp_total + fn_total,
        "model_covered_total": tp_total + fp_total,
        "true_positive": tp_total, "false_positive": fp_total, "false_negative": fn_total,
        "gap_completeness_recall_pct": pct(tp_total, tp_total + fn_total),
        "gap_completeness_precision_pct": pct(tp_total, tp_total + fp_total),
        "cause_tag_agreement_pct": pct(cause_correct, cause_total),
        "cause_tag_agreement_unknown_pct": pct(unknown_correct, unknown_total),
        "cause_tag_agreement_traceable_pct": pct(traceable_correct, traceable_total),
        "unknown_total": unknown_total, "traceable_total": traceable_total,
        "fabricated_cause": fabricated,
        "fabricated_cause_rate_pct": pct(fabricated, cause_total),
        "missing_view_echo_correct": missing_view_correct,
        "missing_view_echo_total": missing_view_total,
        "missing_view_echo_pct": pct(missing_view_correct, missing_view_total),
        "narrative_faithful": narratives_faithful,
        "narrative_scored": narratives_scored,
        "narrative_missing": narratives_missing,
        "narrative_faithfulness_pct": pct(narratives_faithful, narratives_scored),
    }
    return {"overall": overall, "per_cycle": per_cycle, "fabricated_examples": fabricated_examples}
