"""Where does the FALSE-ALARM RATE actually come from? THIS SPENDS MONEY.

    python -m evals.ablate --run-id a001-ctr-precheck --yes

⚑ WHY THIS EXISTS, AND WHY IT IS THE ONLY PROBE THIS KIT PAID FOR. The scored run returned 0 false
alarms on 18 clean filings. That is the number this kit leads with, and a zero is exactly the kind
of figure that is equally consistent with two very different claims:

  (a) the model reads the rulebook, sees that a wire is not currency and that an entry at 03:15 is
      the previous gaming day, and correctly leaves both out of its finding list; or
  (b) this kit's own system prompt tells it, in two explicit rules, not to over-flag -- and the
      model is following instructions.

Those are different products. A forker who replaces the prompt gets (a) for free and loses (b), and
nothing on the published page would have told them which they were relying on. So the two rules are
STRIPPED and the CLEAN packs are re-fired:

  rule 4  "A NON-REPORTABLE ENTRY IS NOT A DEFECT ... reporting them as a missed aggregation is a
           false alarm, and on this check a false alarm costs a person the time to clear a row that
           never needed clearing."
  rule 5  "A FILING WITH NOTHING WRONG WITH IT IS 'none'. Answer 'none' and do not manufacture a
           finding to look thorough."

Everything else is unchanged: the rulebook still travels in the call, the stopping order is still
stated, the schema is identical.

⚠︎ ONLY THE CLEAN PACKS ARE RE-FIRED, AND THAT IS A DELIBERATE LIMIT ON WHAT THIS MEASURES. The
false-alarm rate's denominator is the clean packs and only the clean packs, so 18 calls buy the
whole of the number this probes. What it does NOT measure is whether the stripped prompt still finds
the 38 real defects -- that would be another 38 calls for a different question, and this kit did not
buy it. It is named in Eval.could_not_verify rather than glossed.

⚠︎ THIS IS NOT A SCORED RUN. It uses a prompt this kit does not ship, over a subset of the corpus.
Its result file exists so the claim above can be checked, and it is in no denominator on any
published page.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from src import prompt as P                    # noqa: E402
from src.extract import defect_set as _defect_set   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# The two sentences removed, matched on their opening words so a rewording of the prompt breaks
# this file loudly rather than silently ablating nothing.
STRIP_MARKERS = ("4. A NON-REPORTABLE ENTRY IS NOT A DEFECT.",
                 "5. A FILING WITH NOTHING WRONG WITH IT IS 'none'.")


def stripped_system():
    """The system prompt with those two rules cut out, and NOTHING ELSE CHANGED.

    ⚠︎ THE REMAINING RULES ARE NOT RENUMBERED. Cutting 4 and 5 leaves 1, 2, 3, 6, 7, 8, 9, which
    looks untidy and is the point: renumbering would be rewriting the prompt, and then the probe
    would be measuring a prompt this kit never shipped MINUS two rules PLUS an edit. What is
    measured here is the removal and only the removal.
    """
    text = P.SYSTEM
    for marker in STRIP_MARKERS:
        i = text.find(marker)
        if i < 0:
            raise SystemExit("prompt rule %r is no longer in src/prompt.py::SYSTEM — this "
                             "ablation would strip nothing and report a meaningless zero." % marker)
        j = text.find("\n", i)
        text = text[:i] + text[j + 1:]
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    fields = EX.load_fields()
    golds = {r["case_id"]: r for r in
             (json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip())}
    clean = sorted(s for s, g in golds.items() if not (_defect_set(g["defects_found"]) or set()))

    system = stripped_system()
    print("stripped %d chars of system prompt (%d -> %d)"
          % (len(P.SYSTEM) - len(system), len(P.SYSTEM), len(system)))
    print(BUDGET.plan(len(clean), cfg.get("model")) + " via %s" % cfg.get("provider"))
    if not a.yes and input("type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")
    BUDGET.check(len(clean))

    from src import adapters, segment, select as selector

    def one(case_id):
        text = EX.load_doc(case_id)
        secs = segment.sections(text)
        msgs, _parts, _used = P.build(text, secs, fields, selector)
        t0 = time.time()
        res = adapters.complete(cfg, system, msgs[1]["content"], max_tokens=EX.MAX_TOKENS)
        values = P.parse(res.get("text", ""), fields)
        return case_id, _defect_set(values.get("defects_found")), int((time.time() - t0) * 1000), \
            res.get("input_tokens") or 0, res.get("output_tokens") or 0

    rows, flagged = [], []
    tin = tout = 0
    with ThreadPoolExecutor(max_workers=int(os.environ.get("EVAL_WORKERS", "12"))) as pool:
        for case_id, got, ms, i_tok, o_tok in pool.map(one, clean):
            tin += i_tok
            tout += o_tok
            raised = sorted(got) if got else []
            rows.append({"doc": case_id, "flagged": raised,
                         "unanswered": got is None, "latency_ms": ms})
            if raised:
                flagged.append({"doc": case_id, "flagged": raised})
            print("  %-10s %s  %d ms" % (case_id, ", ".join(raised) or "none", ms))

    rate = round(100.0 * len(flagged) / len(clean), 2) if clean else None
    out = {
        "run_id": a.run_id,
        "kind": "ablation",
        "note": "NOT A SCORED RUN. The two anti-false-alarm rules were removed from the system "
                "prompt and only the CLEAN packs were re-fired, because the false-alarm rate's "
                "denominator is the clean packs and only the clean packs. Whether the stripped "
                "prompt still finds the 38 real defects is NOT measured here.",
        "stripped_rules": list(STRIP_MARKERS),
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "documents": len(clean),
        "clean_packs": len(clean),
        "clean_packs_flagged": len(flagged),
        "false_alarm_rate_pct": rate,
        "flagged": flagged,
        "rows": rows,
        "input_tokens_total": tin,
        "output_tokens_total": tout,
        "max_tokens": EX.MAX_TOKENS,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\n%-36s %s%%  (%d of %d clean filings flagged)"
          % ("FALSE-ALARM RATE, RULES STRIPPED", rate, len(flagged), len(clean)))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
