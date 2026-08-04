"""Run the extractor over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per document
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 3        # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE. The plan is printed and the run stops for
confirmation unless --yes is passed. "Run once, for real" is the published claim of every kit
here, so the thing that spends must say what it is about to spend first.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from src.extract import MAX_TOKENS             # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["nct_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def stub_complete(cfg, system, user, max_tokens=1024):
    """A deterministic fake provider. It reads the header lines straight out of the prompt and
    returns null for everything else — so it exercises segment/select/prompt/parse/judge end to
    end and posts an honest, mediocre score. It is NOT a baseline: see --baseline for that."""
    import re
    out = {}
    m = re.search(r"NCT Number:\s*(\S+)", user)
    out["nct_id"] = m.group(1) if m else None
    m = re.search(r"Brief Title:\s*(.+)", user)
    out["brief_title"] = m.group(1).strip() if m else None
    return {"text": json.dumps(out), "input_tokens": len(user) // 4,
            "output_tokens": len(json.dumps(out)) // 4, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--baseline", action="store_true",
                    help="run the rules-and-regex extractor instead of a model: no key, no spend, "
                         "scored by the same judge so the two are comparable")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    fields = EX.load_fields()
    docs = EX.documents()
    if a.limit:
        docs = docs[:a.limit]

    if not a.stub and not a.baseline:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free.")
        # The plan line now carries the shared daily cap, because "57 calls" and "57 calls, 12 of
        # your 200 used today" are different decisions — and on a machine with no cap set at all
        # that is the single most useful thing this line can say before you type 'run'.
        print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        # Refuse the whole run up front when it cannot finish inside the cap, rather than dying
        # partway through with half a corpus paid for and no scoreable result file. The adapter
        # checks each call as well; this is the check that saves you the money, not just the call.
        BUDGET.check(len(docs))

    complete = stub_complete if a.stub else None
    records, lat, tin, tout, failures = {}, [], 0, 0, []
    first = None
    t_all = time.time()
    for i, nct in enumerate(docs, 1):
        t0 = time.time()
        try:
            if a.baseline:
                from evals import baseline as B
                r = {"fields": B.extract(EX.load_doc(nct), fields), "sections_used": [],
                     "prompt_parts": [], "input_tokens": 0, "output_tokens": 0, "raw_text": ""}
            else:
                r = EX.extract(cfg, EX.load_doc(nct), fields, complete=complete)
        except Exception as exc:
            # A failed document is RECORDED, not retried into a bill and not dropped. A run that
            # silently skips its failures reports a rate for the documents that happened to work.
            failures.append({"doc": nct, "error": str(exc)[:300]})
            print("  !! %-14s %s" % (nct, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            # Counted where every other lost document is counted. It cost money and produced no
            # answer -- exactly like a 503 -- and scoring it as nine misses would publish a
            # parsing defect as a model quality figure, which is what run 1 did.
            #
            # ⚠︎ AND THE REPLY IS KEPT. Run 2's four failures each reported 3000 output tokens
            # against a max_tokens of 3000 -- the reply had consumed its entire budget and been
            # cut off mid-JSON -- and the run recorded that number and threw the text away, so
            # the one question left open ("why does a nine-field record run to 3000 tokens?")
            # could not be answered from the artifact. A failure that discards its own evidence
            # is a failure you get to have twice.
            failures.append({"doc": nct, "error": "reply did not parse as JSON (truncated?) — "
                                                  "%d output tokens" % (r.get("output_tokens") or 0),
                             "output_tokens": r.get("output_tokens"),
                             "max_tokens": MAX_TOKENS,
                             "at_ceiling": (r.get("output_tokens") or 0) >= MAX_TOKENS,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-14s reply did not parse (%s output tokens, cap %d)"
                  % (nct, r.get("output_tokens"), MAX_TOKENS))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        records[nct] = r["fields"]
        # THE FIRST DOCUMENT THAT WORKED, not the first one attempted. `if i == 1` left `first`
        # unbound whenever document 1 failed and a later one succeeded -- `records` is non-empty,
        # so the guard below reads `first` and the run dies at the write step with a NameError,
        # after every call has been paid for.
        if first is None:
            first = r
        print("  %3d/%-3d %-14s %d ms" % (i, len(docs), nct, lat[-1]))

    golds = load_gold()
    scored = J.score(fields, records, golds)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    os.makedirs(RESULTS, exist_ok=True)
    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else ("rules-baseline" if a.baseline else cfg.get("model")),
        "provider": "stub" if a.stub else ("none" if a.baseline else cfg.get("provider")),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "by_field": scored["by_field"],
        "cells": scored["cells"],
        "prompt_parts": [{"name": q["name"], "chars": len(q["text"])}
                         for q in (first["prompt_parts"] if first else [])],
        "sections_used": (first["sections_used"] if first else []),
        # ⚑ ONE REAL REPLY, VERBATIM, BEFORE ANY PARSING. The kit standard's LLM lens asks for it
        # and this harness was the reason it could not be filled: `extract()` has always returned
        # `raw_text` and the write step dropped it, so four runs produced no example of what the
        # model actually sends back. It is the first successful document's, matching the prompt
        # parts and sections beside it, so the three describe one call rather than three.
        "raw_text": (first["raw_text"] if first else ""),
        "max_tokens": MAX_TOKENS,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-22s %s" % ("run", a.run_id))
    print("%-22s %d/%d  (%s)" % ("extraction accuracy",
                                 sum(1 for c in scored["cells"]
                                     if c["stated"] and c["verdict"] == "hit"),
                                 o["extraction_cells"], o["extraction_accuracy"]))
    print("%-22s %d/%d  (%s)" % ("refusal accuracy", o["refusal_cells"] - o["hallucinations"],
                                 o["refusal_cells"], o["refusal_accuracy"]))
    print("%-22s %d" % ("hallucinations", o["hallucinations"]))
    print("%-22s %s of %s returned" % ("values with a span",
                                       o["values_with_span"], o["values_returned"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
