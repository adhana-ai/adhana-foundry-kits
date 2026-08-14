#!/usr/bin/env python3
"""Write the corpus, the change requests and the expected results. Deterministic — re-run and diff.

    python3 tools/build_corpus.py            # write data/corpus/, data/gold/, data/requests.jsonl
    python3 tools/build_corpus.py --verify   # rebuild and prove the committed tree matches

⚑ --verify IS THE LICENCE ARGUMENT MADE EXECUTABLE. The corpus contract claims every byte is ours
and reproducible from a fixed seed. That claim decays the moment somebody edits a file by hand, and
nothing else in the kit would notice. This exits 1 if the committed tree is not what the generator
produces.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import corpus as C  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")


def _tree(docs):
    """{relative path: exact bytes} — the whole committed corpus as one dict, so writing and
    verifying cannot drift apart by being two different walks of the same idea."""
    out = {}
    for d in docs:
        out["corpus/%s.txt" % d["doc_id"]] = d["before"]
        out["gold/%s.txt" % d["doc_id"]] = d["after"]
    out["requests.jsonl"] = "".join(
        json.dumps({"doc_id": d["doc_id"], "request": d["request"], "family": d["family"],
                    "should_write": d["should_write"], "why_refuse": d["why"]},
                   sort_keys=True) + "\n"
        for d in docs)
    return out


def write():
    docs = C.make_documents()
    tree = _tree(docs)
    for rel, body in tree.items():
        p = os.path.join(DATA, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    fam = {}
    for d in docs:
        fam[d["family"]] = fam.get(d["family"], 0) + 1
    n_write = sum(1 for d in docs if d["should_write"])
    print("wrote %d documents, %d gold results, %d requests"
          % (len(docs), len(docs), len(docs)))
    print("  %d must be applied, %d must be refused" % (n_write, len(docs) - n_write))
    print("  families: %s" % ", ".join("%s %d" % kv for kv in sorted(fam.items())))
    # A refusal's gold is the document UNCHANGED. Assert it rather than trust it: if a generator
    # bug ever made a refusal's `after` differ from its `before`, every refusal would score as a
    # required edit and the whole refusal half of this kit would silently invert.
    bad = [d["doc_id"] for d in docs if not d["should_write"] and d["after"] != d["before"]]
    assert not bad, "refusal rows whose gold is not the untouched document: %s" % bad
    print("  every refusal's expected result is the untouched document — asserted")


def verify():
    tree = _tree(C.make_documents())
    bad = []
    for rel, body in tree.items():
        p = os.path.join(DATA, rel)
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != body:
            bad.append(rel)
    if bad:
        print("CORPUS DRIFT — %d file(s) are not what the seed produces: %s"
              % (len(bad), ", ".join(bad[:8])))
        return 1
    print("corpus verified — %d file(s) byte-identical to a rebuild from seed %d"
          % (len(tree), C.SEED))
    return 0


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else (write() or 0))
