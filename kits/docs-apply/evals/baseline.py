#!/usr/bin/env python3
"""The free floor: an anchored find-and-replace that refuses when the anchor is not unique. $0.00.

    python3 evals/baseline.py

⚑ WHY THIS IS THE RIGHT FLOOR. It is what a careful engineer writes before reaching for a model,
and it is genuinely good at two of the three refusal families: it counts matches, so it declines
when a number appears twice (ambiguous) and when the clause named does not exist (missing).

⚠︎ AND IT IS STRUCTURALLY BLIND TO THE THIRD, WHICH IS THE POINT. It cannot see that clause 6 says
"any exception to clause 4" and that deleting clause 4 therefore leaves that reference pointing at
nothing. Seeing it requires reading the whole document and understanding that one clause refers to
another — the thing the model is supposed to be for. The kit is worth running because that
prediction is testable: if the model does NOT beat the floor on the contradiction family, the model
is not buying comprehension here, and this page will say so.

⚑ IT IS NOT A STRAW MAN. It parses clause numbers and headings, it handles the "In clause N (Head),
change X to Y" form the requests actually use, it refuses rather than guessing, and it never
touches a line it was not pointed at — so its collateral damage is structurally zero. A floor built
to lose proves nothing; this one is expected to win on collateral and lose on comprehension.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from evals.score import score_all, load_requests, load_doc  # noqa: E402

CLAUSE_RE = re.compile(r"^(\d+)\.\s+(.+)$")
IN_CLAUSE = re.compile(r"in clause (\d+)\s*\(([^)]+)\)[,:]?\s*change\s+(\S+)\s+to\s+(\S+?)\.?$",
                       re.I)
BARE_CHANGE = re.compile(r"change the (\S+) in this document to (\S+?)\.?$", re.I)
DELETE = re.compile(r"delete clause (\d+)", re.I)


def _clauses(text):
    """{number: (heading_line_index, body_line_index)} — parsed, not guessed at."""
    lines = text.split("\n")
    out = {}
    for i, line in enumerate(lines):
        m = CLAUSE_RE.match(line)
        if m and i + 1 < len(lines):
            out[int(m.group(1))] = (i, i + 1)
    return out, lines


def apply_request(text, request):
    """Return the edited document, or None to decline. Declining is a real answer here."""
    clauses, lines = _clauses(text)

    m = IN_CLAUSE.search(request.strip())
    if m:
        n, _head, old, new = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        if n not in clauses:
            return None                       # missing: the clause named is not in the document
        _hi, bi = clauses[n]
        if lines[bi].count(old) != 1:
            return None                       # not a unique anchor inside the target clause
        # ⚑ ONLY THE TARGET LINE IS TOUCHED. That is the whole discipline of a rules editor and it
        # is why its collateral damage is zero by construction.
        out = list(lines)
        out[bi] = out[bi].replace(old, new, 1)
        return "\n".join(out)

    m = BARE_CHANGE.search(request.strip())
    if m:
        old, new = m.group(1), m.group(2)
        hits = [i for i, ln in enumerate(lines) if re.search(r"\b%s\b" % re.escape(old), ln)]
        if len(hits) != 1:
            return None                       # ambiguous (or absent): refuse rather than pick one
        out = list(lines)
        out[hits[0]] = re.sub(r"\b%s\b" % re.escape(old), new, out[hits[0]], count=1)
        return "\n".join(out)

    m = DELETE.search(request.strip())
    if m:
        n = int(m.group(1))
        if n not in clauses:
            return None
        # ⚠︎ IT DELETES. It has no way to know clause 6 refers to clause 4, so it does exactly what
        # it was told — which is the failure this family is planted to expose, and it is left in
        # rather than special-cased, because special-casing it would be writing the answer into the
        # floor and calling it a measurement.
        hi, bi = clauses[n]
        out = [ln for i, ln in enumerate(lines) if i not in (hi, bi)]
        return "\n".join(out)

    return None                               # a form it does not understand: decline


def main():
    rows = load_requests(HERE)
    t0 = time.time()
    produced, lat = {}, []
    for r in rows:
        before = load_doc(HERE, "corpus", r["doc_id"])
        s = time.time()
        produced[r["doc_id"]] = apply_request(before, r["request"])
        lat.append(int((time.time() - s) * 1000))
    res = score_all(rows, produced, HERE)
    res.update({
        "run_id": "b000-docs-apply-rules", "stub": False, "model": "rules-baseline", "provider": "none",
        "documents": len(rows), "answered": len(rows), "failures": [],
        "latency_p50_ms": sorted(lat)[len(lat) // 2], "latency_p95_ms": sorted(lat)[int(len(lat) * .95)],
        "wall_seconds": round(time.time() - t0, 2),
        "input_tokens_total": 0, "output_tokens_total": 0,
    })
    out = os.path.join(HERE, "results", "eval-b000-docs-apply-rules.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    sc = res["scores"]
    print("b000-docs-apply-rules  applied %.1f%%  clean %.1f%%  collateral %d line(s)  "
          "refusal %.1f%%  unsafe writes %d"
          % (100 * sc["edit_applied"], 100 * sc["edit_clean"], sc["collateral_lines"],
             100 * sc["refusal_accuracy"], sc["unsafe_writes"]))
    for fam, v in res["by_family"].items():
        print("   %-14s %d/%d = %.1f%%" % (fam, v["correct"], v["n"], v["pct"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
