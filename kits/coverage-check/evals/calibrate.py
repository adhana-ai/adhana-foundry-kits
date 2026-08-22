"""MEASURE the completion budget this workload actually needs, before setting MAX_TOKENS.

    python -m evals.calibrate --run-id c001-coverage-check --n 3 --ceiling 16000 --yes

⚑ WHY THIS FILE EXISTS. `MAX_TOKENS` is the one number in a kit that is almost always inherited
from a sibling and almost never measured, and getting it wrong is invisible in exactly the wrong
direction: a reply cut off at the ceiling does not parse, and a grader that cannot tell a
truncation from a wrong answer publishes a model failure rate that is really a budget failure
rate. A sibling kit in this series published an inflated failure rate twice before measuring.

⚑ WHAT IT MEASURES, AND WHY IT IS NOT THE REPLY LENGTH. It sends a handful of real claims at a
deliberately generous ceiling and records, per call, what the PROVIDER says it billed:
`output_tokens` (the whole completion), `reasoning_tokens` where the provider reports them, and
`finish_reason`. This kit never sends a `thinking` parameter, so reasoning is left at the
provider's own default and reasoning tokens are billed and bounded as completion tokens -- which
means the budget a six-branch priority rule plus a date calculation consumes is mostly invisible
in the JSON that comes back. The visible answer is a few hundred tokens. The bill is not.

It picks the claims deliberately rather than at random: the sample leads with the records whose
verdict needs the most work -- an exclusion buried in the narrative, a plan-limit case past
36/36,000, and a wear item at the early-failure boundary -- because a ceiling measured on the
easiest records in the corpus is a ceiling measured on the wrong thing.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import adapters                       # noqa: E402
from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# The hardest shapes first, chosen by class rather than by id so a regenerated corpus still picks
# work of the same difficulty.
WANT_CLASSES = ["exclusion_in_narrative", "plan_limit_beats_basic", "wear_early",
                "past_limit", "labor_op_mismatch", "boundary_covered"]


def pick(n):
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_class = {}
    for r in rows:
        by_class.setdefault(r.get("_class"), []).append(r["claim_ref"])
    out = []
    for cls in WANT_CLASSES:
        for ref in sorted(by_class.get(cls, []))[:1]:
            out.append((cls, ref))
        if len(out) >= n:
            break
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--ceiling", type=int, default=16000)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    cfg = config.load()
    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured. This file measures a live provider; there is "
                         "nothing to measure without one.")
    fields = EX.load_fields()
    sample = pick(a.n)

    print(BUDGET.plan(len(sample), cfg.get("model")) + " via %s" % cfg.get("provider"))
    print("  measuring the completion budget at a ceiling of %d on: %s"
          % (a.ceiling, ", ".join("%s (%s)" % (ref, cls) for cls, ref in sample)))
    if not a.yes and input("type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")

    def at_ceiling(c, system, user, max_tokens=None, thinking=None):
        """Overrides src/extract.py's own MAX_TOKENS with the measurement ceiling -- the whole
        point is to find out what the workload wants when nothing is constraining it."""
        return adapters.complete(c, system, user, max_tokens=a.ceiling)

    calls = []
    for cls, ref in sample:
        r = EX.extract(cfg, EX.load_doc(ref), fields, complete=at_ceiling)
        det = r.get("token_details") or {}
        row = {"doc": ref, "class": cls,
               "input_tokens": r.get("input_tokens"),
               "output_tokens": r.get("output_tokens"),
               "reasoning_tokens": det.get("reasoning_tokens"),
               "finish_reason": r.get("finish_reason"),
               "parsed": r.get("parsed"),
               "answer_chars": len(r.get("raw_text") or "")}
        calls.append(row)
        print("  %-10s %-24s out=%-6s reasoning=%-6s finish=%-8s parsed=%s"
              % (ref, cls, row["output_tokens"], row["reasoning_tokens"],
                 row["finish_reason"], row["parsed"]))

    outs = [c["output_tokens"] for c in calls if c["output_tokens"] is not None]
    peak = max(outs) if outs else None
    reas = [c["reasoning_tokens"] for c in calls if c["reasoning_tokens"] is not None]
    out = {
        "run_id": a.run_id,
        "what_it_is": "A MEASUREMENT of the completion budget this workload consumes, taken at a "
                      "deliberately generous ceiling so nothing is truncated. It is what "
                      "src/extract.py::MAX_TOKENS was set from.",
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "ceiling_used": a.ceiling,
        "calls": calls,
        "output_tokens_peak": peak,
        "output_tokens_mean": round(sum(outs) / len(outs), 1) if outs else None,
        "reasoning_tokens_peak": max(reas) if reas else None,
        "reasoning_share_of_output_pct": (round(100.0 * sum(reas) / sum(outs), 1)
                                          if reas and sum(outs) else None),
        "any_truncated": any(c["finish_reason"] == "length" for c in calls),
        "thinking": None,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "calib-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\npeak completion: %s tokens   mean: %s   reasoning share: %s%%   truncated: %s"
          % (out["output_tokens_peak"], out["output_tokens_mean"],
             out["reasoning_share_of_output_pct"], out["any_truncated"]))
    print("set MAX_TOKENS with real headroom above the peak -- not just past it.")
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
