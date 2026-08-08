"""The free baseline: no model, no key, no spend. What does looking for the label alone get you?

Usage:
    python -m evals.baseline --run-id b000-label

WHY A KIT LIKE THIS NEEDS ONE. "The model got 96%" is not a result until you know what a rule you
could write in an afternoon gets. Every sibling kit ships this and every one of them has found the
baseline closer to the model than expected on at least one metric — docs-redact's regex matched the
model exactly on SSN, EMAIL, PHONE and CARD and lost only on the two categories that need reading.
The point of the number is to locate where the model is actually buying you something.

THE RULE, and it is deliberately the obvious one:

    the rule's element name appears as a line label in the document  ->  met
    it does not                                                     ->  never_addressed

It can never answer `breached`. That is not a weakness in the baseline — it is the finding.

⚠︎ THIS BASELINE IS EXPECTED TO SCORE VERY HIGH, AND THAT IS THE MOST USEFUL THING IN THE KIT.
Breach is 3.6% of applicable rules, so a checker that never says "breached" still gets ~96% of them
right. Read that number next to `breached recall: 0.0` and the lesson is unmissable: **on this
corpus accuracy measures almost nothing**, and any kit reporting a single headline percentage is
hiding the only part of the job that is hard.

⚠︎ IT IS ALSO A FAIRER FIGHT THAN IT LOOKS, AND THE REASON IS WORTH STATING RATHER THAN BURYING.
`tools/build_corpus.py` renders each document with the regulation's own element names as line
labels, because that is what those documents actually look like. So met-vs-never-addressed on this
corpus is very nearly a lexical question, and a string match answers it. What a string match cannot
do is notice that an enrolment count is estimated on a trial that has already finished, or that a
terminated trial never says why it stopped — every one of which needs someone to read the line and
know what the rule asks for. That is the whole margin, and it is small, real, and where this kit's
value has to come from if it has any.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import comply as C                       # noqa: E402
from evals import judge as J                      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def classify(rule, doc_text):
    """Label present -> met (quoting the line); label absent -> never_addressed."""
    name = rule["element"]
    if name.startswith("Primary Disease or Condition"):
        name = "Primary Disease or Condition Being Studied in the Trial"
    for cand in (name, name.replace("(s)", "")):
        for ln in doc_text.splitlines():
            if ln.startswith(cand + ": "):
                return "met", ln.strip()
    return "never_addressed", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-label")
    a = ap.parse_args()

    gold = C.load_gold()
    rules = C.rules()
    records = []
    for doc_id in C.documents():
        doc = C.load_doc(doc_id)
        rows = []
        for r in rules:
            verdict, quote = classify(r, doc)
            rows.append({"rule": r["id"], "cite": r["cite"], "element": r["element"],
                         "verdict": verdict, "quote": quote,
                         # The quote is lifted from the document by construction, so asserting
                         # fidelity here would be measuring this file rather than the checker.
                         "quote_in_doc": None})
        records.append({"doc": doc_id, "rules": rows, "answered": len(rows),
                        "asked": len(rows), "parsed": True, "latency_ms": 0})

    scored = J.score(records, gold)
    out = {
        "run_id": a.run_id,
        "stub": False,
        "baseline": True,
        "model": "none — element-label presence, pure code",
        "provider": "none",
        "documents": len(records),
        "rules": scored["overall"]["rules_scored"],
        "failures": 0,
        # ⚠︎ None, NOT 0. This baseline calls no provider, so it has no latency and no token count
        # — those are ABSENT measurements, not measurements of zero. Writing 0 would put "0 ms,
        # 0 tokens" on the history board beside two real runs, reading as "instant and free" (true)
        # and as "measured against the same thing" (not true).
        "latency_p50_ms": None, "latency_p95_ms": None,
        "input_tokens_total": None, "output_tokens_total": None,
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
    print("%-26s %s" % ("baseline", a.run_id))
    print("%-26s %s%%   <- read this beside 'breached recall' below"
          % ("accuracy", o["accuracy_answered_pct"]))
    print("%-26s %s  (%s%% of unmet rules)" % ("FALSE MET", o["false_met"],
                                               o["false_met_rate_pct"]))
    for c in J.LABELS:
        pc = scored["per_class"][c]
        print("  %-22s recall %-7s precision %-7s (gold %s)"
              % (c, pc["recall_pct"], pc["precision_pct"], pc["gold"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
