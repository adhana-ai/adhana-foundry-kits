"""Compare two runs over the documents BOTH of them completed. Free — no key, no calls.

    python -m evals.compare eval-r002-deepseek-v4-flash.json eval-r003-deepseek-v4-pro.json

⚠︎ WHY THIS EXISTS, AND IT IS THE SAME MISTAKE TWICE. A run that loses documents — to a busy
provider, to a truncated reply — is scored over the ones that survived. Put two such runs side by
side and every rate is over a different denominator, so the comparison is not between two models,
it is between two models AND two corpora. This kit has already published one figure that way: the
rules baseline was scored over all 57 documents and the model over the 53 that returned, 353
extraction cells against 328, and the two were printed beside each other as though they answered
the same question. It was corrected by re-scoring, and this file is that correction made routine.

⚑ IT RE-DERIVES, IT DOES NOT RE-RUN. `overall` in evals/judge.py is a pure function of the run's
own `cells`, and every result file carries them. So restricting to the documents both runs
completed is arithmetic over committed evidence: exact, instant, and it spends nothing. Re-running
a model to answer a question the artifact already contains is paying twice for one measurement.

⚑ AND IT REPORTS THE COVERAGE DIFFERENCE RATHER THAN HIDING IT. Which documents each run lost is
itself a finding — the tier that completes the corpus is telling you something about its output
ceiling, not just about its accuracy — so the shared-set comparison is printed beside the counts
each run reported for itself, and neither replaces the other.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                       # noqa: E402
from evals import judge as J                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

# Every rate in `overall`, with the count it is measured over. A rate is never printed without it.
PAIRS = [("extraction_accuracy", "extraction_cells"),
         ("refusal_accuracy", "refusal_cells"),
         ("span_rate", "values_returned")]
COUNTS = ["hallucinations", "values_with_span"]


def overall_over(cells, fields, docs):
    """Re-derive `overall` from committed cells, restricted to `docs`.

    It rebuilds the aggregation rather than importing a private helper, because judge.score()
    takes records and these files carry cells — but every line below is the same arithmetic that
    file performs, and the shared-set totals are asserted against the full-set ones when the two
    sets are equal.
    """
    cs = [c for c in cells if c["doc"] in docs]
    ext_n = sum(1 for c in cs if c["stated"])
    ext_hit = sum(1 for c in cs if c["stated"] and c["verdict"] == "hit")
    ref_n = sum(1 for c in cs if not c["stated"])
    ref_ok = sum(1 for c in cs if not c["stated"] and c["verdict"] == "abstained")
    spanned = sum(1 for c in cs
                  if c["verdict"] in ("hit", "wrong") and c.get("spannable", True) and c["span"])
    valued = sum(1 for c in cs
                 if c["verdict"] in ("hit", "wrong", "hallucinated") and c.get("spannable", True))
    return {
        "documents": len(docs),
        "extraction_cells": ext_n,
        "extraction_accuracy": round(ext_hit / ext_n, 4) if ext_n else None,
        "refusal_cells": ref_n,
        "refusal_accuracy": round(ref_ok / ref_n, 4) if ref_n else None,
        "hallucinations": ref_n - ref_ok,
        "values_returned": valued,
        "values_with_span": spanned,
        "span_rate": round(spanned / valued, 4) if valued else None,
    }


def load(name):
    path = name if os.path.isabs(name) else os.path.join(RESULTS, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    runs = [load(a) for a in argv[:2]]
    sets = [{c["doc"] for c in r["cells"]} for r in runs]
    shared = sets[0] & sets[1]
    fields = EX.load_fields()

    print("%-30s %18s %18s" % ("", runs[0]["model"], runs[1]["model"]))
    print("%-30s %18s %18s" % ("run", runs[0]["run_id"], runs[1]["run_id"]))
    print("%-30s %18d %18d" % ("documents it completed", len(sets[0]), len(sets[1])))
    only = [sorted(sets[i] - sets[1 - i]) for i in (0, 1)]
    for i in (0, 1):
        if only[i]:
            print("  only in %s: %s" % (runs[i]["run_id"], ", ".join(only[i])))
    print("\nAS EACH RUN REPORTED ITSELF — different corpora, NOT comparable")
    for key, of in PAIRS:
        print("  %-28s %18s %18s"
              % (key, "%s of %s" % (runs[0]["scores"].get(key), runs[0]["scores"].get(of)),
                 "%s of %s" % (runs[1]["scores"].get(key), runs[1]["scores"].get(of))))

    print("\nOVER THE %d DOCUMENTS BOTH COMPLETED — this is the comparison" % len(shared))
    o = [overall_over(r["cells"], fields, shared) for r in runs]
    # If a run's own document set IS the shared set, the re-derivation must reproduce the figures
    # it published. That is the check that this arithmetic is the same arithmetic.
    for i in (0, 1):
        if sets[i] == shared:
            for key, _ in PAIRS:
                assert o[i][key] == runs[i]["scores"][key], \
                    "re-derivation disagrees with the run's own %s" % key
    for key, of in PAIRS:
        print("  %-28s %18s %18s"
              % (key, "%s of %s" % (o[0][key], o[0][of]), "%s of %s" % (o[1][key], o[1][of])))
    for key in COUNTS:
        print("  %-28s %18s %18s" % (key, o[0][key], o[1][key]))

    out = {"shared_documents": sorted(shared),
           "runs": [{"run_id": r["run_id"], "model": r["model"],
                     "completed": len(s), "as_reported": r["scores"], "over_shared": ov}
                    for r, s, ov in zip(runs, sets, o)]}
    path = os.path.join(RESULTS, "compare-%s-vs-%s.json" % (runs[0]["run_id"], runs[1]["run_id"]))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\n-> %s" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
