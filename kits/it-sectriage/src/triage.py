"""Triage one case window: classify, correlate, draft -- one model call, done.

This is the whole AI layer of the kit, deliberately short -- the same split fin-payrun's payrun.py
and fin-close's close.py both make: the model does one job, and this file is small enough that you
can see exactly which one.

⚠︎ THIS KIT NEVER EXECUTES A CONTAINMENT ACTION. `check()` below returns dispositions, case
groupings and drafted recommendations and nothing else -- there is no function anywhere in this
file, or in src/app.py, that locks an account, blocks mail flow or isolates an endpoint. Every
recommendation is text, addressed to the window's named on-call analyst, awaiting their approval.
See src/prompt.py's SYSTEM for the same boundary stated to the model itself.

⚠︎ THE OPEN ASSUMPTIONS THIS KIT DOES NOT SOLVE. Indicator coverage varies by which security tools
are actually integrated -- an alert from a tool this kit has no feed for cannot be enriched past
whatever indicators it already carries. And the case-window boundary itself (which alerts get
bundled together for one call) is set upstream of this file, by whatever entity/time correlation
window a real deployment tunes -- too loose over-merges unrelated alerts before a model ever sees
them, too tight splits one real incident across two calls. See data/SOURCES.md.
"""
import json
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = os.path.join(HERE, "data", "windows.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

MAX_TOKENS = P.MAX_TOKENS


def windows():
    out = []
    with open(WINDOWS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold verdicts, keyed by window id. NEVER read by check() -- passing them anywhere near
    the prompt would be the oldest mistake in evaluation."""
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def check(cfg, window, complete=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one case window: dispositions, groupings, recommendations, and
    what the call cost.

    `complete` is injectable so the eval harness, the local app and the stub all drive the same
    code path.
    """
    msgs, parts = P.build(window, prompt=prompt)
    call = complete or adapters.complete
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], max_tokens=MAX_TOKENS)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    return {
        "id": window["id"],
        "alert_dispositions": parsed["alert_dispositions"],
        "case_groups": parsed["case_groups"],
        "recommendations": parsed["recommendations"],
        "parsed": parsed["parsed"] and bool(parsed["alert_dispositions"]),
        "raw": raw,
        "parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_chars": res.get("reasoning_chars"),
    }
