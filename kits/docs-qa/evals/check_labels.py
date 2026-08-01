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
  5. no fragment is longer than MAX_FRAGMENT_WORDS -- see below

WHY CHECK 5 EXISTS, AND THE MEASUREMENT THAT PUT IT THERE.
Check 2 has a hole big enough to invert a headline number, and it stayed green through it. It
proves a fragment is IN the document; it has never proved the fragment ANSWERS THE QUESTION. A
section heading is in the document. So `answer_contains: ["querying an r*tree index"]` passed the
gate, and then marked every correct prose answer wrong, because no answer to "how do you query an
R*Tree index?" contains that document's table-of-contents entry.

Measured on the first capture run -- 50 rows x 2 models, 100 graded answers:

    longest fragment in the row     graded correct
      1-2 words                          80%
      3-4 words                          43%
      5-6 words                          45%
      7+  words                          33%

The model cannot see the label. That slide is the RULER, not the model: the longer the string you
require verbatim, the less likely a correct paraphrase happens to contain it, so measured
"accuracy" falls as label verbosity rises. Left alone, the published number would have described
the authoring style of the labelled set and been read as a property of the model.

A word cap is a proxy for the real rule -- a fragment must be the DISCRIMINATING content, a number,
a term, a stem -- and a proxy is what is mechanically checkable. Judging whether a short fragment
is the RIGHT short fragment is still a human read, and check 2's closing note still applies.

An LLM-as-judge grader would measure correctness directly rather than by proxy. That is the honest
next instrument, and it is deliberately not this one: a judge costs a call per row and brings its
own error, so it is a decision to take with numbers in hand, not a default.
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

# Four, not two, and the gap is deliberate. The measurement says 1-2 words grades most reliably,
# but some answers genuinely need a short phrase -- "no reads or writes", "name of the object" --
# and a cap that forbids the correct answer would be a gate that cannot go green.
MAX_FRAGMENT_WORDS = 4
_FRAG_WORD = re.compile(r"[A-Za-z0-9:.*_-]+")


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
            n = len(_FRAG_WORD.findall(frag))
            if n > MAX_FRAGMENT_WORDS:
                problems.append((rid, "fragment is %d words, cap is %d -- grade a paraphrase, not "
                                      "a quotation: %r" % (n, MAX_FRAGMENT_WORDS, frag[:60])))
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
