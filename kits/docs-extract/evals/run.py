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
from src import adapters                        # noqa: E402
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
    # ⚑ THE KNOB THE SIBLING KIT'S EVIDENCE POINTS AT. docs-summarise measured its own ceiling
    # failures spending a MEDIAN OF 100% of the output budget on a reasoning pass nobody asked for
    # -- `thinking` defaults to ENABLED on this model family -- and disabling it took that kit from
    # 29 of 42 to 42 of 42 with a maximum output of 1,419 tokens against a cap of 8,000.
    #
    # This kit has the same shape of failure and no diagnosis: run 2's four failures each returned
    # exactly 3000 output tokens against a cap of 3000, and nothing here has ever recorded
    # `token_details`, so the cause is a hypothesis rather than a measurement.
    #
    # ⚠︎ WIRED, NOT CONCLUDED. This flag makes the experiment possible; it does not report its
    # result, and no claim about this kit's ceiling may be made until a run has been fired.
    ap.add_argument("--no-thinking", action="store_true",
                    help="send thinking={'type':'disabled'}. Provider-documented for "
                         "deepseek-v4-flash, where it is ON by default. Recorded in the run as a "
                         "comparability guard: reasoning-off is a DIFFERENT SYSTEM, not a tuned "
                         "one, and its runs may not be differenced against reasoning-on runs.")
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
    # ⚠︎ ONLY THE PAID PATH CAN SEND IT, AND SAYING SO IS THE POINT. `stub_complete` takes no
    # `thinking` argument and the rules baseline calls no provider at all, so a run down either
    # path sends nothing and must RECORD nothing -- a result file claiming a setting it never put
    # on the wire is the exact failure `thinking` was withheld from the adapter for two runs to
    # avoid. Ignored loudly rather than silently, so a wiring check cannot be mistaken for a test.
    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub and not a.baseline) else None
    if a.no_thinking and (a.stub or a.baseline):
        print("  note: --no-thinking ignored — %s calls no provider, so there is no reasoning "
              "pass to disable and the run records none."
              % ("--stub" if a.stub else "--baseline"))
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
                r = EX.extract(cfg, EX.load_doc(nct), fields, complete=complete,
                               thinking=thinking)
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
            #
            # ⚑ AND IT NOW SAYS WHY IN THE PROVIDER'S OWN WORD — 2026-08-05. "(truncated?)", with
            # a question mark, left a reader to compare output_tokens against the cap by eye.
            # finish_reason == "length" IS that answer and the API had been sending it all along.
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": nct,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"),
                             "max_tokens": MAX_TOKENS,
                             # ⚑ WHERE THE BUDGET WENT, NOT JUST HOW MUCH OF IT. This is the field
                             # that settled the identical question in docs-summarise: every failure
                             # returned at exactly the cap there too, and `token_details` showed a
                             # median of 100% of it going to reasoning. Four runs of this kit have
                             # recorded the number and never the destination, which is why "why
                             # does a nine-field record run to 3000 tokens?" is still open.
                             "token_details": r.get("token_details"),
                             "finish_reason": why,
                             "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-14s reply did not parse (%s output tokens, cap %d, finish_reason=%s)"
                  % (nct, r.get("output_tokens"), MAX_TOKENS, why))
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
    # ⚑ THE PER-CALL TIMINGS ARE KEPT, NOT ONLY AGGREGATED — 2026-08-08. Every one of these
    # was measured above and then thrown away the moment it had been folded into a p50 and a p95,
    # so the result file could publish the two percentiles with no distribution behind them. A p95
    # on its own cannot say whether the tail is one slow call or a fat one; the array can. Snapshot
    # taken BEFORE the sort, so call order survives and a warm-up effect stays visible — sorting in
    # place is what would have made this a distribution and not a history.
    #
    # It is written at the TOP LEVEL rather than onto each per-document record on purpose: those
    # records are what score.py grades, and adding a key to a graded structure to carry telemetry
    # is how a timing turns into a phantom extracted field. Costs one array and no provider call.
    lat_in_order = list(lat)
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
        "latency_ms_all": lat_in_order,
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
        # ⚑ WHAT WAS SENT, NOT WHAT WAS ASKED FOR. `thinking` is the object that actually went on
        # the wire, so --no-thinking down a free path records null rather than a setting it never
        # sent. build/measured/runlog.py reads it into a comparability guard: a reasoning-off run
        # measures a DIFFERENT SYSTEM and the board refuses to difference it against these.
        "thinking": thinking,
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
