"""Check the rubric before anything spends money on it. No key, no network, no cost.

⚑ WHY A CHECKER FOR A JSON FILE. The rubric is the input, the gold and the cost driver of this kit
all at once, and every one of its failure modes is SILENT. Weights that sum to 97 make every
published score wrong by 3%, and nothing would say so — the arithmetic works, the page renders, and
the null baseline moves off 60 without anyone noticing it moved. A duplicated key overwrites a
section in the prompt and the brief comes back a section short, which reads as the model skipping
one. A missing `asks` line sends the model a heading with no instruction.

It is the counterpart of docs-extract's `check_labels.py`, and it exists for the same reason: the
thing you are measuring against has to be checked before you pay to measure against it.

    python -m evals.check_rubric
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import summarise as SM                 # noqa: E402

# The weights must total this. Not "roughly" — every score this kit publishes is out of it, and
# `evals/baseline.py` computes the null floor from it.
TOTAL = 100


def check():
    r = SM.load_rubric()
    secs = r.get("sections") or []
    bad = []

    if not secs:
        return ["the rubric has no sections"]

    total = sum(s.get("weight") or 0 for s in secs)
    if total != TOTAL:
        bad.append("weights total %s, not %s — every published score is out of that total, and "
                   "the null baseline is computed from it" % (total, TOTAL))

    seen = set()
    for i, s in enumerate(secs):
        where = s.get("key") or "section %d" % i
        for f in ("key", "name", "weight", "asks"):
            if not s.get(f):
                bad.append("%s: missing %r" % (where, f))
        if s.get("key") in seen:
            bad.append("%s: duplicate key — the second one silently overwrites the first in the "
                       "prompt and the brief comes back a section short" % where)
        seen.add(s.get("key"))
        w = s.get("weight")
        if isinstance(w, (int, float)) and w <= 0:
            bad.append("%s: weight %s — a section worth nothing is a section that should not be "
                       "in a fixed shape" % (where, w))

    scale = r.get("scale") or {}
    anchors = scale.get("anchors") or {}
    lo, hi = scale.get("min"), scale.get("max")
    if lo is None or hi is None:
        bad.append("scale is missing min/max")
    else:
        for n in range(lo, hi + 1):
            if str(n) not in anchors:
                # An unanchored point on the scale is where two graders quietly disagree, and
                # agreement is the figure this kit's Evals board exists to print.
                bad.append("scale point %d has no anchor — two graders will read it differently "
                           "and the agreement figure will be measuring the scale, not the briefs"
                           % n)
    return bad


def main():
    bad = check()
    if bad:
        print("RUBRIC: %d problem(s)" % len(bad))
        for b in bad:
            print("  - %s" % b)
        raise SystemExit(1)
    r = SM.load_rubric()
    secs = r["sections"]
    print("RUBRIC: clean — %d sections, weights total %d, scale %d-%d fully anchored"
          % (len(secs), sum(s["weight"] for s in secs), r["scale"]["min"], r["scale"]["max"]))
    print("  a grader scoring everything %d earns %.1f of %d before reading anything"
          % (3, sum(s["weight"] * 3 / 5.0 for s in secs), TOTAL))


if __name__ == "__main__":
    main()
