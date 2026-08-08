"""Check the labelled set before anything is scored against it. Run this before spending money.

A labelled set is the one thing in a kit that nothing else can check — same warning
docs-extract's check_labels.py opens with. A label whose text does not literally appear in its
document does not crash anything: it silently converts a correct detection into a recorded leak,
and the run that discovers it has already been paid for. This kit's own build step derives the
label from the same dict that renders the document (see tools/build_corpus.py), which should make
that failure structurally impossible here — this script is the check that confirms it actually is,
rather than trusting the construction to have worked.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import detect as D                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELLED = os.path.join(HERE, "data", "labelled.jsonl")

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def main():
    categories = {c["name"] for c in D.load_categories()}
    docs = set(D.documents())                  # ids without ".txt", matching detect.documents()

    rows = [json.loads(l) for l in open(LABELLED, encoding="utf-8") if l.strip()]
    by_doc = {}
    for r in rows:
        doc = r.get("doc", "")
        if doc in by_doc:
            bad("duplicate labelled.jsonl row for %r" % doc)
        by_doc[doc] = r

    labelled_ids = {doc[:-4] for doc in by_doc if doc.endswith(".txt")}
    missing = docs - labelled_ids
    if missing:
        bad("%d document(s) have no labelled row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = labelled_ids - docs
    if orphan:
        bad("%d labelled row(s) have no document: %s" % (len(orphan), sorted(orphan)[:5]))

    total_spans = 0
    per_category = {c: 0 for c in categories}
    for doc, row in sorted(by_doc.items()):
        doc_id = doc[:-4] if doc.endswith(".txt") else doc
        if doc_id not in docs:
            continue                            # already reported above as an orphan
        text = D.load_doc(doc_id)
        spans = row.get("spans") or []
        if not (3 <= len(spans) <= 7):
            bad("%s: %d labelled span(s), expected 3-7" % (doc, len(spans)))
        for sp in spans:
            cat = sp.get("category")
            txt = sp.get("text")
            if cat not in categories:
                bad("%s: category %r is not one of %s" % (doc, cat, sorted(categories)))
                continue
            # ⚠︎ THE CHECK THE WHOLE FILE EXISTS FOR. A label that is not a literal substring of
            # its document is worse than no label: it would score a correct detection as a miss
            # (or an honest silence as a hallucinated over-redaction) and nobody would know why.
            if not isinstance(txt, str) or txt == "" or txt not in text:
                bad("%s: span %r (%s) is not an exact substring of the document" % (doc, txt, cat))
                continue
            total_spans += 1
            per_category[cat] = per_category.get(cat, 0) + 1

    for cat, n in sorted(per_category.items()):
        if n == 0:
            bad("%s is labelled in 0 documents — a detector can never be scored on it" % cat)
        elif n < 3:
            print("  warn  %s is labelled in only %d span(s) — thin, but scoreable" % (cat, n))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d document(s), %d labelled span(s) across %d categories, all exact "
          "substrings" % (len(by_doc), total_spans, len(categories)))


if __name__ == "__main__":
    main()
