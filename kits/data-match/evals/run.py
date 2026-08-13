#!/usr/bin/env python3
"""The eval harness. One model call per candidate pair, scored by precision and recall — never one number.

    python3 -m evals.run --dry-run          # prints what it would spend, calls nothing
    python3 -m evals.run --run-id r012-data-match-flash

⚑ TWO NUMBERS, AND THE REASON IS THAT THE TWO MISTAKES COST DIFFERENT AMOUNTS. Precision answers "of the
pairs we merged, how many should have been?" — its failures are FALSE MERGES, which destroy records that
cannot be un-merged. Recall answers "of the pairs that should have merged, how many did?" — its failures
are MISSED MATCHES, which leave a duplicate for somebody to fix next quarter. An F-score is one number
that moves when either does, and it would let a kit that fuses real customers look like a kit that
merely misses a few duplicates. So this file publishes both and no combined figure.

⚑ THE SCORER IS SHARED WITH THE FREE FLOOR. `score_pair` is what `evals/baseline.py` calls too, so the
deterministic matcher and the model travel the identical path: same normalisation, same threshold logic,
same five outcomes. A baseline with its own scorer is a second opinion, not a floor.

⚑ THERE IS A REAL FREE HALF HERE, UNLIKE UC010 — AND IT IS THE POINT. `evals/baseline.py` scores a
working matcher with no key at all, so the model's number arrives beside a number anybody can reproduce
for nothing. Read that first.

THE FIVE OUTCOMES are `src/decide.py`'s, and `no_verdict` is deliberately not folded into
`missed_match`: an empty reply merges nothing, so it LOOKS cautious, and counting it as caution converts
a reliability failure into a quality figure.

⚠︎ WHAT THIS RUN DOES NOT MEASURE. It judges the 128 pairs blocking produced, not all 41,328 — so every
score here is conditional on `src/block.py` having generated the pair at all. Blocking recall is measured
(`src/block.py::stats`) and published beside the scores, because a blocker that drops true matches sets a
ceiling no model quality can lift.
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from evals.check_labels import load_labels, load_records                      # noqa: E402
from src import block, config, decide, prompt as pr, similarity              # noqa: E402

RESULTS = os.path.join(HERE, "results")
DEFAULT_THRESHOLD = 0.70


def score_pair(row, records, verdict, replied=True, threshold=DEFAULT_THRESHOLD):
    """One pair's outcome, from whichever decider is being measured.

    `verdict` is a word from `src/prompt.VERDICTS` for a model run, or None for the deterministic
    floor — in which case the similarity score alone decides. Everything else is identical between the
    two, which is what makes the comparison a comparison.
    """
    a, b = records[row["a"]], records[row["b"]]
    cmp = similarity.compare(a, b)
    out = decide.outcome(row["label"], cmp["score"], threshold, verdict, replied)
    return {"id": row["id"], "a": row["a"], "b": row["b"], "label": row["label"],
            "trap": row.get("trap", ""), "score": cmp["score"], "agreed": cmp["agreed"],
            "verdict": verdict, "replied": replied, "threshold": threshold, "outcome": out,
            "merged": out in ("merged_correct", "false_merge")}


def by_trap(rows):
    """Per-trap results, because "72% accurate" hides which KIND of hard case it fails. Each trap has a
    different owner: a nickname miss is a prompt problem, a twin merge is a threshold problem."""
    out = {}
    for r in rows:
        t = out.setdefault(r["trap"], {"pairs": 0, "wrong": 0, "outcomes": {}})
        t["pairs"] += 1
        t["outcomes"][r["outcome"]] = t["outcomes"].get(r["outcome"], 0) + 1
        if r["outcome"] in ("false_merge", "missed_match", "no_verdict"):
            t["wrong"] += 1
    return out


def summarise(rows):
    lat = sorted(r.get("model_latency_ms", 0) for r in rows if r.get("model_latency_ms"))
    t = decide.tally(rows)
    pct = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0
    # ⚑ `answered` IS THE DENOMINATOR BOTH RATES WERE DIVIDED BY, AND IT SHIPS WITH THEM — added
    # 2026-08-13, after r012 answered ONE pair of 78 and scored precision 100% / recall 100%.
    #
    # `no_verdict` is excluded from both rates on purpose, and that exclusion is still right: an
    # empty reply is a reliability failure, not a cautious answer. But it means the rates describe
    # only the pairs that replied, and nothing here said how many that was. One correct answer out
    # of 78 produced two perfect numbers, a reconciling taxonomy, and a run that read as flawless.
    #
    # A rate without its denominator is not a small omission on this kit — it is the difference
    # between "it matched everything correctly" and "it answered once". So it goes in the summary,
    # it goes in the printed headline, and the ingest refuses to publish a record where the pairs
    # that failed outnumber the pairs that answered.
    answered = len(rows) - t.get("counts", {}).get("no_verdict", 0)
    t.update({"model_latency_p50_ms": pct(lat, 0.50), "model_latency_p95_ms": pct(lat, 0.95),
              "answered": answered,
              "coverage": round(answered / len(rows), 4) if rows else None,
              "input_tokens_total": sum(r.get("input_tokens", 0) or 0 for r in rows),
              "output_tokens_total": sum(r.get("output_tokens", 0) or 0 for r in rows),
              "by_trap": by_trap(rows)})
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap the run while iterating")
    ap.add_argument("--run-id", default=None, help="stamped into the result file")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--dry-run", action="store_true",
                    help="print what this would spend and call nothing")
    a = ap.parse_args()

    records, labels = load_records(), load_labels()
    # Only pairs blocking would actually generate are judged — anything else measures a pipeline the
    # app does not run.
    cand = set(block.candidates(list(records.values())))
    rows = [p for p in labels
            if (min(p["a"], p["b"]), max(p["a"], p["b"])) in cand]
    skipped = [p["id"] for p in labels if p not in rows]
    if a.limit:
        rows = rows[:a.limit]
    cfg = config.load()

    sample = pr.render(records[rows[0]["a"]], records[rows[0]["b"]])
    print("data-match eval — %d labelled pair(s), %d judged after blocking"
          % (len(labels), len(rows)))
    print("  threshold: %.2f (nothing merges below it)" % a.threshold)
    print("  prompt: ~%d chars per pair, %d verdicts (%s)"
          % (len(sample), len(pr.VERDICTS), ", ".join(pr.VERDICTS)))
    print("  calls it will make: %d (one per pair, no retries counted)" % len(rows))
    if skipped:
        print("  NOT judged: %d labelled pair(s) blocking never generated — %s"
              % (len(skipped), " ".join(skipped[:8])))
    if a.dry_run:
        print("\n--dry-run: nothing was called and nothing was spent.")
        print("Read evals/baseline.py first — the free floor costs nothing and this number only means")
        print("something beside it.")
        return 0
    if not config.has_key(cfg):
        print("\nno API_KEY configured. The FREE floor still runs: python3 -m evals.baseline")
        return 1
    print("  model: %s / %s\n" % (cfg["provider"], cfg["model"]))

    from src.adapters import complete
    results = []
    for row in rows:
        user = pr.render(records[row["a"]], records[row["b"]])
        t0 = time.time()
        got = complete(cfg, pr.SYSTEM, user, max_tokens=16)
        ms = round((time.time() - t0) * 1000, 2)
        verdict = pr.parse(got["text"])
        rec = score_pair(row, records, verdict, replied=verdict is not None,
                         threshold=a.threshold)
        rec.update({"model_latency_ms": ms, "raw_response": got["text"],
                    # Kept so an empty reply can be diagnosed from the RESULTS FILE rather than from
                    # a second run. See the adapter's note: "length" is a truncation, "stop" is a
                    # model that said nothing, and reasoning billed inside the output budget is how
                    # a healthy-looking token count produces an empty string.
                    "finish_reason": got.get("finish_reason"),
                    "reasoning_chars": got.get("reasoning_chars"),
                    "input_tokens": got["input_tokens"], "output_tokens": got["output_tokens"],
                    "prompt_chars": len(user)})
        results.append(rec)
        print("  %-6s %-9s %-14s score %.2f  %s"
              % (row["id"], verdict or "(none)", rec["outcome"], rec["score"], row["trap"]))

    s = summarise(results)
    # THE DENOMINATOR PRINTS FIRST, above the rates rather than beside them, because the terminal is
    # where this run was first read as a success. `answered 1 of 78` on its own line is the sentence
    # that would have stopped it.
    print("\nanswered %d of %d pair(s) — the two rates below are computed over those %d ONLY"
          % (s["answered"], s["pairs"], s["answered"]))
    print("precision %s   recall %s   false merges %d   missed %d   no verdict %d"
          % ("%.1f%%" % (100 * s["precision"]) if s["precision"] is not None else "n/a",
             "%.1f%%" % (100 * s["recall"]) if s["recall"] is not None else "n/a",
             s["false_merges"], s["missed_matches"], s["no_verdict"]))
    if s["answered"] <= s["pairs"] - s["answered"]:
        # Not a warning about data quality — a refusal to let the run be read as a result at all.
        print("⚠︎  MORE PAIRS FAILED THAN ANSWERED. Those rates describe the exception, not the run,")
        print("   and the ingest will refuse this record. Check `finish_reason` on the rows before")
        print("   changing anything: a truncated reply and a silent model need different fixes.")
        bad = [r for r in results if r["outcome"] == "no_verdict"]
        why = {}
        for r in bad:
            why[r.get("finish_reason")] = why.get(r.get("finish_reason"), 0) + 1
        print("   finish_reason on the %d that gave no verdict: %s"
              % (len(bad), ", ".join("%s %d" % (k, v) for k, v in sorted(why.items(), key=str))))
    print("tokens in/out %d/%d   p50 %.0f ms   p95 %.0f ms"
          % (s["input_tokens_total"], s["output_tokens_total"],
             s["model_latency_p50_ms"], s["model_latency_p95_ms"]))
    print("\nby trap — which KIND of hard case it failed:")
    for trap, t in sorted(s["by_trap"].items(), key=lambda x: -x[1]["wrong"]):
        print("  %-16s %d/%d wrong   %s" % (trap, t["wrong"], t["pairs"],
                                            ", ".join("%s %d" % kv for kv in sorted(t["outcomes"].items()))))

    os.makedirs(RESULTS, exist_ok=True)
    run_id = a.run_id or "unstamped"
    payload = {
        "kind": "match",
        "run_id": run_id, "model": cfg["model"], "provider": cfg["provider"],
        "threshold": a.threshold,
        "dataset": {"rows": len(rows), "labelled": len(labels), "file": "data/labelled.jsonl",
                    "same": sum(1 for r in rows if r["label"] == "same"),
                    "different": sum(1 for r in rows if r["label"] == "different")},
        "corpus": {"records": len(records), "file": "data/records.csv",
                   "note": "generated by tools/build_corpus.py from a fixed seed, MIT"},
        "blocking": block.stats(list(records.values()), labels),
        "summary": s, "rows": results,
        "could_not_verify": [
            "Only the %d pairs blocking generated were judged, not all %d possible pairs. Every "
            "score is conditional on the blocker having produced the pair — blocking recall is "
            "published beside it for exactly that reason."
            % (len(rows), len(records) * (len(records) - 1) // 2),
            "The corpus is invented, so it contains the failure modes we thought to plant and no "
            "others. A real customer list will contain kinds of mess this set does not.",
            "No confidence figure is collected. Three kits here measured confidence numbers that "
            "carried no information, so this one does not publish one it would have to caveat away.",
        ]}
    out = os.path.join(RESULTS, "eval-%s.json" % re.sub(r"[^a-z0-9._-]+", "-", run_id.lower()))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print("\nwrote %s" % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
