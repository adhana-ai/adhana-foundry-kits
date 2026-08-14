#!/usr/bin/env python3
"""Write the corpus and its ground truth. Deterministic — re-run it and diff.

    python3 tools/build_corpus.py            # write data/corpus/{clean,messy}/ and data/gold.jsonl
    python3 tools/build_corpus.py --verify   # rebuild in memory and prove the tree matches

⚑ --verify IS THE LICENCE ARGUMENT MADE EXECUTABLE. The corpus contract claims every byte is ours
and reproducible from a fixed seed. A claim like that decays the moment someone edits a file in
data/corpus by hand, and nothing else in the kit would notice. This exits 1 if the committed corpus
is not what the generator produces.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import corpus as C  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")

FIELDS = [
    {"key": "doc_number", "label": "Document number",
     "hint": "The document's own identifier, not any other reference on the page."},
    {"key": "doc_date", "label": "Document date", "hint": "ISO format, YYYY-MM-DD."},
    {"key": "total_amount", "label": "Total amount due",
     "hint": "The final total, not the subtotal and not a line total. Digits only, two decimals."},
    {"key": "currency", "label": "Currency", "hint": "Three-letter ISO code."},
    {"key": "counterparty", "label": "Counterparty",
     "hint": "The organisation that issued the document."},
    {"key": "reference", "label": "Purchase-order or customer reference",
     "hint": "Often absent. If the page does not state one, say so rather than guessing."},
]


def write():
    docs = C.build()
    for cond in ("clean", "messy"):
        d = os.path.join(CORPUS, cond)
        os.makedirs(d, exist_ok=True)
        for doc in docs:
            with open(os.path.join(d, doc["doc_id"] + ".txt"), "w", encoding="utf-8") as f:
                f.write(doc[cond])
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as f:
        for doc in docs:
            # One gold row per DOCUMENT, not per condition. That is the whole design: the page says
            # the same thing in both conditions, so the answer is the same and only the legibility
            # changed. A gold row per condition would let the two drift and quietly turn this into
            # two unrelated benchmarks.
            f.write(json.dumps({"doc_id": doc["doc_id"], "kind": doc["kind"],
                                "gold": doc["gold"]}, sort_keys=True) + "\n")
    with open(os.path.join(DATA, "fields.json"), "w", encoding="utf-8") as f:
        json.dump({"fields": FIELDS}, f, indent=2)
        f.write("\n")
    n_ref = sum(1 for d in docs if d["gold"]["reference"] is None)
    print("wrote %d documents x 2 conditions = %d files" % (len(docs), len(docs) * 2))
    print("  %d cells total: %d stated, %d not-stated (refusal cells)"
          % (len(docs) * len(FIELDS), len(docs) * len(FIELDS) - n_ref, n_ref))
    print("  mean character error rate clean->messy: %.1f%%" % (100 * _cer(docs)))


def _cer(docs):
    """Character error rate, as an EDIT distance — reported so the degradation is not a black box.

    ⚠︎ THE FIRST VERSION OF THIS ZIPPED THE TWO STRINGS AND COUNTED POSITIONS THAT DIFFERED, AND
    IT REPORTED 53.9%. That number is an alignment artifact, not a measurement: this degrader
    deletes spaces and joins lines, so a single dropped character shifts everything after it and
    every following position counts as an error. A real 54% CER would be an unreadable page, and
    the pages are plainly readable — the number had the wrong SHAPE, which is the cheapest kind of
    harness bug to catch and the most embarrassing to publish. difflib gives the aligned answer.
    """
    import difflib
    bad = tot = 0
    for d in docs:
        a, b = d["clean"], d["messy"]
        tot += len(a)
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        bad += len(a) - sum(blk.size for blk in sm.get_matching_blocks())
    return bad / max(1, tot)


def verify():
    docs = C.build()
    bad = []
    for cond in ("clean", "messy"):
        for doc in docs:
            p = os.path.join(CORPUS, cond, doc["doc_id"] + ".txt")
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != doc[cond]:
                bad.append("%s/%s" % (cond, doc["doc_id"]))
    if bad:
        print("CORPUS DRIFT — %d file(s) are not what the seed produces: %s"
              % (len(bad), ", ".join(bad[:8])))
        return 1
    print("corpus verified — %d files byte-identical to a rebuild from seed %d"
          % (len(docs) * 2, C.SEED))
    return 0


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else (write() or 0))
