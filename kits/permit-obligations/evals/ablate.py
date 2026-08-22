"""IS THE RULEBOOK IN EVERY PROMPT EARNING ITS TOKENS? A targeted ablation. THIS SPENDS MONEY.

    python -m evals.ablate --run-id a001-permit-obligations --yes

⚑ WHY THIS EXISTS. The scored run returned 2,294 of 2,294 cells, 268 of 268 statuses, 172 of 172
derived due dates, 0 false alarms and 0 missed actions. A perfect score is a reason to verify
harder, not a reason to trust more, and this kit has a specific thing worth verifying that most
siblings do not: THE MODEL NEVER COMPUTES A STATUS HERE. Code does. So the rulebook block that rides
in every single call -- 458 tokens, measured, of the worked example's 2,223 -- describes a
calculation the model is explicitly told it will not perform. Either it makes the FIELDS legible (which is the claim
src/prompt.py makes for it) or it is a fifth of every bill for nothing. Nothing in a clean run
separates those two.

⚑ WHAT IS REMOVED, AND WHAT IS DELIBERATELY NOT. Only the RULEBOOK BLOCK -- the intervals, the
windows, the condition-state meanings and the trigger-state meanings. The system prompt is sent
EXACTLY as the kit ships it, and so is the field schema with all of its hints. That is the honest
version of the question: this is not "can the model read a register with no instructions", it is
"does the intervals-and-windows table, which the model is told it will not apply, change what the
model reports".

⚑ WHY A SUBSET AND NOT ALL 50. The registers carrying the wrong-period decoy are the only ones where
the removed text can plausibly change an answer: an annual report filed inside the last 90 days and
credited to a stale reporting period is the one row on this corpus whose correct reading depends on
understanding that a report is measured by its PERIOD. An ordinary reading with a date on it has no
context to lose. The subset is selected by a predicate over gold, printed before it spends, so it is
reproducible and is not a hand-picked set chosen after seeing a result.

⚠︎ THIS IS NOT A SCORED RUN AND MUST NEVER BE QUOTED AS ONE. It runs a prompt the kit does not ship,
over a subset of the corpus. Its run id is `a<NNN>-` so it can never be mistaken for one.
"""
import argparse
import datetime
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET               # noqa: E402
from src import config, extract as EX          # noqa: E402
from src import prompt as P                    # noqa: E402
from evals import judge as J                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {r["register_id"]: r for r in (json.loads(l) for l in f if l.strip())}


def _d(s):
    return datetime.date.fromisoformat(s)


def decoy_registers(golds):
    """Registers carrying at least one annual report that is OVERDUE while showing a recent filing.

    The predicate is gold's own, and it is the same one evals/check_labels.py puts a floor on, so
    the subset cannot drift from the trap it is chosen to exercise.
    """
    out = {}
    for reg_id, r in sorted(golds.items()):
        hits = [o["condition_id"] for o in r["obligations"]
                if o["obligation_type"] == "periodic_report" and o["status"] == "overdue"
                and o["last_done"] and (_d(r["register_date"]) - _d(o["last_done"])).days <= 90]
        if hits:
            out[reg_id] = hits
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if not a.run_id.startswith("a"):
        raise SystemExit("an ablation's run id must start with 'a' -- it runs a prompt this kit "
                         "does not ship, over a subset, and must never be read as a scored run.")

    cfg = config.load()
    fields = EX.load_fields()
    ob_fields = EX.load_obligation_fields()
    golds = load_gold()
    picked = decoy_registers(golds)
    docs = sorted(picked)

    print("ablation subset, selected by a predicate over gold:")
    print("  %-40s %2d register(s)" % ("carry the wrong-period decoy", len(docs)))
    print("  %-40s %2d row(s)" % ("decoy rows inside them", sum(len(v) for v in picked.values())))

    if not config.has_key(cfg):
        raise SystemExit("no API_KEY configured.")
    print(BUDGET.plan(len(docs), cfg.get("model")) + " via %s" % cfg.get("provider"))
    if not a.yes and input("type 'run' to continue: ").strip() != "run":
        raise SystemExit("nothing was called.")
    BUDGET.check(len(docs))

    shipped = P.RULEBOOK_TEXT
    # The whole ablation, in one line: the rulebook block becomes a single sentence naming that a
    # rulebook exists, so the prompt's SHAPE is unchanged and only its content is removed.
    P.RULEBOOK_TEXT = ("A separate piece of code decides each obligation's status from the values "
                       "you report. You do not compute it.")
    records, flags, lat = {}, {}, []
    tin = tout = 0
    failures = []
    t_all = time.time()

    def process_one(item):
        i, reg_id = item
        t0 = time.time()
        try:
            r = EX.extract(cfg, EX.load_doc(reg_id), fields, ob_fields)
        except Exception as exc:
            return i, reg_id, None, str(exc)[:300], time.time() - t0
        return i, reg_id, r, None, time.time() - t0

    try:
        with ThreadPoolExecutor(max_workers=int(os.environ.get("EVAL_WORKERS", "12"))) as pool:
            for i, reg_id, r, err, dt in pool.map(process_one, list(enumerate(docs, 1))):
                if err is not None:
                    failures.append({"doc": reg_id, "error": err})
                    print("  !! %-10s %s" % (reg_id, err[:90]))
                    continue
                if not r.get("parsed", True):
                    failures.append({"doc": reg_id, "error": "reply did not parse as JSON",
                                     "finish_reason": r.get("finish_reason")})
                    continue
                lat.append(int(dt * 1000))
                tin += r.get("input_tokens") or 0
                tout += r.get("output_tokens") or 0
                records[reg_id] = {"fields": r["fields"], "obligations": r["obligations"]}
                flags[reg_id] = r.get("escalate")
                print("  %3d/%-3d %-10s %2d row(s)  %d ms"
                      % (i, len(docs), reg_id, len(r["obligations"]), lat[-1]))
    finally:
        P.RULEBOOK_TEXT = shipped

    sub_gold = {k: v for k, v in golds.items() if k in set(docs)}
    scored = J.score(fields, ob_fields, records, sub_gold)
    ss = J.score_statuses(records, flags, sub_gold)

    decoy_rows = {(reg, cid) for reg, cids in picked.items() for cid in cids}
    decoy_wrong = [r for r in ss["rows"]
                   if (r["doc"], r["condition"]) in decoy_rows and not r["correct"]]

    lat_in_order = list(lat)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None

    out = {
        "run_id": a.run_id,
        "kind": "ablation",
        "not_a_scored_run": ("This run REMOVES THE RULEBOOK BLOCK from the user message -- the "
                             "intervals, the action windows, the condition-state meanings and the "
                             "trigger-state meanings -- over a SUBSET of the corpus selected by a "
                             "predicate over gold. The system prompt and the field schema are sent "
                             "exactly as the kit ships them. It exists to answer 'is a rulebook "
                             "the model is told it will not apply worth 21.5 pct of every call', "
                             "and it must never be quoted as this kit's score."),
        "ablated": ["the rulebook block: obligation types with their intervals and action windows, "
                    "the condition-state meanings, the trigger-state meanings and the status "
                    "vocabulary"],
        "kept": ["the system prompt, verbatim as shipped",
                 "the field schema and every one of its per-field hints",
                 "the register sections themselves"],
        "model": cfg.get("model"),
        "provider": cfg.get("provider"),
        "documents": len(records),
        "obligations": sum(len(g.get("obligations") or []) for g in sub_gold.values()),
        "subset": picked,
        "failures": failures,
        "latency_p50_ms": p(0.50), "latency_p95_ms": p(0.95),
        "latency_ms_all": lat_in_order,
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "scores": dict(scored["overall"],
                       status_accuracy_pct=round(100.0 * ss["status_accuracy"], 2),
                       false_alarm_rate_pct=ss["false_alarm_rate_pct"],
                       false_alarm_count=ss["false_alarm_count"],
                       missed_action_count=ss["missed_action_count"],
                       due_date_accuracy_pct=ss["due_dates"]["accuracy_pct"]),
        "status_scores": ss,
        "decoy_rows_wrong": decoy_wrong,
        "rows": scored["rows"],
        "max_tokens": EX.MAX_TOKENS,
        "thinking": None,
    }
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("\n%-38s %s" % ("ablation", a.run_id))
    print("%-38s %d/%d" % ("extraction cells on the subset",
                           sum(1 for c in scored["cells"] if c["verdict"] == "hit"),
                           scored["overall"]["extraction_cells"]))
    print("%-38s %d/%d" % ("status accuracy on the subset",
                           ss["status_correct"], ss["status_rows"]))
    print("%-38s %s%%  (%d of %d raised)" % ("FALSE-ALARM RATE", ss["false_alarm_rate_pct"],
                                             ss["false_alarm_count"], ss["worklist_raised"]))
    print("%-38s %d" % ("missed actions", ss["missed_action_count"]))
    print("%-38s %d/%d" % ("derived due dates exact", ss["due_dates"]["correct"],
                           ss["due_dates"]["scored"]))
    print("%-38s %d of %d wrong" % ("the wrong-period decoy rows", len(decoy_wrong),
                                    len(decoy_rows)))
    # ⚠︎ COMPARED AGAINST THIS SUBSET'S OWN SHIPPED COST, NOT THE WHOLE CORPUS'S. The 17
    # registers here are not an average sample, so differencing against the full run's 2,146.5
    # would attribute the subset's own size to the ablation. The rulebook block is a fixed 458
    # tokens (measured, results/tokens-p001-permit-obligations.json), so adding it back is exactly
    # what these same calls would have cost as shipped.
    mean_in = tin / max(1, len(records))
    print("%-38s %d input tokens/call, against %d as shipped -- %.1f pct of every call"
          % ("input", round(mean_in), round(mean_in + 458), 100.0 * 458 / (mean_in + 458)))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
