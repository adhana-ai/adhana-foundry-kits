"""What blocking plus the weighted exact-match floor catches, with no model anywhere. Free. No
key, no dependency, no network.

    python -m evals.baseline

Reuses src/block.py's own candidate generation (the SAME code the real pipeline runs) and
src/decide.py's own threshold, so baseline and model are compared on identical candidate sets and
scored by the identical function (evals/scoring.py) -- the gap measured between them is entirely in
which pairs get counted as analogs, not in who saw a smaller haystack or a friendlier grader.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import block, decide as D, match as M, similarity as SIM   # noqa: E402
from evals import scoring as S                                        # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-exact-match-floor")
    a = ap.parse_args()

    history = M.load_history()
    requests = M.load_requests()
    gold = M.load_gold()

    rows_by_request = {}
    for req in requests:
        cand = block.candidates(req, history)
        per_candidate = []
        for c in cand:
            sim = SIM.score(req, c)
            merged = D.counts_as_analog(sim)                 # no verdict -- the pure floor
            per_candidate.append({"event_id": c["event_id"], "verdict": None, "reason": None,
                                  "similarity_score": sim, "counted": merged})
        rows_by_request[req["request_id"]] = per_candidate

    scored = S.score(rows_by_request, gold, expects_verdict=False)
    out = {"run_id": a.run_id, "baseline": True, "requests": len(requests),
          "pairs": scored["overall"]["pairs_scored"], "scores": scored["overall"]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("exact-match floor over %d requests, %d pairs" % (len(requests), o["pairs_scored"]))
    print("precision : %s%%" % o["precision_pct"])
    print("recall    : %s%%" % o["recall_pct"])
    print("f1        : %s%%" % o["f1_pct"])
    print("counts    : %s" % o["counts"])
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
