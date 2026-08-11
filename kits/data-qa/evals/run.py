"""The eval harness. Scores by EXECUTION MATCH and classifies every failure.

WHAT EXECUTION MATCH IS, AND WHY IT IS THE RIGHT RULER HERE.
The model's answer is a query, and there is no single correct query — `>= '2024-01-01'` and
`strftime('%Y', d) = '2024'` are the same answer written twice. Comparing SQL strings would score
correct answers wrong. So the query is RUN and its result set is compared against the result set of
the gold query. Two queries agree if the data agrees.

⚠︎ AND WHERE THAT RULER IS BLUNT, STATED RATHER THAN HIDDEN. On a small database two different
queries can return the same rows by coincidence — a wrong join that happens to produce the right
count. Execution match cannot tell that from understanding, and this kit does not pretend it can:
it goes in `could_not_verify` on the published report. The honest claim is "the answer was right",
never "the model understood the schema".

⚑ THERE IS NO FREE HALF, AND SAYING SO IS BETTER THAN INVENTING ONE.
UC001 can score retrieval offline because retrieval is pure code. Here every score needs a
generated query, and generating one needs the model. `--dry-run` therefore prints exactly what a
run would cost and calls nothing; the app still renders the recorded run with no key at all. What
is NOT done is a fake offline path that scores the gold SQL against itself and reports 100%.

THE TAXONOMY. A single accuracy figure says the pipeline is wrong and nothing about where. Each
cause below has a different owner:

  refused_by_guard  the model wrote a statement that writes.   Fix: src/prompt.py — SYSTEM
  invalid_sql       it ran and SQLite rejected it.             Fix: src/prompt.py, or the model
  wrong_result      it ran and the rows disagree with gold.    Fix: the model, or the schema card
  false_refusal     said CANNOT ANSWER to an answerable one.   Fix: src/prompt.py — SYSTEM
  missed_refusal    invented schema for an unanswerable one.   Fix: src/prompt.py, or the model
  timed_out         the query never finished.                  Fix: src/execute.py bounds

`missed_refusal` is the one worth watching. It means the model wrote confident SQL against columns
that do not exist — the database equivalent of a fabricated citation, and the reason two rows of
the labelled set have no gold answer at all.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels                                   # noqa: E402
from src import config, execute as ex, guard, prompt as pr, schema           # noqa: E402

RESULTS = os.path.join(HERE, "results")


def score_row(row, sql_text, card):
    """Decide one row. Returns the fields merged into the result record."""
    out = {"sql": sql_text, "cause": None, "correct": False}
    answerable = bool(row.get("gold_sql"))
    refused = sql_text.strip().upper().startswith(pr.CANNOT)

    if refused:
        # A refusal is correct exactly when there is no gold answer.
        out["correct"] = not answerable
        out["cause"] = None if out["correct"] else "false_refusal"
        return out
    if not answerable:
        out["cause"] = "missed_refusal"
        return out

    ok, why = guard.check(sql_text)
    if not ok:
        out["cause"] = "refused_by_guard"
        out["guard_reason"] = why
        return out

    try:
        got = ex.run(sql_text)
    except ex.ExecError as exc:
        out["cause"] = "timed_out" if "timed out" in str(exc) else "invalid_sql"
        out["error"] = str(exc)
        return out

    gold = ex.run(row["gold_sql"])
    out["correct"] = ex.same(got, gold, sql_text, row["gold_sql"])
    out["rows_returned"] = got["row_count"]
    out["gold_rows"] = gold["row_count"]
    out["exec_ms"] = got["ms"]
    if not out["correct"]:
        out["cause"] = "wrong_result"
    return out


def summarise(results):
    n = len(results)
    answered = [r for r in results if r.get("answered")]
    causes = {}
    for r in results:
        if r["cause"]:
            causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    s = {"rows": n, "answered": len(answered), "causes": causes}
    if answered:
        lat = sorted(r["model_latency_ms"] for r in answered)
        s.update({
            "accuracy": round(sum(r["correct"] for r in answered) / len(answered), 4),
            "model_latency_p50_ms": lat[len(lat) // 2],
            "model_latency_p95_ms": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
            "input_tokens_total": sum(r.get("input_tokens") or 0 for r in answered),
            "output_tokens_total": sum(r.get("output_tokens") or 0 for r in answered),
        })
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap the run while iterating")
    ap.add_argument("--run-id", default=None, help="stamped into the result file")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what this would spend and call nothing")
    a = ap.parse_args()

    rows = load_labels()
    if a.limit:
        rows = rows[:a.limit]
    card = schema.card()
    cfg = config.load()

    _, sample_user, _ = pr.assemble(rows[0]["question"], card)
    print("data-qa eval — %d question(s), %d answerable" % (len(rows), sum(1 for r in rows if r.get("gold_sql"))))
    print("  schema card: %d chars, FIXED on every question" % len(card))
    print("  prompt: ~%d chars per question" % len(sample_user))
    print("  calls it will make: %d (one per question, no retries counted)" % len(rows))
    if a.dry_run:
        print("\n--dry-run: nothing was called and nothing was spent.")
        return 0
    if not config.has_key(cfg):
        print("\nno API_KEY configured. This kit has no free scoring half — every score needs a\n"
              "generated query. Set a key, or open the app to read the recorded run.")
        return 1
    print("  model: %s / %s\n" % (cfg["provider"], cfg["model"]))

    from src.adapters import complete
    results = []
    for row in rows:
        system, user, parts = pr.assemble(row["question"], card)
        rec = {"id": row["id"], "question": row["question"], "tests": row.get("tests", ""),
               "answerable": bool(row.get("gold_sql")), "gold_sql": row.get("gold_sql")}
        t0 = time.time()
        got = complete(cfg, system, user)
        rec["model_latency_ms"] = round((time.time() - t0) * 1000, 2)
        sql_text = pr.clean(got["text"])
        rec.update({"answered": True, "raw_response": got["text"],
                    "input_tokens": got["input_tokens"], "output_tokens": got["output_tokens"],
                    "prompt_chars": len(user), "prompt_parts": len(parts)})
        rec.update(score_row(row, sql_text, card))
        results.append(rec)
        print("  %-6s %-14s %s" % (row["id"], "correct" if rec["correct"] else (rec["cause"] or "?"),
                                   (sql_text.replace("\n", " ")[:64])))

    s = summarise(results)
    print("\naccuracy %.1f%%   p50 %.0f ms   p95 %.0f ms   tokens in/out %d/%d"
          % (100 * s["accuracy"], s["model_latency_p50_ms"], s["model_latency_p95_ms"],
             s["input_tokens_total"], s["output_tokens_total"]))
    if s["causes"]:
        print("\nfailures by cause — recorded, not hidden:")
        for c, n in sorted(s["causes"].items(), key=lambda x: -x[1]):
            ids = [r["id"] for r in results if r["cause"] == c]
            print("  %-18s %2d   %s" % (c, n, " ".join(ids)))

    os.makedirs(RESULTS, exist_ok=True)
    run_id = a.run_id or "unstamped"
    payload = {
        "run_id": run_id,
        "model": cfg["model"], "provider": cfg["provider"],
        "dataset": {"rows": len(rows), "file": "data/labelled.jsonl"},
        "corpus": {"tables": schema.stats(), "schema_card_chars": len(card),
                   "database": "data/shop.db (generated, MIT, fixed seed)"},
        "summary": s, "rows": results,
        "could_not_verify": [
            "Execution match cannot distinguish understanding from coincidence: on a database this "
            "size a wrong query can return the right rows by luck. The claim is 'the answer was "
            "right', never 'the model understood the schema'.",
            "q-04 is genuinely ambiguous in English — 'average revenue per customer' may or may not "
            "count the 112 customers who ordered nothing. The gold picks one reading and says so; a "
            "model taking the other reading is scored wrong here and is not obviously mistaken.",
            "No free offline half exists: every score needs a model call, so nothing here was "
            "verified without spending.",
        ]}
    out = os.path.join(RESULTS, "eval-%s.json" % re.sub(r"[^a-z0-9._-]+", "-", run_id.lower()))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
