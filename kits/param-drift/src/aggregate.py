"""SEAM 2 -- the cut. Grouping raw readings into the rolling window a parameter is judged on, and
computing the facts a rule floor and a prompt both draw from. Pure code, no model.

⚑ "SAMPLE EVENTS" IN THIS KIT'S FLOW IS data/readings.csv -- ONE ROW PER PERIOD, PER PARAMETER, NOT
PER PARAMETER. It is a flat stream, the same shape as ops-triage's events.csv, and `cut()` is the
station that turns it into one ordered window per parameter -- the unit everything downstream
judges one at a time. Nothing upstream of this file knows a parameter has a "window"; it only has
rows.

⚠︎ THREE FACTS, AND EACH ONE EXISTS BECAUSE A NAIVE MEAN-DEVIATION THRESHOLD CANNOT SEE IT:

    mean/std     what `src/formulas.py`'s floor actually thresholds on. Cheap, and blind to shape.
    trend        first-half mean vs second-half mean. A `slow_creep` parameter can end 35-55% away
                 from where it started while its WHOLE-WINDOW mean deviation still reads mild --
                 averaging a bad ending together with a fine beginning is exactly what hides a
                 creep from a threshold on the average. Stated as a fact, it is what lets a reader
                 catch the drift before the average does.
    outliers     periods far from the window's own centre, with whatever note the corpus logged
                 against them. A `one_off_spike` parameter can push a naive mean or std well past
                 threshold from ONE reading; the outlier fact plus its note is the evidence a
                 reader needs to hold instead of flag. Same division of labour as ops-triage's
                 `gone_silent()`: **code establishes what is true, the model judges what it
                 means.**
"""
import csv
import os
import statistics

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READINGS = os.path.join(HERE, "data", "readings.csv")

OUTLIER_K = 2.5          # a reading counts as an outlier past this many std devs from the mean


def load_readings(path=READINGS):
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["period_index"] = int(r["period_index"])
        r["observed"] = float(r["observed"])
        r["note"] = r["note"] or None
    return rows


def cut(rows):
    """Group readings by parameter_id into ordered windows. {parameter_id: [reading, ...]}."""
    out = {}
    for r in rows:
        out.setdefault(r["parameter_id"], []).append(r)
    for pid in out:
        out[pid].sort(key=lambda r: r["period_index"])
    return out


def stats(window):
    """n, mean and the SAMPLE standard deviation (n-1 denominator -- the usual estimator of an
    underlying process's variability from a sample of it, which is exactly what the safety-margin
    formula needs)."""
    vals = [r["observed"] for r in window]
    n = len(vals)
    mean = statistics.fmean(vals) if vals else None
    std = statistics.stdev(vals) if n >= 2 else 0.0
    return {"n": n, "mean": mean, "std": std}


def trend(window):
    """First-half mean vs second-half mean. The fact that catches a `slow_creep` a whole-window
    average would average away."""
    n = len(window)
    if n < 4:
        return {"first_half_mean": None, "second_half_mean": None, "delta_pct": None,
                "direction": "flat"}
    half = n // 2
    first = statistics.fmean(r["observed"] for r in window[:half])
    second = statistics.fmean(r["observed"] for r in window[half:])
    delta_pct = round(100.0 * (second - first) / first, 1) if first else None
    direction = "flat"
    if delta_pct is not None:
        if delta_pct >= 8.0:
            direction = "rising"
        elif delta_pct <= -8.0:
            direction = "falling"
    return {"first_half_mean": round(first, 2), "second_half_mean": round(second, 2),
            "delta_pct": delta_pct, "direction": direction}


def outliers(window, k=OUTLIER_K):
    """Readings more than k std devs from the window's own mean, with their note if the corpus
    logged one. Evidence, not a verdict -- what a reader (or the model) does with it is judgement."""
    st = stats(window)
    if st["std"] == 0 or st["mean"] is None:
        return []
    out = []
    for r in window:
        if abs(r["observed"] - st["mean"]) > k * st["std"]:
            out.append({"period_label": r["period_label"], "observed": r["observed"],
                       "note": r["note"]})
    return out


def facts(window):
    """Everything downstream needs about one parameter's window, in one call."""
    st = stats(window)
    return {"stats": st, "trend": trend(window), "outliers": outliers(window)}
