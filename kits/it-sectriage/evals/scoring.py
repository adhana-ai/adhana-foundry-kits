"""Score a set of predicted case-window triages against gold. Pure code, shared by
evals/baseline.py and evals/run.py so the free floor and the real run are graded by the identical
function -- a baseline and a model scored by two different scorers cannot be compared honestly.

Four things are scored, kept separate, never folded into one accuracy number:

    disposition_accuracy   per-alert true_positive/false_positive, exact match against gold,
                            over every alert in every window.
    missed_true_positive   THE expensive-direction error for classification -- a gold true
                            positive the model called false_positive. Reported overall and, on
                            its own, over the planted mundane-phishing trap subset -- see
                            data/SOURCES.md.
    false_correlation      THE expensive-direction error for grouping -- a pair of alerts gold
                            keeps in different cases (or one case and no case) that the model put
                            in the same case. Reported overall and, on its own, over the planted
                            coincidental-indicator trap subset.
    citation_validity      does every drafted recommendation cite an indicator that actually
                            exists on an alert in that case -- never a fabricated one. Pure-code
                            lookup, same discipline as gap-brief's citation_is_real.

⚑ "FALSE CORRELATION" IS SCORED OVER PAIRS, NOT OVER GROUPS, BECAUSE A GROUP-LEVEL COMPARISON
HIDES A PARTIAL MERGE. If gold has three separate cases and the model returns one group containing
two of them, no single group-vs-group comparison describes what went wrong -- but every pair drawn
from those two now-merged cases IS a false correlation, and counting pairs says exactly how many.
A "gold-different" pair is any two alerts NOT in the same true-positive case together in gold --
that includes two different real incidents, and it includes a true positive paired with a false
positive, which is exactly the shape of this kit's own named example (a real brute-force attempt
merged with an unrelated, benign travelling user's login because they coincidentally shared a
source IP).
"""
import re
from collections import Counter

DISPOSITIONS = ("true_positive", "false_positive")


def _gold_group_map(gold_row):
    """alert_id -> its case_groups index, or None if it is in no case (every false positive, by
    construction -- see tools/build_corpus.py::derive_gold)."""
    out = {}
    for i, grp in enumerate(gold_row["case_groups"]):
        for aid in grp:
            out[aid] = i
    return out


def _pred_group_map(case_groups):
    out = {}
    for i, grp in enumerate(case_groups or []):
        for aid in grp:
            if aid not in out:                     # first group wins; a model that double-lists
                out[aid] = i                        # an id has already produced a malformed reply
    return out


def _norm_kv(s):
    """'source_ip=203.0.113.9' / 'source_ip: 203.0.113.9' / extra whitespace -> the same
    (key, value) pair, lower-cased. Returns None for anything that does not look like one."""
    if not s or not isinstance(s, str):
        return None
    m = re.match(r"\s*([A-Za-z0-9_]+)\s*[:=]\s*(.+?)\s*$", s)
    if not m:
        return None
    return (m.group(1).strip().lower(), m.group(2).strip().lower())


def citation_is_real(citation, case_alert_ids, alerts_by_id):
    """True iff `citation` names a (indicator_name, value) pair that actually exists on at least
    one alert in this case -- exact match after normalisation, never a fuzzy or substring one. A
    citation for an indicator that exists but on a DIFFERENT alert not in this case does not
    count; see citation_is_relevant's discussion in gap-brief for why "real but wrong item" is
    still a fabrication as far as a reader trusting the citation is concerned."""
    kv = _norm_kv(citation)
    if kv is None:
        return False
    for aid in case_alert_ids:
        a = alerts_by_id.get(aid)
        if not a:
            continue
        for k, v in a.get("indicators", {}).items():
            if (k.lower(), str(v).lower()) == kv:
                return True
    return False


def score(records, gold, windows_by_id, fn_trap_alert_ids, fc_trap_pairs):
    """`records`: this run's output, keyed by nothing in particular -- a list, one per window
    actually judged. `gold`: dict id -> gold row. `windows_by_id`: dict id -> window (for alert
    indicator lookups). `fn_trap_alert_ids`: set of alert ids carrying the false_negative trap.
    `fc_trap_pairs`: dict window_id -> (a, b), the one planted pair per false_correlation window.
    """
    # ── 1. disposition accuracy ────────────────────────────────────────────────────────────────
    disp_total = disp_answered = disp_correct = 0
    # ── 2. missed true positive ────────────────────────────────────────────────────────────────
    tp_total = tp_missed = 0
    trap_tp_total = trap_tp_missed = 0
    # ── 3. false correlation ───────────────────────────────────────────────────────────────────
    pair_total = pair_false = 0
    trap_pair_total = trap_pair_false = 0
    # ── 4. citation validity ───────────────────────────────────────────────────────────────────
    cite_total = cite_valid = 0
    fabricated = []

    windows_judged = 0
    for rec in records:
        wid = rec["id"]
        g = gold.get(wid)
        if not g:
            continue
        win = windows_by_id[wid]
        windows_judged += 1
        alerts_by_id = {a["alert_id"]: a for a in win["alerts"]}
        pred_disp = rec.get("alert_dispositions") or {}

        # 1 + 2 -----------------------------------------------------------------------------------
        for aid, gold_disp in g["alert_dispositions"].items():
            disp_total += 1
            p = pred_disp.get(aid)
            if p in DISPOSITIONS:
                disp_answered += 1
                if p == gold_disp:
                    disp_correct += 1
            if gold_disp == "true_positive":
                tp_total += 1
                is_trap = aid in fn_trap_alert_ids
                if is_trap:
                    trap_tp_total += 1
                if p != "true_positive":
                    tp_missed += 1
                    if is_trap:
                        trap_tp_missed += 1

        # 3 -----------------------------------------------------------------------------------------
        gold_grp = _gold_group_map(g)
        pred_grp = _pred_group_map(rec.get("case_groups"))
        alert_ids = list(alerts_by_id)
        for i, a in enumerate(alert_ids):
            for b in alert_ids[i + 1:]:
                ga, gb = gold_grp.get(a), gold_grp.get(b)
                gold_same = ga is not None and ga == gb
                if gold_same:
                    continue
                pair_total += 1
                pa, pb = pred_grp.get(a), pred_grp.get(b)
                pred_same = pa is not None and pa == pb
                if pred_same:
                    pair_false += 1
        if wid in fc_trap_pairs:
            a, b = fc_trap_pairs[wid]
            trap_pair_total += 1
            pa, pb = pred_grp.get(a), pred_grp.get(b)
            if pa is not None and pa == pb:
                trap_pair_false += 1

        # 4 -----------------------------------------------------------------------------------------
        for r in rec.get("recommendations") or []:
            case_ids = r.get("case") or []
            for cit in r.get("citations") or []:
                cite_total += 1
                if citation_is_real(cit, case_ids, alerts_by_id):
                    cite_valid += 1
                else:
                    fabricated.append({"window": wid, "case": case_ids, "citation": cit})

    def pct(n, d):
        return round(100.0 * n / d, 1) if d else None

    return {
        "windows_judged": windows_judged,
        "disposition": {
            "total": disp_total, "answered": disp_answered,
            "answered_pct": pct(disp_answered, disp_total),
            "accuracy_pct": pct(disp_correct, disp_answered),
        },
        "missed_true_positive": {
            "count": tp_missed, "of": tp_total, "rate_pct": pct(tp_missed, tp_total),
            "trap_count": trap_tp_missed, "trap_of": trap_tp_total,
            "trap_rate_pct": pct(trap_tp_missed, trap_tp_total),
        },
        "false_correlation": {
            "count": pair_false, "of": pair_total, "rate_pct": pct(pair_false, pair_total),
            "trap_count": trap_pair_false, "trap_of": trap_pair_total,
            "trap_rate_pct": pct(trap_pair_false, trap_pair_total),
        },
        "citation_validity": {
            "count": cite_valid, "of": cite_total, "rate_pct": pct(cite_valid, cite_total),
            "fabricated": fabricated[:20],
        },
    }
