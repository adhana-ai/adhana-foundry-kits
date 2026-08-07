"""Turn a raw fetch into the shipped corpus: one .txt per document version, a manifest of pairs.

    python -m tools.build_corpus

⚑ WHAT THE MODEL SEES IS TITLE + ACTION + ABSTRACT, THE SAME FIELDS docs-route USES — not the
full legal text. Two reasons, both measured on the sibling kit rather than assumed here: the
abstract is where a correction actually narrates its own fix ("NMFS corrects the final rule
published on July 22, 2026... inadvertently omitted portions of three amendatory instructions"),
and staying at abstract-length keeps this kit standard-library-only with nothing to chunk.

⚑ A PAIR WITH NO DETECTABLE DIFFERENCE AT THIS FIELD SET IS SKIPPED, COUNTED, NOT SHIPPED. Two
documents can share a RIN and still read identically at the abstract level if the correction's
substance lives entirely in the body text the API does not return here — that is a real limit of
working at abstract-length, stated in Data.breaks_on on the published kit rather than hidden by
silently keeping a pair `src/diff.py` would find nothing in.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import diff as D                          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = os.path.join(HERE, "data", "_fetched")
CORPUS = os.path.join(HERE, "data", "corpus")
PAIRS_FILE = os.path.join(HERE, "data", "pairs.jsonl")
MANIFEST = os.path.join(CORPUS, "manifest.json")

MIN_ABSTRACT = 80


def _clean(s):
    return re.sub(r"[ \t]+", " ", (s or "").replace("\r\n", "\n")).strip()


def _document_text(rec):
    parts = ["TITLE: " + _clean(rec.get("title"))]
    action = _clean(rec.get("action"))
    if action:
        parts.append("ACTION: " + action)
    parts.append("")
    parts.append(_clean(rec.get("abstract")))
    return "\n".join(parts) + "\n"


def build():
    raw_path = os.path.join(FETCHED, "pairs.json")
    if not os.path.exists(raw_path):
        raise SystemExit("nothing fetched. Run `python -m tools.fetch_corpus` first.")
    os.makedirs(CORPUS, exist_ok=True)
    raw = json.load(open(raw_path, encoding="utf-8")).get("pairs") or []

    manifest, pairs_out = [], []
    skipped = {"short_abstract": 0, "no_detectable_change": 0}
    for p in raw:
        v1, v2 = p["v1"], p["v2"]
        a1, a2 = _clean(v1.get("abstract")), _clean(v2.get("abstract"))
        if len(a1) < MIN_ABSTRACT or len(a2) < MIN_ABSTRACT:
            skipped["short_abstract"] += 1
            continue
        t1, t2 = _document_text(v1), _document_text(v2)
        if D.primary(t1, t2) is None:
            skipped["no_detectable_change"] += 1
            continue

        v1_id, v2_id = v1["document_number"], v2["document_number"]
        with open(os.path.join(CORPUS, "%s.txt" % v1_id), "w", encoding="utf-8") as f:
            f.write(t1)
        with open(os.path.join(CORPUS, "%s.txt" % v2_id), "w", encoding="utf-8") as f:
            f.write(t2)

        pair_id = "%s__%s" % (v1_id, v2_id)
        manifest.append({
            "pair_id": pair_id, "v1_id": v1_id, "v2_id": v2_id,
            "v1_title": v1.get("title", "")[:180], "v1_published": v1.get("publication_date"),
            "v2_published": v2.get("publication_date"),
            "regulation_id_numbers": v2.get("regulation_id_numbers") or [],
            "v1_source_url": v1.get("html_url"), "v2_source_url": v2.get("html_url"),
        })
        pairs_out.append({"pair_id": pair_id, "v1_id": v1_id, "v2_id": v2_id,
                          "correction_abstract": a2})

    manifest.sort(key=lambda m: m["pair_id"])
    pairs_out.sort(key=lambda p: p["pair_id"])
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"pairs": manifest}, f, indent=1, ensure_ascii=False)
    with open(PAIRS_FILE, "w", encoding="utf-8") as f:
        for p in pairs_out:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print("%-30s %d" % ("pairs built", len(manifest)))
    for reason, n in skipped.items():
        if n:
            print("  %-28s %d skipped" % (reason, n))
    print("\n-> %s" % os.path.relpath(CORPUS, HERE))
    print("-> %s" % os.path.relpath(PAIRS_FILE, HERE))
    return len(manifest)


if __name__ == "__main__":
    build()
