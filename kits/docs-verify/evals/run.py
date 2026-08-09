"""Run the claim checker over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>             # the real run, ONE call per document
    python -m evals.run --run-id t000 --stub              # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 3         # a costed toe in the water

⚠︎ ONE CALL PER DOCUMENT, COUNTED BEFORE IT IS MADE — same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed. 20 calls
covers 174 claims here, because the claims for a document are batched into its one call; that
ratio is the reason this kit is cheap enough to run on two models.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                 # noqa: E402
from src import adapters                          # noqa: E402
from src import config, verify as V               # noqa: E402
from src.verify import MAX_TOKENS                 # noqa: E402
from evals import judge as J                      # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It answers `supported` to every claim and quotes the
    document's first line. That is an honestly mediocre checker — it scores exactly the majority
    class and nothing better — and it exists to exercise prompt -> call -> parse -> score end to
    end without a key. It is NOT a baseline; `evals/baseline.py` is.

    ⚠︎ IT READS ONLY THE DOCUMENT, NOT THE WHOLE PROMPT — the same trap docs-redact's stub records
    paying for. `build()` always emits the literal marker below immediately before the document,
    so splitting on it is what keeps the stub from quoting the instructions back.
    """
    marker = "DOCUMENT\n--------\n"
    doc_only = user.split(marker, 1)[-1] if marker in user else user
    first_line = next((l for l in doc_only.splitlines() if l.strip()), "")
    n = user.count("\n1. ") and user.split("CLAIMS\n------\n", 1)[-1].split("\n\n", 1)[0]
    count = len([l for l in (n or "").splitlines() if l.strip()])
    verdicts = [{"n": i + 1, "verdict": "supported", "quote": first_line}
                for i in range(count)]
    return {"text": json.dumps({"verdicts": verdicts}), "usage": {},
            "input_tokens": len(user) // 4, "output_tokens": 20 * max(1, count),
            "raw": {"stub": True}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--no-thinking", action="store_true",
                    help="disable provider-side reasoning. The default leaves it alone; UC006 "
                         "found the hard way that a provider default of ON can burn the whole "
                         "output ceiling on hidden reasoning and return nothing.")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    labelled = V.load_claims()
    docs = V.documents()
    if a.limit:
        docs = docs[:a.limit]
    n_claims = sum(len(labelled.get(d, [])) for d in docs)

    print("run      : %s" % a.run_id)
    print("documents: %d   claims: %d" % (len(docs), n_claims))
    print("calls    : %d  (one per document — claims are batched)" % len(docs))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("thinking : %s" % ("disabled" if a.no_thinking else "provider default"))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted — nothing spent")
            return
    if not a.stub:
        # ⚠︎ THIS IS THE ONLY BUDGET CALL THIS HARNESS MAKES, AND THE LOOP BELOW USED TO MAKE
        # ANOTHER. It called BUDGET.record(1) after every document while adapters.complete()
        # already recorded one layer down, so every call was written to the shared ledger TWICE —
        # and worse, `1` was passed where record() expects a MODEL, so the phantom lines are
        # filed under model "1" and cannot even be attributed. A spend guard that double-counts is
        # not conservative, it is broken: it halves the real cap and cannot be reconciled against
        # a provider invoice. THE ADAPTER OWNS `check` AND `record`; a harness must not also
        # record. This pre-flight check is a different question — "can I afford the whole run
        # before starting it" — and stays.
        BUDGET.check(len(docs))

    thinking = adapters.THINKING_OFF if (a.no_thinking and not a.stub) else None
    complete = stub_complete if a.stub else None

    records, lat, tin, tout, failures = [], [], 0, 0, 0
    first = None
    t_all = time.time()
    for i, doc_id in enumerate(docs, 1):
        claims = labelled.get(doc_id, [])
        if not claims:
            continue
        t0 = time.time()
        r = V.verify(cfg, V.load_doc(doc_id), claims, complete=complete, thinking=thinking)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        if first is None and r["parsed"]:
            first = r
        rec = {"doc": doc_id, "claims": r["claims"], "answered": r["answered"],
               "asked": r["asked"], "parsed": r["parsed"],
               "finish_reason": r.get("finish_reason"),
               "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
               "reasoning_tokens": r.get("reasoning_tokens"), "latency_ms": ms}
        # ⚠︎ A FAILED CALL KEEPS ITS RAW REPLY. Run r001 had one document return nothing with
        # finish_reason="stop" — not truncation, so the interesting question was what it DID say,
        # and the record had thrown it away. Only the first SUCCESSFUL reply was being kept.
        # A failure you cannot read is a failure you cannot fix.
        if not r["parsed"]:
            rec["raw_text"] = r.get("raw", "")
        records.append(rec)
        print("  %2d/%d  %-14s %2d/%-2d answered  %s"
              % (i, len(docs), doc_id, r["answered"], r["asked"],
                 "" if r["parsed"] else "*** UNPARSEABLE ***"))

    scored = J.score(records, labelled)
    lat.sort()

    def p(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    out = {
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "documents": len(records),
        "claims": n_claims,
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": scored["overall"],
        "per_class": scored["per_class"],
        "matrix": scored["matrix"],
        "unanswered_by_class": scored["unanswered_by_class"],
        "prompt_parts": [{"name": p_["name"], "chars": len(p_["text"])}
                         for p_ in (first["parts"] if first else [])],
        # ⚑ ONE REAL REPLY, VERBATIM, BEFORE ANY PARSING — the LLM lens standard's requirement,
        # matching every sibling: the first successful document's raw reply, alongside the prompt
        # parts, so the two describe ONE call rather than two unrelated ones.
        "raw_text": (first["raw"] if first else ""),
        "max_tokens": MAX_TOKENS,
        "thinking": thinking,
        "records": records,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    o = scored["overall"]
    print("\n%-24s %s" % ("run", a.run_id))
    print("%-24s %s of %s  (%s%%)" % ("answered", o["answered"], o["claims"], o["answered_pct"]))
    print("%-24s %s%%  (over answered claims)" % ("accuracy", o["accuracy_answered_pct"]))
    print("%-24s %s  (%s%% of unsupported claims)"
          % ("false support", o["false_support"], o["false_support_rate_pct"]))
    print("%-24s %s%%" % ("quote fidelity", o["quote_fidelity_pct"]))
    for c in J.LABELS:
        pc = scored["per_class"][c]
        print("  %-20s recall %-7s precision %-7s (gold %s)"
              % (c, pc["recall_pct"], pc["precision_pct"], pc["gold"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
