"""Score two completed runs against each other by agreement. Free — reads results/, calls nobody.

    python -m evals.compare --a r001-<model-a> --b r002-<model-b>
    python -m evals.compare --a b000-regex --b r001-<model>     # baseline vs model

See evals/score.py for why agreement, not a gold match, is what this kit publishes.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals import score as SC                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def _load(run_id):
    path = os.path.join(RESULTS, "eval-%s.json" % run_id)
    if not os.path.exists(path):
        raise SystemExit("no such run: %s (looked for %s)" % (run_id, path))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None, help="run-id to save the comparison under "
                                                "(default: 'compare-<a>-<b>')")
    a = ap.parse_args()

    run_a, run_b = _load(a.a), _load(a.b)
    result = SC.agree(run_a["records"], run_b["records"], run_a["model"], run_b["model"])
    print(SC.agreement_text(result))

    out_id = a.out or ("compare-%s-%s" % (a.a, a.b))
    out = {"run_id": out_id, "kind": "compare", "run_a": a.a, "run_b": a.b, "agreement": result}
    path = os.path.join(RESULTS, "eval-%s.json" % out_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\n-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
