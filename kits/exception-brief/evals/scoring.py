"""Score a set of drafted exception briefs against gold. Pure code, shared by evals/baseline.py and
evals/run.py so the free floor and the real run are graded by the identical function -- a baseline
and a model scored by two different scorers cannot be compared honestly. Same discipline
gap-brief's evals/scoring.py and param-drift's evals/scoring.py both state for their own scorers.

Three axes, per src/rubric.py's RUBRIC_AXES, plus one guardrail metric reported on its own:

    exception_completeness    recall/precision of the ITEM SET the brief covers, against the
                              material exceptions it was actually handed.
    cause_tag_agreement        for items both gold and the brief cover, does the cause match --
                              split by whether gold's own cause was 'unknown' or traceable.
    narrative_faithfulness     does every quantified claim in the narrative trace to a number
                              actually present in the packed evidence.
    fabricated_cause          (guardrail, not an axis) a non-'unknown' cause whose citations are
                              not both real, item-relevant lines from that batch's own notes.

⚑ A CITATION MUST BE BOTH REAL AND RELEVANT, NOT MERELY REAL. Every planted cause-note line in this
corpus opens with "<item_label>: ..." (see tools/build_corpus.py), so a citation that is a genuine
substring of the notes log but does not name the item it is cited for is citing someone else's
evidence -- caught here, same discipline gap-brief's own scorer uses.
"""
import re

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
    """The numbers a faithful narrative is allowed to state: every unit figure and percentage in
    the packed exception list, the count of exceptions, and any digit run in the batch's own
    metadata (review_week, batch_id) or an item's location (e.g. "Store 118") that the model was
    also handed as input -- same carve-out gap-brief's own scorer applies, added after reading
    that kit's real run rather than before.

    ⚑ THE LOCATION CARVE-OUT WAS ADDED AFTER READING r001-exception-brief's OWN RESULT, NOT
    BEFORE. 8 of 40 real replies named a store location in the narrative ("Store 118"), and a
    first version of this pool -- built from the numeric evidence fields alone -- flagged "118" as
    an unmatched, seemingly-invented number. It is not invented; it is the `location` field the
    model was already given as context for every packed item. Widening the pool to cover what the
    model was actually handed is a scorer correctness fix, not a loosening of the guardrail: a
    narrative number still fails here the moment it is not traceable to ANYTHING in the packed
    input, which is the property this check exists to guarantee."""
    units, pcts = set(), set()
    for it in packed["items"]:
        if it["forecast_units"] is not None:
            units.add(round(it["forecast_units"]))
        if it["actual_pos_units"] is not None:
            units.add(round(it["actual_pos_units"]))
        if it["prior_year_analog_units"] is not None:
            units.add(round(it["prior_year_analog_units"]))
        if it["delta_units"] is not None:
            units.add(round(abs(it["delta_units"])))
        if it.get("delta_pct") is not None:
            pcts.add(round(abs(it["delta_pct"]), 1))
        for tok in re.findall(r"\d+", str(it.get("location") or "")):
            units.add(int(tok))
    units.add(len(packed["items"]))          # "N exceptions" is a legitimate narrative claim
    for field in ("review_week", "batch_id", "region"):
        for tok in re.findall(r"\d+", str(packed.get(field, ""))):
            units.add(int(tok))
    return units, pcts


def _amount_matches(val, is_pct, units, pcts):
    pool = pcts if is_pct else units
    for allowed in pool:
        tol = 1.5 if is_pct else max(5.0, 0.02 * abs(allowed))
        if abs(val - allowed) <= tol:
            return True
    return False


def narrative_faithfulness(narrative, packed):
    """Returns (faithful: bool or None, unmatched: [(val, is_pct), ...]). None means no narrative
    was produced at all -- a distinct, worse state than an unfaithful one, never folded in as a
    pass."""
    if not narrative:
        return None, []
    units, pcts = _allowed_pool(packed)
    nums = _extract_numbers(narrative)
    unmatched = [n for n in nums if not _amount_matches(n[0], n[1], units, pcts)]
    return (len(unmatched) == 0), unmatched


def score(records, gold, notes_by_id):
    """`records` are evals/run.py's per-batch output dicts (record["answer"]["items"/"narrative"],
    record["packed"]). `gold` and `notes_by_id` are keyed by batch_id."""
    tp_total = fp_total = fn_total = 0
    cause_correct = cause_total = 0
    unknown_correct = unknown_total = 0
    traceable_correct = traceable_total = 0
    fabricated = 0
    fabricated_examples = []
    unreliable_correct = unreliable_total = 0
    narratives_faithful = narratives_scored = narratives_missing = 0
    per_batch = []

    for rec in records:
        bid = rec["batch_id"]
        g = gold.get(bid)
        if not g:
            continue
        notes_text = "\n".join(notes_by_id.get(bid, []))
        gold_material = {gi["item_id"]: gi for gi in g["items"] if gi["material"]}
        model_items = {mi["item_id"]: mi for mi in rec["answer"]["items"] if mi.get("item_id")}

        gold_ids = set(gold_material)
        model_ids = set(model_items)
        tp = gold_ids & model_ids
        fp = model_ids - gold_ids
        fn = gold_ids - model_ids
        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn)

        b_cause_correct = 0
        b_fabricated = 0
        for item_id in tp:
            gi, mi = gold_material[item_id], model_items[item_id]
            gold_cause = gi["true_cause"]
            model_cause = mi.get("cause")
            cause_total += 1
            is_correct = model_cause == gold_cause
            if is_correct:
                cause_correct += 1
                b_cause_correct += 1
            if gold_cause == "unknown":
                unknown_total += 1
                if is_correct:
                    unknown_correct += 1
            else:
                traceable_total += 1
                if is_correct:
                    traceable_correct += 1

            if model_cause and model_cause != "unknown":
                c1_ok = (citation_is_real(mi.get("citation_1"), notes_text)
                        and citation_is_relevant(mi.get("citation_1"), gi["item_label"]))
                c2_ok = (citation_is_real(mi.get("citation_2"), notes_text)
                        and citation_is_relevant(mi.get("citation_2"), gi["item_label"]))
                if not (c1_ok and c2_ok):
                    fabricated += 1
                    b_fabricated += 1
                    if len(fabricated_examples) < 10:
                        fabricated_examples.append({
                            "batch_id": bid, "item_id": item_id, "cause": model_cause,
                            "citation_1": mi.get("citation_1"), "citation_2": mi.get("citation_2"),
                            "citation_1_ok": c1_ok, "citation_2_ok": c2_ok,
                        })

            if gi["unreliable_evidence"] is not None:
                unreliable_total += 1
                if mi.get("unreliable_evidence") == gi["unreliable_evidence"]:
                    unreliable_correct += 1

        faithful, unmatched = narrative_faithfulness(rec["answer"].get("narrative"), rec["packed"])
        if faithful is None:
            narratives_missing += 1
        else:
            narratives_scored += 1
            if faithful:
                narratives_faithful += 1

        per_batch.append({
            "batch_id": bid, "gold_material": len(gold_ids), "model_covered": len(model_ids),
            "true_positive": len(tp), "false_positive": len(fp), "false_negative": len(fn),
            "cause_correct": b_cause_correct, "fabricated_cause": b_fabricated,
            "narrative_faithful": faithful, "narrative_unmatched": unmatched,
        })

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    overall = {
        "batches_scored": len(per_batch),
        "gold_material_total": tp_total + fn_total,
        "model_covered_total": tp_total + fp_total,
        "true_positive": tp_total, "false_positive": fp_total, "false_negative": fn_total,
        "exception_completeness_recall_pct": pct(tp_total, tp_total + fn_total),
        "exception_completeness_precision_pct": pct(tp_total, tp_total + fp_total),
        "cause_tag_agreement_pct": pct(cause_correct, cause_total),
        "cause_tag_agreement_unknown_pct": pct(unknown_correct, unknown_total),
        "cause_tag_agreement_traceable_pct": pct(traceable_correct, traceable_total),
        "unknown_total": unknown_total, "traceable_total": traceable_total,
        "fabricated_cause": fabricated,
        "fabricated_cause_rate_pct": pct(fabricated, cause_total),
        "unreliable_evidence_echo_correct": unreliable_correct,
        "unreliable_evidence_echo_total": unreliable_total,
        "unreliable_evidence_echo_pct": pct(unreliable_correct, unreliable_total),
        "narrative_faithful": narratives_faithful,
        "narrative_scored": narratives_scored,
        "narrative_missing": narratives_missing,
        "narrative_faithfulness_pct": pct(narratives_faithful, narratives_scored),
    }
    return {"overall": overall, "per_batch": per_batch, "fabricated_examples": fabricated_examples}
