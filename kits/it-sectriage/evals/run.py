"""Run the triager over the corpus and write one result file. THIS SPENDS MONEY.

Usage:
    python -m evals.run --run-id r001-<model>             # the real run, ONE call per window
    python -m evals.run --run-id t000 --stub               # no key, no spend, proves the wiring
    python -m evals.run --run-id r001-x --limit 5           # a costed toe in the water

⚠︎ ONE CALL PER CASE WINDOW, COUNTED BEFORE IT IS MADE -- same discipline as every sibling kit's
run.py. The plan is printed and the run stops for confirmation unless --yes is passed.

⚑ READ evals/baseline.py FIRST. It costs nothing, needs no key, and demonstrates both named traps
concretely with a rule anyone could free-text in five minutes -- this run only means something
measured beside it.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import budget as BUDGET                  # noqa: E402
from src import config, triage as T                 # noqa: E402
from src import prompt as P                           # noqa: E402
from evals import scoring as S                          # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def stub_complete(cfg, system, user, max_tokens=1024, **kw):
    """A deterministic fake provider. It exercises prompt -> call -> parse -> score end to end
    with no key and no network: it calls every alert true_positive (so missed_true_positive is
    always 0 -- there is nothing left to miss) and merges the whole window into one case
    regardless of how many genuinely distinct incidents are in it, which is the worst-case version
    of exactly this kit's false_correlation failure and drives that metric to 100%. Its
    recommendation cites a real indicator value drawn from the window, so citation_validity passes
    -- the citation check and the correlation check are independent by design, and the stub is not
    built to fail every metric at once. It is NOT a baseline; evals/baseline.py is."""
    ids = []
    for line in user.split("\n"):
        line = line.strip()
        if line.startswith("ALT-"):
            ids.append(line.split()[0])
    if not ids:
        ids = ["ALT-0000"]
    first_kv = None
    marker = "indicators: "
    for line in user.split("\n"):
        if marker in line:
            first_kv = line.split(marker, 1)[-1].split(",")[0].strip()
            break
    reply = json.dumps({
        "alert_dispositions": {aid: "true_positive" for aid in ids},
        "case_groups": [ids],
        "recommendations": [{"case": ids, "action": "Isolate pending analyst approval (stub).",
                             "citations": [first_kv] if first_kv else []}],
    })
    return {"text": reply, "input_tokens": len(user) // 4, "output_tokens": 80,
           "finish_reason": "stop", "reasoning_chars": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stub", action="store_true", help="no key, no spend")
    ap.add_argument("--prompt", default=P.DEFAULT_PROMPT,
                    help="which SYSTEM variant to send: %s" % ", ".join(sorted(P.SYSTEMS)))
    ap.add_argument("--yes", action="store_true", help="skip the confirmation")
    a = ap.parse_args()

    cfg = config.load()
    gold = T.load_gold()
    windows = T.windows()
    windows_by_id = {w["id"]: w for w in windows}
    if a.limit:
        windows = windows[:a.limit]

    fn_trap_ids = {aid for g in gold.values() if g["trap"] == "false_negative"
                  for aid in g["trap_alert_ids"]}
    fc_trap_pairs = {g["id"]: tuple(g["trap_pair"]) for g in gold.values()
                     if g["trap"] == "false_correlation"}

    print("run      : %s" % a.run_id)
    print("windows  : %d   calls: %d  (one per case window)"
          % (len(windows), len(windows)))
    print("alerts   : %d" % sum(len(w["alerts"]) for w in windows))
    print("model    : %s" % ("stub" if a.stub else cfg.get("model")))
    print("prompt   : %s" % a.prompt)
    print("max_tokens: %d" % T.MAX_TOKENS)
    if not a.stub:
        print(BUDGET.plan(len(windows), cfg.get("model")))
    if not a.stub and not a.yes:
        if input("proceed? [y/N] ").strip().lower() != "y":
            print("aborted -- nothing spent")
            return
    if not a.stub:
        BUDGET.check(len(windows))

    complete = stub_complete if a.stub else None

    records, lat, tin, tout, failures = [], [], 0, 0, 0
    t_all = time.time()
    for i, win in enumerate(windows, 1):
        t0 = time.time()
        r = T.check(cfg, win, complete=complete, prompt=a.prompt)
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        tin += r.get("input_tokens") or 0
        tout += r.get("output_tokens") or 0
        if not r["parsed"]:
            failures += 1
        rec = {"id": r["id"], "alert_dispositions": r["alert_dispositions"],
              "case_groups": r["case_groups"], "recommendations": r["recommendations"],
              "parsed": r["parsed"], "finish_reason": r.get("finish_reason"),
              "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
              "reasoning_chars": r.get("reasoning_chars"), "latency_ms": ms}
        if not r["parsed"]:
            rec["raw_text"] = r.get("raw", "")
        records.append(rec)
        print("  %2d/%d  %-6s  %d alert(s) -> %d case(s)  %s"
              % (i, len(windows), win["id"], len(win["alerts"]), len(r["case_groups"]),
                 "" if r["parsed"] else "*** UNPARSEABLE ***"))

    scored = S.score(records, gold, windows_by_id, fn_trap_ids, fc_trap_pairs)
    lat.sort()

    def pctl(q):
        return lat[min(int(q * len(lat)), len(lat) - 1)] if lat else None

    out = {
        "kind": "triage",
        "run_id": a.run_id,
        "stub": bool(a.stub),
        "model": "stub" if a.stub else cfg.get("model"),
        "provider": "stub" if a.stub else cfg.get("provider"),
        "windows": len(records),
        "alerts": sum(len(w["alerts"]) for w in windows),
        "failures": failures,
        "latency_p50_ms": pctl(0.50), "latency_p95_ms": pctl(0.95),
        "wall_seconds": round(time.time() - t_all, 1),
        "input_tokens_total": tin, "output_tokens_total": tout,
        "max_tokens": T.MAX_TOKENS,
        "prompt_version": a.prompt,
        "scores": scored,
        "records": records,
        "could_not_verify": [
            "Every window judged here is a pre-selected 2-4 alert candidate group; nothing in this "
            "kit chooses which alerts get bundled together in the first place. A real deployment's "
            "own entity/time correlation window governs that, and too loose or too tight a window "
            "changes what a model is even given the chance to get right.",
            "Indicator coverage is assumed complete for every alert in this corpus. An alert from a "
            "security tool this deployment has no feed for would arrive with fewer or no "
            "indicators, and this kit does not model that gap.",
            "The corpus is invented, so it contains the two failure modes planted on purpose and no "
            "others. A real alert stream carries noise and incident shapes this set does not.",
        ]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    d, mt, fc, ci = (scored["disposition"], scored["missed_true_positive"],
                     scored["false_correlation"], scored["citation_validity"])
    print("\n%-26s %s" % ("run", a.run_id))
    print("%-26s %s of %s answered (%s%%)" % ("disposition", d["answered"], d["total"],
                                              d["answered_pct"]))
    print("%-26s %s%%" % ("disposition accuracy", d["accuracy_pct"]))
    print("%-26s %s of %s (%s%%)  trap subset %s of %s (%s%%)"
          % ("MISSED TRUE POSITIVE", mt["count"], mt["of"], mt["rate_pct"], mt["trap_count"],
             mt["trap_of"], mt["trap_rate_pct"]))
    print("%-26s %s of %s pairs (%s%%)  trap subset %s of %s (%s%%)"
          % ("FALSE CORRELATION", fc["count"], fc["of"], fc["rate_pct"], fc["trap_count"],
             fc["trap_of"], fc["trap_rate_pct"]))
    print("%-26s %s of %s (%s%%)" % ("citation validity", ci["count"], ci["of"], ci["rate_pct"]))
    print("tokens in/out %d/%d   p50 %.0f ms   p95 %.0f ms   failures %d"
          % (tin, tout, out["latency_p50_ms"] or 0, out["latency_p95_ms"] or 0, failures))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
