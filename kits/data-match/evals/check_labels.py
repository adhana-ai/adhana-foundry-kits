#!/usr/bin/env python3
"""Read the labelled pairs, and refuse a set that cannot be scored honestly.

    python3 -m evals.check_labels

⚑ RUN THIS BEFORE ANY RUN, PAID OR FREE. Every score this kit publishes is `==` against these labels,
so a defect here is a defect in every number downstream and it is invisible once the run has started.
Cheap to check, expensive to discover late.

What it refuses, and why each one has to be an error rather than a warning:

    a pair whose record ids do not exist      scores against nothing
    a pair comparing a record with itself     trivially SAME, inflates recall for free
    a duplicate pair                          double-counts one judgement
    a label outside {same, different}         the scorer has no branch for it
    a set with no `same` pairs                recall has a zero denominator and prints as 0%
    a set with no `different` pairs           precision cannot be wrong, so it means nothing

⚠︎ THE BALANCE IS REPORTED EVEN WHEN IT IS FINE. A matcher evaluated on a mostly-different set can look
excellent by answering DIFFERENT to everything, so the proportion belongs beside every score rather than
in a footnote — this is the `balanced_set` field the spec requires for exactly that reason.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

RECORDS = os.path.join(HERE, "data", "records.csv")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")


def load_records():
    """id -> record. person_id is read but never given to the model or the floor: it is ground truth
    about the corpus, not a field a real customer list would carry."""
    with open(RECORDS, encoding="utf-8") as fh:
        return {r["id"]: r for r in csv.DictReader(fh)}


def load_labels():
    out = []
    with open(LABELS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def check(records, labels):
    problems = []
    seen = set()
    for p in labels:
        pid = p.get("id", "?")
        for side in ("a", "b"):
            if p.get(side) not in records:
                problems.append("%s: record %r does not exist" % (pid, p.get(side)))
        if p.get("a") == p.get("b"):
            problems.append("%s: compares a record with itself" % pid)
        key = tuple(sorted((p.get("a"), p.get("b"))))
        if key in seen:
            problems.append("%s: duplicate pair %s" % (pid, list(key)))
        seen.add(key)
        if p.get("label") not in ("same", "different"):
            problems.append("%s: label %r is outside {same, different}" % (pid, p.get("label")))
    same = sum(1 for p in labels if p.get("label") == "same")
    if not same:
        problems.append("no `same` pairs — recall has a zero denominator")
    if same == len(labels):
        problems.append("no `different` pairs — precision cannot be wrong, so it means nothing")
    return problems, same


def main():
    records, labels = load_records(), load_labels()
    problems, same = check(records, labels)
    traps = {}
    for p in labels:
        traps[p.get("trap", "?")] = traps.get(p.get("trap", "?"), 0) + 1

    print("LABELS — %d pairs over %d records" % (len(labels), len(records)))
    print("  balance          %d same / %d different  (%.0f%% same)"
          % (same, len(labels) - same, 100.0 * same / len(labels) if labels else 0))
    for k, v in sorted(traps.items()):
        print("    %-16s %d" % (k, v))
    if problems:
        print("\nREFUSED — %d problem(s):" % len(problems))
        for p in problems[:20]:
            print("  - %s" % p)
        return 1
    print("\n  clean — every pair resolves, no duplicates, both labels present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
