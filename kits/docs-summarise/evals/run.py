"""Run the summariser over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per document
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id b000 --lead             # the zero-cost baseline summariser
    python -m evals.run --run-id r001-x --limit 3        # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed. "Run once, for real" is the published claim of every kit here,
so the thing that spends must say what it is about to spend first.

⚑ AND THIS RUN PRODUCES NO SCORE. That is the difference from the two kits before it and it is not
an omission: the record it writes is EVIDENCE — six sections of prose per document, with what was
sent and what was dropped beside them — and the score comes later, from a person, through
`python -m evals.grade`. A run that printed a number here would have had to invent one.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                # noqa: E402
from src import config, summarise as SM         # noqa: E402
from src.summarise import MAX_TOKENS            # noqa: E402
from evals import baseline as B                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024):
    """A deterministic fake provider. It returns the rubric's keys filled with a marker string, so
    it exercises pack/prompt/parse/state end to end without a key. It is NOT a baseline — see
    --lead for one that is, and which a person actually grades."""
    sections = SM.sections_spec()
    out = {s["key"]: "[stub] %s — this reply came from a stub provider, not a model."
                     % s["name"] for s in sections}
    # One section deliberately refuses, so the absent-state path is exercised on every stub run.
    out[sections[-1]["key"]] = "Not stated in this document."
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--lead", action="store_true",
                    help="the zero-cost baseline: the document's own opening as the brief. No key, "
                         "no spend, graded by the same person against the same rubric so the two "
                         "are comparable.")
    ap.add_argument("--budget-tokens", type=int, default=0,
                    help="override the packer's input budget for this run")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    sections = SM.sections_spec()
    docs = SM.documents()
    if a.limit:
        docs = docs[:a.limit]
    if not docs:
        raise SystemExit("the corpus is empty. Run `python -m tools.fetch_corpus` then "
                         "`python -m tools.build_corpus` first.")

    if not a.stub and not a.lead:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free.")
        print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(len(docs))

    complete = stub_complete if a.stub else None
    records, lat, tin, tout, failures = {}, [], 0, 0, []
    first, dropped_any = None, 0
    t_all = time.time()
    for i, doc_id in enumerate(docs, 1):
        t0 = time.time()
        text = SM.load_doc(doc_id)
        try:
            if a.lead:
                r = {"sections": B.lead_summary(text, sections), "prompt_parts": [],
                     "pack": {"sent": [], "dropped": [], "fits": True, "chars_sent": 0,
                              "chars_total": len(text), "est_tokens_sent": 0,
                              "budget_tokens": 0},
                     "segment_coverage": 1.0, "section_count": 0,
                     "input_tokens": 0, "output_tokens": 0, "raw_text": "", "parsed": True}
            else:
                r = SM.summarise(cfg, text, sections, complete=complete,
                                 budget_tokens=a.budget_tokens or None)
        except Exception as exc:
            # A failed document is RECORDED, not retried into a bill and not dropped. A run that
            # silently skips its failures reports a result for the documents that happened to work.
            failures.append({"doc": doc_id, "error": str(exc)[:300]})
            print("  !! %-18s %s" % (doc_id, str(exc)[:80]))
            continue
        if not r.get("parsed", True):
            # It cost money and produced no brief. Scoring it as six absent sections would publish
            # a parsing defect as a model-quality figure, which is what UC002's first run did.
            # ⚑ SAY WHY, IN THE PROVIDER'S WORD. Until 2026-08-05 this said "(truncated?)" with a
            # question mark and left a person to compare output_tokens against the cap by eye —
            # across 36 failures in run r001, which is how a one-word answer the API had already
            # given became an inference. finish_reason == "length" IS the answer.
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": doc_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"),
                             "max_tokens": MAX_TOKENS,
                             "finish_reason": why,
                             "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-18s reply did not parse (%s output tokens, cap %d, finish_reason=%s)"
                  % (doc_id, r.get("output_tokens"), MAX_TOKENS, why))
            continue

        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[doc_id] = {"sections": r["sections"], "pack": r["pack"],
                           "segment_coverage": r["segment_coverage"],
                           "input_tokens": r.get("input_tokens"),
                           "output_tokens": r.get("output_tokens")}
        if r["pack"]["dropped"]:
            dropped_any += 1
        if first is None:
            first = r
        absent = sum(1 for s in r["sections"].values() if s["state"] != "written")
        print("  %3d/%-3d %-18s %5d ms   %d/%d sections written%s"
              % (i, len(docs), doc_id, lat[-1], len(sections) - absent, len(sections),
                 "   (%d section(s) dropped from the prompt)" % len(r["pack"]["dropped"])
                 if r["pack"]["dropped"] else ""))

    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "kind": "pipeline",
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("lead-baseline" if a.lead else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.lead else cfg.get("provider")),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        # ⚑ WHAT THE MODEL WAS GIVEN, PER RUN, BESIDE WHAT IT PRODUCED. A brief written from a
        # document the packer truncated is not a measurement of the model, and without this number
        # nothing downstream could tell the two apart.
        "documents_with_dropped_sections": dropped_any,
        "rubric_weights": {s["key"]: s["weight"] for s in sections},
        "null_baseline_score": B.null_score(sections),
        # ⚠︎ NO SCORES. This kit's verdict is a person's, and it is attached by evals/grade.py into
        # results/grades-<run-id>-<grader>.json. A `scores` key here holding anything at all would
        # be read as the run having been evaluated, which it has not.
        "records": records,
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "raw_text": (first["raw_text"] if first else ""),
        "max_tokens": MAX_TOKENS,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n%-30s %s" % ("run", a.run_id))
    print("%-30s %d of %d" % ("briefs written", len(records), len(docs)))
    print("%-30s %d" % ("documents packed incomplete", dropped_any))
    print("%-30s %s (a grader scoring everything 3 earns this)"
          % ("null baseline", out["null_baseline_score"]))
    print("-> %s" % os.path.relpath(path, HERE))
    print("\nNothing has been scored. Next: python -m evals.grade --run-id %s" % a.run_id)


if __name__ == "__main__":
    main()
