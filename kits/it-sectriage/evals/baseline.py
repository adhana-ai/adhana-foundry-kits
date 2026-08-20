"""What a simple, dumb rule catches, over the same corpus. Free. No key, no dependency, no model
call.

    python -m evals.baseline

Every sibling kit publishes this floor -- fin-payrun's reverse-precedence classifier, ops-triage's
rule-and-threshold pager -- and this kit's version is a triager someone free-texting a quick script
in twenty minutes would actually write: trust the alert type for the three detector categories
that sound serious by construction, keyword-match the two categories a human reports (phishing,
login) for alarming language, and group anything left standing that shares an entity or a raw
indicator VALUE, full stop.

⚠︎ BOTH HALVES OF THIS BASELINE ARE HONEST, NOT STRAWMEN. Trusting malware/exfil/brute-force alert
TYPES outright is exactly what a rotation under time pressure does before anyone builds a real
model for this. Grouping on ANY shared entity-or-indicator value is exactly the na ve correlation
rule this kit's whole second trap is built to catch out -- it is not weakened for the demonstration,
it is what "same IP, must be one incident" looks like as code.

**This baseline is correct on every window that carries no trap.** It fails specifically where the
corpus means it to: a calmly-worded true-positive phishing report has no alarming keyword to catch
it, and a coincidentally shared indicator has no way to be told apart from a causally connected
one. See the per-window miss list this file prints for exactly which ones and why -- including
misses OUTSIDE the two named traps, printed without being smoothed over: a keyword rule also
misses a quiet, no-precursor account-takeover login, which is a real gap in this floor and not one
either named trap set out to test.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import triage as T                                     # noqa: E402
from evals import scoring as S                                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

TRUSTED_TYPES = ("malware_detection", "data_exfil_alert", "brute_force")

# A short list of the words a person would actually reach for in five minutes -- not tuned against
# this corpus after the fact. See the module docstring for which true positives it necessarily
# misses as a result.
ALARM_RE = re.compile(
    r"(urgent|wire transfer|credentials?|re-authenticat|impersonat|\binstall\b|executable)",
    re.I)


def classify(win):
    """(alert_dispositions, case_groups) for one window, by the dumb rule described above.

    ⚑ CORRELATE FIRST, THEN SPREAD DISPOSITION BY ASSOCIATION -- the order a hasty read actually
    goes in, and the order that makes the shared-indicator trap bite. Two alerts are "the same
    thing" the instant they share an entity or ANY raw indicator value, full stop, before anyone
    has judged either one individually. A group then counts as a real incident if at least one
    member independently looks bad (trusted type or an alarm keyword) -- and every OTHER alert in
    that group inherits the call. That second step is not a strawman: it is exactly how a shared
    IP address turns an unrelated, calmly-worded login into "part of the incident" in a five-minute
    read, which is this kit's own false_correlation trap. It also occasionally works the other
    way and rescues a quiet, correctly-true-positive alert riding next to a loud one it is
    genuinely correlated with -- see the false_negative trap misses this file prints; not every
    quiet true positive is missed, only the ones with no loud neighbour to borrow from.
    """
    alerts = win["alerts"]
    by_id = {a["alert_id"]: a for a in alerts}
    ids = list(by_id)
    parent = {aid: aid for aid in ids}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = by_id[a], by_id[b]
            shares = (A["entity"] == B["entity"]) or bool(
                set(str(v) for v in A["indicators"].values())
                & set(str(v) for v in B["indicators"].values()))
            if shares:
                union(a, b)

    base_tp = {aid for aid in ids if by_id[aid]["alert_type"] in TRUSTED_TYPES
              or ALARM_RE.search(by_id[aid]["description"])}
    group_has_tp = {}
    for aid in ids:
        r = find(aid)
        group_has_tp[r] = group_has_tp.get(r, False) or (aid in base_tp)

    disp = {aid: ("true_positive" if group_has_tp[find(aid)] else "false_positive")
           for aid in ids}
    groups = {}
    for aid in ids:
        if disp[aid] == "true_positive":
            groups.setdefault(find(aid), []).append(aid)
    case_groups = sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])
    return disp, case_groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-keyword-rule")
    a = ap.parse_args()

    windows = T.windows()
    windows_by_id = {w["id"]: w for w in windows}
    gold = T.load_gold()
    fn_trap_ids = {aid for g in gold.values() if g["trap"] == "false_negative"
                  for aid in g["trap_alert_ids"]}
    fc_trap_pairs = {g["id"]: tuple(g["trap_pair"]) for g in gold.values()
                     if g["trap"] == "false_correlation"}

    records = []
    misses = []
    for win in windows:
        disp, case_groups = classify(win)
        records.append({"id": win["id"], "alert_dispositions": disp, "case_groups": case_groups,
                        "recommendations": []})
        g = gold[win["id"]]
        for aid, gold_disp in g["alert_dispositions"].items():
            if disp.get(aid) != gold_disp:
                why = "false_negative trap" if aid in fn_trap_ids else (
                    "missed TP, no alarm keyword" if gold_disp == "true_positive"
                    else "type-trusted FP called TP")
                misses.append({"window": win["id"], "alert": aid, "gold": gold_disp,
                              "predicted": disp.get(aid), "why": why})

    scored = S.score(records, gold, windows_by_id, fn_trap_ids, fc_trap_pairs)

    out = {"run_id": a.run_id, "baseline": True, "windows": len(records),
          "scores": scored, "misses": misses}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    d, mt, fc, ci = (scored["disposition"], scored["missed_true_positive"],
                     scored["false_correlation"], scored["citation_validity"])
    print("keyword-rule baseline over %d windows, %d alerts -- 0 model calls, $0.00\n"
          % (len(records), d["total"]))
    print("disposition accuracy      : %s%% (%d of %d answered)"
          % (d["accuracy_pct"], d["answered"], d["total"]))
    print("missed_true_positive      : %d of %d (%s%%)  trap subset %d of %d (%s%%)"
          % (mt["count"], mt["of"], mt["rate_pct"], mt["trap_count"], mt["trap_of"],
             mt["trap_rate_pct"]))
    print("false_correlation         : %d of %d pairs (%s%%)  trap subset %d of %d (%s%%)"
          % (fc["count"], fc["of"], fc["rate_pct"], fc["trap_count"], fc["trap_of"],
             fc["trap_rate_pct"]))
    print("citation_validity         : n/a -- the baseline drafts no recommendations")
    print("\nmisses (%d):" % len(misses))
    for m in misses:
        print("  %-8s %-9s gold=%-15s predicted=%-15s %s"
              % (m["window"], m["alert"], m["gold"], m["predicted"], m["why"]))
    print("\n-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
