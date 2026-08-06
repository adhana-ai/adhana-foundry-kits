"""Turn a raw fetch into the shipped corpus: one .txt per document, a manifest, and the gold set.

    python -m tools.build_corpus

⚑ THE GOLD LABEL IS SEPARATED FROM THE DOCUMENT HERE, AND THAT IS THE POINT OF THIS FILE.
The API hands back the text and its `type` in one object. If both stayed in one file, every later
stage would be one careless `json.load` away from reading the answer it is being scored on — and
that failure does not crash, it produces a suspiciously good number. So the split happens once, at
the corpus boundary: `data/corpus/<id>.txt` holds ONLY what a router gets to see, and
`data/gold.jsonl` holds the labels, in a file nothing but the scorer opens.

⚠︎ WHAT THE ROUTER SEES IS TITLE + ACTION + ABSTRACT, AND NOT THE AGENCY. The agency is dropped on
purpose. "Federal Aviation Administration" predicts nothing about whether a document binds you,
but it is a strong hint about what KIND of thing the agency usually publishes, and a router that
learned agency priors would score well here while being useless on the one document that matters —
the unusual one from a familiar agency. Dropping it is a decision about what is being measured,
so it is made here, visibly, rather than by a prompt that happens not to mention it.

⚑ AND THE ABSTRACT IS REQUIRED. A document with no abstract is skipped, with a count printed. This
is the same exclusion `taxonomy.py` documents for Presidential Documents, applied per document
rather than per class: a record whose only content is a title is a different input shape, and
mixing shapes measures the shape.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import taxonomy as TX                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = os.path.join(HERE, "data", "_fetched")
CORPUS = os.path.join(HERE, "data", "corpus")
GOLD = os.path.join(HERE, "data", "gold.jsonl")
MANIFEST = os.path.join(CORPUS, "manifest.json")

# Long enough that the router has something to read; short enough that a one-line abstract is not
# silently treated as a document. Measured: the median abstract in a 150-document sample is 407
# characters, and the 10th percentile is 118. This sits below the floor of what a human router
# would call readable, so it excludes stubs without trimming the distribution.
MIN_ABSTRACT = 80

# ⚑ THE SHIPPED CORPUS IS CAPPED PER CLASS, AND THE FETCH DELIBERATELY OVER-PULLS TO FILL IT.
# Fetching 40 per type does not yield 40 per class: the first attempt produced 40 / 40 / 28,
# because 12 of the 40 notices carried no abstract and were skipped. An eval set of 40/40/28 is
# not balanced, and "balanced by construction" is either true or it is a sentence in a docstring.
# So the fetcher pulls more than it needs and this cap takes the first N of each class in
# document-number order — a deterministic cut, not a sample, so a rebuild produces the same corpus.
TARGET_PER_CLASS = 40


def _clean(s):
    """Collapse the API's whitespace. Nothing else — no lowercasing, no punctuation stripping.
    A router in production reads what arrives, and a corpus normalised past what arrives is a
    corpus that flatters every model measured on it."""
    return re.sub(r"[ \t]+", " ", (s or "").replace("\r\n", "\n")).strip()


def _document_text(rec):
    """What the router is allowed to see. Order is the order a person would read it in."""
    parts = ["TITLE: " + _clean(rec.get("title"))]
    action = _clean(rec.get("action"))
    if action:
        # `action` is the publisher's own one-line summary of what the document DOES ("Final rule.",
        # "Notice of meeting."). ⚠︎ IT OFTEN CONTAINS THE ANSWER VERBATIM, and it is kept anyway:
        # it is genuinely present on the real input, so removing it would be building an easier
        # problem than the one a router faces. What it must not do is go unmeasured — `evals/
        # baseline.py` scores a keyword classifier over exactly this text, so the share of the
        # task that is "read the label off the page" is published as a number rather than argued.
        parts.append("ACTION: " + action)
    parts.append("")
    parts.append(_clean(rec.get("abstract")))
    return "\n".join(parts) + "\n"


def build():
    if not os.path.isdir(FETCHED):
        raise SystemExit("nothing fetched. Run `python -m tools.fetch_corpus` first.")
    os.makedirs(CORPUS, exist_ok=True)
    manifest, gold, skipped = [], [], {"no_abstract": 0, "too_short": 0, "unrouted_type": 0,
                                       "over_cap": 0}

    for queue in TX.ORDER:
        path = os.path.join(FETCHED, "%s.json" % queue)
        if not os.path.exists(path):
            continue
        payload = json.load(open(path, encoding="utf-8"))
        taken = 0
        for rec in sorted(payload.get("results") or [],
                          key=lambda r: r.get("document_number") or ""):
            if taken >= TARGET_PER_CLASS:
                skipped["over_cap"] += 1
                continue
            key = TX.from_source(rec.get("type"))
            if key is None:
                skipped["unrouted_type"] += 1
                continue
            abstract = _clean(rec.get("abstract"))
            if not abstract:
                skipped["no_abstract"] += 1
                continue
            if len(abstract) < MIN_ABSTRACT:
                skipped["too_short"] += 1
                continue
            doc_id = rec.get("document_number")
            with open(os.path.join(CORPUS, "%s.txt" % doc_id), "w", encoding="utf-8") as f:
                f.write(_document_text(rec))
            manifest.append({
                "doc_id": doc_id,
                "title": _clean(rec.get("title"))[:180],
                "published": rec.get("publication_date"),
                "agencies": [a.get("name") for a in (rec.get("agencies") or [])
                             if isinstance(a, dict) and a.get("name")],
                "source_url": rec.get("html_url"),
                "chars": len(_document_text(rec)),
            })
            gold.append({"doc_id": doc_id, "queue": key, "source_type": rec.get("type")})
            taken += 1

    manifest.sort(key=lambda m: m["doc_id"])
    gold.sort(key=lambda g: g["doc_id"])
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"documents": len(manifest), "records": manifest}, f, indent=1,
                  ensure_ascii=False)
    with open(GOLD, "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    counts = {}
    for g in gold:
        counts[g["queue"]] = counts.get(g["queue"], 0) + 1
    print("%-30s %d" % ("documents built", len(manifest)))
    for q in TX.ORDER:
        print("  %-28s %d" % (TX.label_of(q), counts.get(q, 0)))
    for reason, n in skipped.items():
        if n:
            print("  %-28s %d skipped" % (reason, n))
    print("\n-> %s" % os.path.relpath(CORPUS, HERE))
    print("-> %s   (the labels; nothing but evals/score.py opens this)"
          % os.path.relpath(GOLD, HERE))
    return len(manifest)


if __name__ == "__main__":
    build()
