#!/usr/bin/env python3
"""What you get without a model. Run this BEFORE reading any score this kit produces.

    python3 -m evals.baseline

⚑ THE FLOOR COMES FIRST, ALWAYS. An accuracy of 80% means nothing until you know what a constant
scores on the same 20 questions. On a text-to-SQL set the floor is not obviously zero, and it is
not obviously non-zero either: two of these questions have NO gold answer, so a strategy that
refuses everything and reads nothing already banks them. Publishing the model's number without
that beside it would report 80% as 80 points of understanding when part of it is arithmetic
anybody gets for free.

⚑ AND THIS FLOOR IS FREE IN THE STRICT SENSE — not "cheap", not "one small call". Every strategy
below is a constant string. Nothing is sent anywhere, so this file can be re-run as often as you
like and its numbers cost nothing to reproduce. That matters on this kit more than on most,
because `evals/run.py` has NO free offline half: scoring a generated query requires generating
one, which requires the model. This is the only number here that can be checked without spending,
which is exactly why it is committed rather than quoted.

⚠︎ THE FLOORS ARE SCORED BY `evals/run.py::score_row`, UNCHANGED. A baseline with its own scorer
is not a baseline, it is a second opinion — the floor has to travel the identical path the model's
answer travels, through the same guard, the same executor and the same execution match, or the
comparison is between two rulers rather than between two answers.

Three constants, none of which sends a request:

    always-refuse   reply `CANNOT ANSWER` to every question. Correct exactly on the questions that
                    have no answer, and it never touches the database.
    count-star      reply `SELECT COUNT(*) FROM customers` to everything — the single most likely
                    query shape on this schema, guessed with no reading of the question at all.
    select-all      reply `SELECT * FROM orders` to everything. It runs, it returns rows, and it
                    is wrong: the shape that proves "the query executed" is not "the answer is
                    right", which is the confusion execution match exists to remove.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels                                   # noqa: E402
from evals.run import score_row                                             # noqa: E402
from src import schema                                                       # noqa: E402

# Each floor is a constant answer, exactly as a model would have returned it — a string, before
# any of them has been near the guard. Nothing here inspects the question.
STRATEGIES = (
    ("always-refuse", "CANNOT ANSWER",
     "reads nothing, answers nothing, and banks the two unanswerable questions"),
    ("count-star", "SELECT COUNT(*) FROM customers",
     "the most likely single query on this schema, guessed without reading the question"),
    ("select-all", "SELECT * FROM orders",
     "a statement that runs and returns rows and is still wrong"),
)


def score(constant, labels, card):
    """Run one constant through the real scorer and return its record."""
    rows, causes = [], {}
    for row in labels:
        out = score_row(row, constant, card)
        out["id"] = row["id"]
        rows.append(out)
        if out["cause"]:
            causes[out["cause"]] = causes.get(out["cause"], 0) + 1
    correct = sum(1 for r in rows if r["correct"])
    return {"answer": constant,
            "correct": correct,
            "rows": len(rows),
            "accuracy": round(correct / len(rows), 4) if rows else 0.0,
            "causes": causes,
            "correct_ids": [r["id"] for r in rows if r["correct"]]}


def main():
    labels = load_labels()
    card = schema.card()
    out = {"kind": "baseline",
           "dataset": {"file": "data/labelled.jsonl", "rows": len(labels)},
           "cost_usd": 0.0,
           "calls": 0,
           "note": "Constant answers scored by evals/run.py::score_row. No model was called.",
           "floors": {}}

    print("FLOORS — %d questions, 0 model calls, $0.00\n" % len(labels))
    for name, constant, why in STRATEGIES:
        rec = score(constant, labels, card)
        rec["why"] = why
        out["floors"][name] = rec
        print("  %-14s %5.1f%%  %2d/%d correct   %s"
              % (name, rec["accuracy"] * 100, rec["correct"], rec["rows"],
                 ", ".join("%s %d" % (k, v) for k, v in sorted(rec["causes"].items())) or "—"))
        print("  %-14s %s" % ("", why))
        if rec["correct_ids"]:
            print("  %-14s correct on: %s" % ("", " ".join(rec["correct_ids"])))
        print()

    best = max(out["floors"].values(), key=lambda r: r["accuracy"])
    out["highest_floor"] = best["accuracy"]
    print("HIGHEST FLOOR: %.1f%%. Any model score must be read against this, not against zero."
          % (best["accuracy"] * 100))
    path = os.path.join(HERE, "results", "baseline.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
