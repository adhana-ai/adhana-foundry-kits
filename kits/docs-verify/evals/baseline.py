"""The free baseline: no model, no key, no spend. What does word-matching alone get you?

Usage:
    python -m evals.baseline --run-id b000-lexical

WHY A KIT LIKE THIS NEEDS ONE. "The model got 84%" is not a result until you know what a rule you
could have written in an afternoon gets. Every sibling kit ships this and every one of them has
found the baseline closer to the model than expected on at least one metric — docs-redact's regex
matched the model exactly on SSN, EMAIL, PHONE and CARD, and only lost on the two categories that
need reading. The point of the number is to locate where the model is actually buying you
something.

THE RULE, and it is deliberately the obvious one. A claim's content words are matched against the
document:

    nearly all of them present  ->  supported
    most present, but a NUMBER in the claim is missing from the document   ->  contradicted
    otherwise                                                              ->  not_stated

That third branch is why this baseline is interesting rather than a straw man. Lexical overlap
genuinely does separate `not_stated` from the rest — a claim about peer review shares almost no
vocabulary with a study record — so the baseline is expected to do respectably on the very class
the kit cares most about, and to fall apart precisely where reading is required: telling
`supported` from `contradicted`, which differ by one value in an otherwise identical sentence.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import verify as V                       # noqa: E402
from evals import judge as J                      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

STOP = set("a an the was were is are be been this that of to in on for by with and or as at "
           "were had has have it its their there which who whom from over under".split())


def _words(s):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'-]*", s.lower()) if w not in STOP]


def classify(claim, doc_text):
    low = doc_text.lower()
    toks = _words(claim)
    if not toks:
        return "not_stated", ""
    present = [t for t in toks if re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(t), low)]
    ratio = len(present) / len(toks)
    nums = [t for t in toks if re.fullmatch(r"\d[\d,.]*", t)]
    nums_missing = [n for n in nums
                    if not re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(n), low)]
    if nums and nums_missing and ratio >= 0.5:
        # The sentence is clearly about this document, and a number in it is not in the document.
        return "contradicted", ""
    if ratio >= 0.85:
        return "supported", ""
    return "not_stated", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-lexical")
    a = ap.parse_args()

    labelled = V.load_claims()
    records = []
    for doc_id in V.documents():
        claims = labelled.get(doc_id, [])
        if not claims:
            continue
        doc = V.load_doc(doc_id)
        rows = []
        for c in claims:
            verdict, quote = classify(c["text"], doc)
            rows.append({"id": c["id"], "claim": c["text"], "verdict": verdict,
                         "quote": quote, "quote_in_doc": None})
        records.append({"doc": doc_id, "claims": rows, "answered": len(rows),
                        "asked": len(rows), "parsed": True, "latency_ms": 0})

    scored = J.score(records, labelled)
    out = {
        "run_id": a.run_id,
        "stub": False,
        "baseline": True,
        "model": "none — lexical overlap, pure code",
        "provider": "none",
        "documents": len(records),
        "claims": scored["overall"]["claims"],
        "failures": 0,
        "latency_p50_ms": 0, "latency_p95_ms": 0,
        "input_tokens_total": 0, "output_tokens_total": 0,
        "scores": scored["overall"],
        "per_class": scored["per_class"],
        "matrix": scored["matrix"],
        "unanswered_by_class": scored["unanswered_by_class"],
        "records": records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("%-24s %s" % ("baseline", a.run_id))
    print("%-24s %s%%" % ("accuracy", o["accuracy_answered_pct"]))
    print("%-24s %s  (%s%%)" % ("false support", o["false_support"],
                                o["false_support_rate_pct"]))
    for c in J.LABELS:
        pc = scored["per_class"][c]
        print("  %-20s recall %-7s precision %-7s (gold %s)"
              % (c, pc["recall_pct"], pc["precision_pct"], pc["gold"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
