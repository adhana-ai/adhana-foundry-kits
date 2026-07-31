"""The gate on the labelled set. Run it before trusting a single eval number.

WHY THIS EXISTS, AND WHY IT RUNS FIRST.
Every other number this kit publishes is derived from a run. The labels are not: somebody wrote
them. That makes them the one input no downstream gate can check -- `validate_kit` checks that a
score EXISTS, never that it is right. A question whose expected answer is not actually in the
corpus produces a confidently wrong accuracy figure, an error taxonomy built on it, and a cost per
correct answer derived from that, with nothing red anywhere.

So the labels get their own gate, and it checks the one thing that is mechanically checkable:
the answer has to actually be in the document the label points at. That does not prove a label is
GOOD -- only a human reading it can say that. It proves the label is not fiction, which is the
failure that costs the most and shows the least.

Checks:
  1. every `doc` exists in the corpus
  2. every `answer_contains` string really occurs in that document's extracted text
  3. no duplicate ids, no duplicate questions
  4. the set spans every format the corpus ships, so retrieval is not scored on the easy ones
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import boilerplate, extract                                     # noqa: E402

CORPUS = os.path.join(HERE, "data", "corpus")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")


def _norm(s):
    # Compare on collapsed whitespace. Extraction decides where the line breaks fall, and a label
    # that fails only because a PDF wrapped a sentence is a false alarm that trains people to
    # ignore this gate.
    return re.sub(r"\s+", " ", s).strip().lower()


def corpus_text():
    docs, fmts = {}, {}
    for name in sorted(os.listdir(CORPUS)):
        path = os.path.join(CORPUS, name)
        if not os.path.isfile(path) or name.startswith("."):
            continue
        doc_id = os.path.splitext(name)[0]
        text, fmt = extract.extract(path)
        docs[doc_id], fmts[doc_id] = text, fmt
    docs, _ = boilerplate.strip(docs, fmts)
    return {d: _norm(t) for d, t in docs.items()}, fmts


def load_labels(path=LABELS):
    rows = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit("labelled.jsonl line %d is not valid JSON: %s" % (n, e))
    return rows


def check(rows, docs, fmts):
    problems, seen_id, seen_q = [], set(), set()
    for r in rows:
        rid = r.get("id", "?")
        for field in ("id", "question", "doc", "answer_contains"):
            if not r.get(field):
                problems.append((rid, "missing field %r" % field))
        if rid in seen_id:
            problems.append((rid, "duplicate id"))
        seen_id.add(rid)
        q = _norm(r.get("question", ""))
        if q in seen_q:
            problems.append((rid, "duplicate question"))
        seen_q.add(q)
        doc = r.get("doc")
        if doc not in docs:
            problems.append((rid, "doc %r is not in the corpus" % doc))
            continue
        for frag in r.get("answer_contains", []):
            if _norm(frag) not in docs[doc]:
                problems.append((rid, "answer fragment not found in %s: %r" % (doc, frag[:60])))
    covered = {fmts[r["doc"]] for r in rows if r.get("doc") in fmts}
    missing = set(fmts.values()) - covered
    if missing:
        problems.append(("-", "no labelled question covers format(s): %s" % ", ".join(sorted(missing))))
    return problems


def main():
    rows = load_labels()
    docs, fmts = corpus_text()
    problems = check(rows, docs, fmts)
    by_fmt, by_doc = {}, {}
    for r in rows:
        f = fmts.get(r.get("doc"), "?")
        by_fmt[f] = by_fmt.get(f, 0) + 1
        by_doc[r.get("doc")] = by_doc.get(r.get("doc"), 0) + 1
    print("labelled set: %d rows over %d documents" % (len(rows), len(by_doc)))
    print("  by format: %s" % ", ".join("%s %d" % kv for kv in sorted(by_fmt.items())))
    if problems:
        print("\n  %d PROBLEM(S) -- the labels are not usable until these are fixed:" % len(problems))
        for rid, msg in problems:
            print("    %-6s %s" % (rid, msg))
        return 1
    print("  every answer fragment verified present in its source document.")
    print("\n  NOTE: this proves the labels are not fiction. It does not prove they are good.")
    print("  Only a human reading them can say that, and that review is not optional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
