"""Cross-check one seller onboarding application against its submitted documents, and flag every
inconsistency for a verification analyst: load the record, one model call, done.

This is the whole AI layer of the kit, deliberately short -- the same split fin-payrun's payrun.py,
docs-comply's comply.py and docs-verify's verify.py all make: the model does one job, and this file
is small enough that you can see exactly which one.

⚠︎ THIS KIT NEVER APPROVES, DENIES, OR ESCALATES AN APPLICATION. `check()` below returns seven
field flags and a drafted summary and nothing else -- there is no function anywhere in this file,
or in src/app.py, that writes a verification_outcome. The historical outcome in data/gold.jsonl
exists only so the eval can show whether the model's flags would plausibly have supported the
verification team's real call; the model is never asked to reproduce it. See the module docstring
in src/prompt.py for where that boundary is worded to the model itself.

⚠︎ THE OPEN ASSUMPTION THIS KIT DOES NOT SOLVE. This kit assumes every submitted verification
document (business registration, bank letter, government ID) already arrives text-extractable --
the three document blocks below are clean fields, not images. A low-quality photo submission that
OCRs poorly has no clean text for this kit to read, and this kit has no way to notice that the
document it was given is degraded rather than simply mismatched. See data/SOURCES.md.
"""
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLICATIONS = os.path.join(HERE, "data", "applications.jsonl")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ SIZED GENEROUSLY FROM THE START, NOT GUESSED LOW -- same discipline every sibling kit's
# MAX_TOKENS states, learned the hard way on an earlier kit tonight: a reply shape this small
# (seven three-way flags plus a short summary) still ran into a ceiling on a real provider
# because provider-side reasoning ate most of the budget before the JSON answer even started.
# This is a safety margin, not a computed number -- only a live run's finish_reason and
# reasoning_tokens can say whether it was needed, and only the operator can fire that run.
MAX_TOKENS = 3000


def applications():
    import json
    out = []
    with open(APPLICATIONS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_gold():
    """The gold flags and historical outcome, keyed by application_id. NEVER read by check() --
    passing them anywhere near the prompt would be the oldest mistake in evaluation."""
    import json
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["application_id"]] = r
    return rows


def check(cfg, app, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one application: the seven field flags, the drafted summary,
    and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the same code
    path.
    """
    msgs, parts = P.build(app, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw)

    parsed_ok = bool((raw or "").strip()) and all(parsed[f] is not None for f in P.FIELDS)
    out = {
        "application_id": app["application_id"],
        "summary": parsed["summary"],
        "parsed": parsed_ok,
        "raw": raw,
        "parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"),
        "model": res.get("model"),
    }
    for f in P.FIELDS:
        out[f] = parsed[f]
    return out
