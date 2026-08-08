"""Score a redaction run. PURE CODE — no LLM judge in this kit either, for the same reason
docs-extract has none: the gold is exact spans of text, and whether a detected span matches a
labelled one is a string comparison, not a judgement call. A judge would add cost, latency and a
second source of disagreement to a question `==` (with light normalisation) already settles.

⚑ THE TWO FAILURE DIRECTIONS, SCORED SEPARATELY AND NEVER AVERAGED — this is the guardrail this
kit exists to measure, and it has the identical shape to docs-extract's extraction/refusal split:

    LEAKED         a labelled span the detector did not report at all.        (false negative)
    OVER-REDACTED  a reported span that matches no labelled span.             (false positive)

⚠︎ THESE ARE NOT SYMMETRIC AND MUST NEVER BE COLLAPSED INTO ONE F1. A detector that reports every
word of every document as every category catches 100% of the real spans and posts a perfect
"recall" — and buries the document under false positives that make the redacted output useless.
A detector that reports nothing posts a perfect "precision" on the zero spans it dared to claim and
leaks all of it. `overall` below reports precision and recall side by side, plus the raw leaked and
over-redacted counts, and F1 is provided only as a single-number summary for a dashboard tile —
never as the number this kit optimises toward, because optimising a blend hides which direction of
error grew.

⚑ MATCHING IS BY (CATEGORY, NORMALISED TEXT) — NOT BY OFFSET. `src/redact.py`'s `locate()` finds
WHERE a span sits in a document, which the app needs to build a redacted or highlighted view. The
judge needs something else: whether the SPAN ITSELF was correctly identified, independent of which
occurrence in the document it happened to land on. Grading on (category, text) as a bag rather than
on offsets sidesteps a whole class of false disagreement — two runs that find the same phone number
via different internal orderings still agree here, exactly as `norm()` in docs-extract's judge
strips whitespace and case rather than treating them as a second answer.
"""
from collections import Counter


def norm(text):
    """Compare like a careful human, not like a database — same discipline as docs-extract's
    judge: case and surrounding whitespace never carry meaning for whether two spans are the same
    sensitive value; punctuation inside the value (dashes in an SSN, parens in a phone number) DOES
    carry meaning, because '219-08-4471' and '2190 84471' are not interchangeable evidence that the
    detector actually read the number rather than approximating it."""
    if text is None:
        return None
    s = " ".join(str(text).split())
    return s.lower() or None


def score_doc(labelled_spans, detected_spans):
    """One document's spans, both sides as {"text","category"} lists -> counts.

    Bag-of-(category, normalised text) comparison. A repeated identical span (the same phone
    number twice in one document) is repeated in the bag too, via Counter multiplicities, so a
    detector that only reports it once is correctly charged with one leak, not credited as if the
    second occurrence never needed catching.
    """
    want = Counter((s["category"].upper(), norm(s["text"])) for s in labelled_spans)
    got = Counter((s["category"].upper(), norm(s["text"])) for s in detected_spans)
    matched = want & got
    tp = sum(matched.values())
    leaked = sum((want - got).values())
    over = sum((got - want).values())
    return {"true_positives": tp, "leaked": leaked, "over_redacted": over,
            "labelled": sum(want.values()), "detected": sum(got.values())}


def score(labels, records):
    """labels: {doc: [{"text","category"}...]}   records: {doc: [{"text","category"}...]}

    `records` is keyed the same way `labels` is (by filename) so a document present in one and
    missing from the other — a failed call, or a corpus edit that outran the label file — is
    visible rather than silently treated as a perfect or an empty score.
    """
    per_doc, by_category = {}, {}
    tot = Counter()
    for doc, spans in sorted(labels.items()):
        detected = records.get(doc, [])
        d = score_doc(spans, detected)
        per_doc[doc] = d
        tot.update(d)

        # Same per-document scoring, run again per category, so a per-category breakdown is a real
        # re-derivation rather than a guess split proportionally from the total.
        cats = {s["category"].upper() for s in spans} | {s["category"].upper() for s in detected}
        for cat in cats:
            bucket = by_category.setdefault(cat, Counter())
            d_cat = score_doc([s for s in spans if s["category"].upper() == cat],
                              [s for s in detected if s["category"].upper() == cat])
            bucket.update(d_cat)

    tp, leaked, over = tot["true_positives"], tot["leaked"], tot["over_redacted"]
    precision = round(tp / (tp + over), 4) if (tp + over) else None
    recall = round(tp / (tp + leaked), 4) if (tp + leaked) else None
    f1 = (round(2 * precision * recall / (precision + recall), 4)
          if precision and recall and (precision + recall) else None)

    return {
        "per_doc": per_doc,
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "overall": {
            "labelled_spans": tot["labelled"],
            "detected_spans": tot["detected"],
            "true_positives": tp,
            # The guardrail figure: a labelled span the detector never reported at all. Higher
            # severity than over-redaction — see the module docstring.
            "leaked": leaked,
            "leak_rate": round(leaked / tot["labelled"], 4) if tot["labelled"] else None,
            # The other direction: a reported span with no matching label — safe text masked.
            "over_redacted": over,
            "over_redaction_rate": round(over / tot["detected"], 4) if tot["detected"] else None,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
    }
