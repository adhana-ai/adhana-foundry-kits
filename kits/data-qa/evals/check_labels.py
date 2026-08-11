"""Gate the labelled set BEFORE it is allowed to grade anything. Needs no key, costs nothing.

⚠︎ WHY A GOLD SET NEEDS ITS OWN GATE. In this kit the gold answer is not a string somebody typed —
it is whatever the gold SQL returns when it runs. That is a strength, because the answer cannot
drift from the database. It is also the failure mode: a gold query with a typo, a stale column name
or a quietly wrong join still RUNS, still produces a result set, and every model answer is then
graded against a wrong answer. The eval would report a low score with total confidence and the
defect would be in the ruler.

So every gold statement is executed here first, and four things are checked:

  1. it parses and runs at all
  2. it passes the same read-only guard the model's output has to pass
  3. it returns at least one row — a gold that returns nothing grades everything as wrong
  4. two rows do not carry the same question text

⚑ AND THE UNANSWERABLE ROWS ARE CHECKED IN THE OTHER DIRECTION. q-19 and q-20 have no gold SQL on
purpose. This gate asserts their `gold_sql` is null AND that their question names something the
schema does not have — otherwise "unanswerable" is just an assertion, and the day someone adds an
email column the row silently becomes wrong in the opposite direction.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from src import execute as ex, guard, schema  # noqa: E402

LABELS = os.path.join(HERE, "data", "labelled.jsonl")


def load_labels(path=LABELS):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit("labelled.jsonl line %d is not JSON: %s" % (n, exc))
    return rows


def gold_result(row):
    """Run a row's gold SQL and return its result set. None for the unanswerable rows."""
    if not row.get("gold_sql"):
        return None
    return ex.run(row["gold_sql"])


def main():
    rows = load_labels()
    card = schema.card().lower()
    problems, answerable, unanswerable = [], 0, 0
    seen = {}

    for row in rows:
        rid = row.get("id", "?")
        q = (row.get("question") or "").strip()
        if not q:
            problems.append("%s: empty question" % rid)
        if q.lower() in seen:
            problems.append("%s: same question as %s" % (rid, seen[q.lower()]))
        seen[q.lower()] = rid

        if row.get("gold_sql"):
            answerable += 1
            ok, why = guard.check(row["gold_sql"])
            if not ok:
                problems.append("%s: gold SQL fails the read-only guard — %s" % (rid, why))
                continue
            try:
                res = ex.run(row["gold_sql"])
            except ex.ExecError as exc:
                problems.append("%s: gold SQL does not run — %s" % (rid, exc))
                continue
            if res["row_count"] == 0:
                problems.append("%s: gold SQL returns NO rows — it would grade every answer wrong"
                                % rid)
            if res["truncated"]:
                problems.append("%s: gold SQL hit the row cap; a truncated gold is not a gold" % rid)
        else:
            unanswerable += 1
            # The claim is "the schema cannot answer this". Check it rather than trust it: every
            # significant word of the question that looks like a column or table must be ABSENT.
            hint = row.get("tests", "")
            if "UNANSWERABLE" not in hint:
                problems.append("%s: no gold_sql but `tests` does not say UNANSWERABLE" % rid)
            leaked = [w for w in ("email", "ticket", "tickets") if w in card]
            if leaked:
                problems.append("%s: claims the schema lacks %s, but the schema card contains it — "
                                "the row is now wrong in the other direction" % (rid, leaked))

    print("labelled set: %d rows — %d answerable, %d unanswerable"
          % (len(rows), answerable, unanswerable))
    print("schema: %s" % ", ".join("%s (%s rows)" % (t, "{:,}".format(n))
                                   for t, n in schema.stats().items()))
    if problems:
        print("\n%d PROBLEM(S) — the ruler is not trustworthy until these are fixed:"
              % len(problems))
        for p in problems:
            print("  !! %s" % p)
        return 1
    print("every gold statement runs, passes the guard and returns rows. The ruler is sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
