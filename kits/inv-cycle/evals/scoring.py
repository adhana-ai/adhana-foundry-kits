"""Score a set of drafted causes against gold. Pure code, shared by evals/baseline.py and
evals/run.py so the free floor and the real run are graded by the identical function -- a baseline
and a model scored by two different scorers cannot be compared honestly. Same discipline
gap-brief's own evals/scoring.py states for its scorer.

Three axes, per src/rubric.py's RUBRIC_AXES, plus two guardrail metrics reported on their own:

    cause_accuracy          5-way exact match against gold's cause.
    citation_validity       for a non-'unresolved' cause, is every cited log line real AND does
                            it actually evidence that cause -- src/segment.py::line_supports_cause
                            is the single rule both this file and tools/build_corpus.py use.
    narrative_faithfulness   does the narrative's stated cause word match the structured cause
                            field -- the simple pure-code proxy the use case spec asks for.
    fabricated_cause         (guardrail) a non-'unresolved' cause with an empty or unsupported
                            citation list.
    uom_transfer_confusion   (guardrail, THE metric) of gold's unrecorded_transfer TRAP cases,
                            how many were drafted as uom_error. Denominator is trap cases only.
"""
from src import segment as SEG


def citation_validity(event, cause, citations):
    """None when not applicable (cause is 'unresolved' and citations is empty, which is the
    correct, honest shape). True/False otherwise -- False for an empty list on a non-'unresolved'
    cause, since a specific cause with no support cited is exactly as ungrounded as one with a
    fabricated line."""
    if cause == "unresolved":
        return None if not citations else False          # unresolved should cite nothing
    if not citations:
        return False
    return all(SEG.line_supports_cause(event, i, cause) for i in citations)


def _cause_phrase(cause):
    return (cause or "").replace("_", " ")


def narrative_faithfulness(narrative, cause):
    """Returns True/False/None -- None means no narrative was produced at all, a distinct, worse
    state than an unfaithful one, never folded in as a pass. The check is deliberately the
    simplest pure-code proxy that still means something: does the narrative's prose actually name
    the drafted cause, in either its underscore or spaced-out form."""
    if not narrative:
        return None
    if not cause:
        return False
    text = narrative.lower()
    return cause in text or _cause_phrase(cause) in text


def score(records, gold_by_id, events_by_id):
    """`records` are evals/run.py's per-event output dicts (record["answer"]["cause"/"citations"/
    "narrative"], record["event_id"]). `gold_by_id` and `events_by_id` are keyed by event_id."""
    cause_correct = cause_total = 0
    unresolved_correct = unresolved_total = 0
    traceable_correct = traceable_total = 0
    confusion = {}          # (gold_cause, model_cause) -> count, for a full breakdown

    cite_valid = cite_total = 0
    fabricated = 0
    fabricated_examples = []

    trap_total = trap_confused = 0

    narratives_faithful = narratives_scored = narratives_missing = 0

    per_event = []

    for rec in records:
        eid = rec["event_id"]
        g = gold_by_id.get(eid)
        event = events_by_id.get(eid)
        if not g or not event:
            continue

        gold_cause = g["cause"]
        model_cause = rec["answer"].get("cause")
        citations = rec["answer"].get("citations") or []

        cause_total += 1
        is_correct = model_cause == gold_cause
        if is_correct:
            cause_correct += 1
        if gold_cause == "unresolved":
            unresolved_total += 1
            if is_correct:
                unresolved_correct += 1
        else:
            traceable_total += 1
            if is_correct:
                traceable_correct += 1
        confusion[(gold_cause, model_cause)] = confusion.get((gold_cause, model_cause), 0) + 1

        cv = citation_validity(event, model_cause, citations) if model_cause else False
        if cv is not None:
            cite_total += 1
            if cv:
                cite_valid += 1
            else:
                fabricated += 1
                if len(fabricated_examples) < 10:
                    fabricated_examples.append({
                        "event_id": eid, "cause": model_cause, "citations": citations,
                        "gold_cause": gold_cause,
                    })

        if g.get("is_trap"):
            trap_total += 1
            if model_cause == "uom_error":
                trap_confused += 1

        faithful = narrative_faithfulness(rec["answer"].get("narrative"), model_cause)
        if faithful is None:
            narratives_missing += 1
        else:
            narratives_scored += 1
            if faithful:
                narratives_faithful += 1

        per_event.append({
            "event_id": eid, "gold_cause": gold_cause, "model_cause": model_cause,
            "correct": is_correct, "citation_valid": cv, "is_trap": bool(g.get("is_trap")),
            "narrative_faithful": faithful,
        })

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    overall = {
        "events_scored": len(per_event),
        "cause_accuracy_pct": pct(cause_correct, cause_total),
        "cause_accuracy_unresolved_pct": pct(unresolved_correct, unresolved_total),
        "cause_accuracy_traceable_pct": pct(traceable_correct, traceable_total),
        "unresolved_total": unresolved_total, "traceable_total": traceable_total,
        "citation_validity_pct": pct(cite_valid, cite_total),
        "citation_scored": cite_total,
        "fabricated_cause": fabricated,
        "fabricated_cause_rate_pct": pct(fabricated, cite_total),
        "uom_transfer_confusion": trap_confused,
        "uom_transfer_confusion_rate_pct": pct(trap_confused, trap_total),
        "trap_total": trap_total,
        "narrative_faithful": narratives_faithful,
        "narrative_scored": narratives_scored,
        "narrative_missing": narratives_missing,
        "narrative_faithfulness_pct": pct(narratives_faithful, narratives_scored),
    }
    return {
        "overall": overall, "per_event": per_event,
        "fabricated_examples": fabricated_examples,
        "confusion": {"%s->%s" % k: v for k, v in confusion.items()},
    }
