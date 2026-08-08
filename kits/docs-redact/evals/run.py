"""Run the detector over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>            # the real run, one call per document
    python -m evals.run --run-id t000 --stub             # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 3         # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE — same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import adapters                        # noqa: E402
from src import config, detect as D, redact as R  # noqa: E402
from src.detect import MAX_TOKENS               # noqa: E402
from evals import judge as J                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
LABELLED = os.path.join(HERE, "data", "labelled.jsonl")


def load_labels():
    with open(LABELLED, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    return {r["doc"]: r["spans"] for r in rows}


def stub_complete(cfg, system, user, max_tokens=1024):
    """A deterministic fake provider. It regex-matches only the SSN shape out of the prompt's own
    document text and reports nothing else — enough to exercise prompt -> call -> parse -> locate
    -> judge end to end, and an honestly mediocre score. It is NOT a baseline: it proves the wiring
    works, nothing about the model's competence.

    ⚠︎ SEARCHES ONLY THE DOCUMENT, NOT THE WHOLE PROMPT — found running this stub for real. The
    SSN category's own hint text in `data/categories.json` gives a worked example, "dashed
    (123-45-6789)", so a regex run over the full `user` string matches that illustrative example —
    which appears before the real document in the prompt — on every single call, never the actual
    document's SSN. `src/prompt.py`'s `build()` always emits the literal marker below right before
    the document text; splitting on it is what makes this stub search the document and nothing else.
    """
    import re
    marker = "DOCUMENT\n--------\n"
    doc_only = user.split(marker, 1)[-1] if marker in user else user
    m = re.search(r"\b\d{3}-\d{2}-\d{4}\b", doc_only)
    spans = [{"text": m.group(0), "category": "SSN"}] if m else []
    return {"text": json.dumps({"spans": spans}), "input_tokens": len(user) // 4,
            "output_tokens": 20, "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    # ⚑ WIRED FOR PARITY WITH THE SIBLING KITS, NOT BECAUSE A MEASUREMENT SAYS IT MATTERS HERE.
    # docs-extract and docs-summarise both measured runs where a reasoning-enabled model burned its
    # entire output budget on a pass nobody asked for and returned nothing. This kit has never been
    # run, so there is no such finding for it — this flag exists so that if a real run's replies
    # come back empty at MAX_TOKENS, the next thing to try is already wired rather than a fresh
    # patch. Making a claim about this kit's ceiling before a run has fired would be exactly the
    # kind of fabricated fact this project's standards forbid.
    ap.add_argument("--no-thinking", action="store_true",
                    help="send thinking={'type':'disabled'}. Provider-documented for "
                         "deepseek-v4-flash, where it is ON by default. Recorded in the run so a "
                         "reasoning-off run is never differenced against a reasoning-on one.")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    categories = D.load_categories()
    docs = D.documents()
    if a.limit:
        docs = docs[:a.limit]

    if not a.stub:
        if not config.has_key(cfg):
            raise SystemExit("no API_KEY configured. Use --stub to prove the wiring for free.")
        print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
        if not a.yes and input("type 'run' to continue: ").strip() != "run":
            raise SystemExit("nothing was called.")
        BUDGET.check(len(docs))

    complete = stub_complete if a.stub else None
    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    if a.no_thinking and a.stub:
        print("  note: --no-thinking ignored — --stub calls no provider, so there is no "
              "reasoning pass to disable and the run records none.")

    records, lat, tin, tout, failures = {}, [], 0, 0, []
    first = None
    t_all = time.time()
    for i, doc_id in enumerate(docs, 1):
        t0 = time.time()
        text = D.load_doc(doc_id)
        try:
            r = D.detect(cfg, text, categories, complete=complete, thinking=thinking)
        except Exception as exc:
            failures.append({"doc": doc_id, "error": str(exc)[:300]})
            print("  !! %-30s %s" % (doc_id, str(exc)[:90]))
            continue
        if not r.get("parsed", True):
            why = r.get("finish_reason")
            cut = (why == "length") or (r.get("output_tokens") or 0) >= MAX_TOKENS
            failures.append({"doc": doc_id,
                             "error": "reply did not parse as JSON — %s, %d output tokens (cap %d)"
                                      % ("CUT OFF AT THE CEILING" if cut else "cause unclear",
                                         r.get("output_tokens") or 0, MAX_TOKENS),
                             "output_tokens": r.get("output_tokens"),
                             "max_tokens": MAX_TOKENS,
                             "token_details": r.get("token_details"),
                             "finish_reason": why,
                             "at_ceiling": cut,
                             "raw_text": (r.get("raw_text") or "")[:4000]})
            print("  !! %-30s reply did not parse (%s output tokens, cap %d, finish_reason=%s)"
                  % (doc_id, r.get("output_tokens"), MAX_TOKENS, why))
            continue
        lat.append(int((time.time() - t0) * 1000))
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        # Judge compares by (category, text) only; the offsets `detect()` located are kept in the
        # per-doc record below for the app/report layer, not sent into scoring.
        records["%s.txt" % doc_id] = [{"text": s["text"], "category": s["category"]}
                                      for s in r["spans"]]
        if first is None:
            first = dict(r, doc_id=doc_id, redacted=R.mask(text, r["spans"]))
        print("  %3d/%-3d %-30s %d span(s), %d unlocated, %d ms"
              % (i, len(docs), doc_id, len(r["spans"]), r["unlocated"], lat[-1]))

    labels = load_labels()
    scored = J.score(labels, records)
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
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "documents": len(records),
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "by_category": scored["by_category"],
        "prompt_parts": (first["prompt_parts"] if first else []),
        # ⚑ ONE REAL REPLY, VERBATIM, BEFORE ANY PARSING — the LLM lens standard's requirement,
        # matching docs-extract's run.py: the first successful document's raw reply, alongside the
        # prompt parts and an example of the redacted output it produced, so the three describe one
        # call rather than three unrelated ones.
        "raw_text": (first["raw_text"] if first else ""),
        "example_redacted": (first["redacted"] if first else ""),
        "max_tokens": MAX_TOKENS,
        "thinking": thinking,
    }
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-22s %s" % ("run", a.run_id))
    print("%-22s %s of %s labelled spans" % ("true positives",
                                             o["true_positives"], o["labelled_spans"]))
    print("%-22s %s  (%s)" % ("leaked (missed)", o["leaked"], o["leak_rate"]))
    print("%-22s %s  (%s)" % ("over-redacted", o["over_redacted"], o["over_redaction_rate"]))
    print("%-22s precision %s   recall %s   f1 %s"
          % ("", o["precision"], o["recall"], o["f1"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
