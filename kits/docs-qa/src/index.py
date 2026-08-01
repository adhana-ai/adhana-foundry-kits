"""Build and load the index. A file, not a server.

WHY A FILE.
A kit has four layers and no more, and "no database" is one of the scope rules. It is not
squeamishness: a database is a thing a forker has to install, run, migrate and understand before
they can change the part they actually came for. Forty documents of vectors fit in a file, and a
file diffs, versions, and ships in the repo.

WHAT IS CHECKED IN AND WHAT IS NOT.
`chunks.json` is small and checked in, so a fresh clone retrieves with no key and no build step.
`vectors.json` is not: it is large, it is specific to one embedding model, and rebuilding it is
exactly what a forker does when they point the kit at their own documents.
"""
import json
import os

from . import boilerplate
from . import chunk as chunker
from . import extract
from .retrieve import build_keyword_index

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")
INDEX = os.path.join(HERE, "data", "index")
CHUNKS = os.path.join(INDEX, "chunks.json")
VECTORS = os.path.join(INDEX, "vectors.json")

# A file that DESCRIBES the corpus is not part of it. `SOURCES.md` carries the licence and the
# provenance for the forty documents beside it, and it sits there deliberately -- provenance travels
# with the thing it covers or it is not provenance. But it is Markdown in a corpus that legitimately
# holds twelve Markdown documents, so nothing about its extension marks it as furniture.
#
# It was added on 2026-07-31 and silently became a 41st document: a rebuild produces 41 documents
# and 676 chunks against the committed 40 and 668. Retrieval over a corpus with an extra document
# scores differently, so every published number would have quietly stopped reproducing. Nobody saw
# it because the cold-clone fork test runs `--retrieval-only`, which calls load() and never build().
#
# README.md is named here too, ahead of a forker meeting the same thing: dropping documents into a
# folder that already explains itself is the ordinary case, not an exotic one.
NOT_CORPUS = {"SOURCES.md", "README.md"}


def build(corpus_dir=CORPUS, verbose=True):
    """Extract, chunk, write. Deterministic: sorted input, sorted output, stable ids -- so a
    rebuild that changes the index is a real change and shows up as a real diff."""
    os.makedirs(INDEX, exist_ok=True)
    texts, formats, failures, by_format = {}, {}, [], {}
    for name in sorted(os.listdir(corpus_dir)):
        path = os.path.join(corpus_dir, name)
        if not os.path.isfile(path) or name.startswith(".") or name in NOT_CORPUS:
            continue
        doc_id = os.path.splitext(name)[0]
        try:
            text, fmt = extract.extract(path)
        except Exception as e:                      # a corpus that hides a bad file lies about size
            failures.append({"doc": doc_id, "file": name, "error": str(e)})
            if verbose:
                print("  !! %-18s %s" % (doc_id, e))
            continue
        texts[doc_id], formats[doc_id] = text, fmt
        by_format[fmt] = by_format.get(fmt, 0) + 1

    # Repeated furniture is dropped ACROSS the corpus, which is why it happens here rather than in
    # an extractor: one document cannot tell you what every document repeats.
    texts, boiler = boilerplate.strip(texts, formats)

    chunks = []
    for doc_id in sorted(texts):
        got = chunker.chunk_document(doc_id, texts[doc_id], formats[doc_id])
        if not got:
            # Extracted, but nothing survived chunking -- this is what "not extracted" looks like
            # from the pipeline's side, and it is recorded rather than skipped.
            failures.append({"doc": doc_id, "error": "extracted 0 usable chunks"})
        chunks += got
        if verbose:
            print("  %-18s %-5s %6d chars -> %2d chunks"
                  % (doc_id, formats[doc_id], len(texts[doc_id]), len(got)))

    payload = {"chunks": chunks, "documents": len(set(c["doc"] for c in chunks)),
               "by_format": by_format, "extraction_failures": failures, "boilerplate": boiler}
    with open(CHUNKS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    return payload


def load():
    """Load chunks, rebuild the keyword weights, and attach vectors if they exist.

    The keyword weights are recomputed rather than stored: they are derived from the chunks, and a
    derived value on disk is a second copy waiting to disagree with the first.
    """
    if not os.path.exists(CHUNKS):
        raise RuntimeError("no index -- run: python -m src.index")
    data = json.load(open(CHUNKS, encoding="utf-8"))
    index = {"chunks": data["chunks"], "idf": build_keyword_index(data["chunks"]),
             "documents": data["documents"], "by_format": data["by_format"],
             "extraction_failures": data.get("extraction_failures", []),
             "boilerplate": data.get("boilerplate", {}), "vectors": None,
             "embed_model": None}
    if os.path.exists(VECTORS):
        v = json.load(open(VECTORS, encoding="utf-8"))
        index["vectors"], index["embed_model"] = v["vectors"], v["model"]
    return index


if __name__ == "__main__":
    p = build()
    print("\nindex: %d chunks across %d documents" % (len(p["chunks"]), p["documents"]))
    for fmt, n in sorted(p["by_format"].items()):
        print("  %-5s %d" % (fmt, n))
    b = p.get("boilerplate") or {}
    if b.get("lines_dropped"):
        print("\n  boilerplate: dropped %d lines (%d distinct) repeated across the corpus, e.g."
              % (b["lines_dropped"], b["distinct_lines"]))
        for ex in b["examples"][:4]:
            print("    %s" % (ex[:88]))
    if p["extraction_failures"]:
        print("\n  %d extraction failure(s) -- recorded, not hidden:" % len(p["extraction_failures"]))
        for f in p["extraction_failures"]:
            print("    %-18s %s" % (f["doc"], f["error"]))
