"""Extract one file's fields: segment, select, prompt, one model call, then a pure-code
review-routing computation downstream. This is the whole AI layer of the kit -- everything above
it (segment, select) and below it (the routing decision) is pure code.

MAX_TOKENS -- a ten-field JSON record; the sibling extraction kits in this series needed 3000-4000
for the same shape of task. Set here on that evidence rather than guessed at from zero.
"""
import json
import os
from datetime import date

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 4000

# Kit-declared policy, not a real accreditation body's published standard -- see README/SOURCES.md.
PSV_LOOKBACK_DAYS = 180


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _parse_date(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold. Mirrors this kit's own
    facet sheet guardrail: never marks a file clean when a required primary-source element is
    missing, expired or unverified. Three checks, none of them a judgment call the model makes:

      - license_expired: the license's own expiration date is before the credentialing
        effective date.
      - psv_stale: the PSV check happened more than PSV_LOOKBACK_DAYS before the effective date.
      - sanction_or_adverse_action_found: the model's own extracted value, passed through.

    needs_review is True if ANY of the three fires. Returns (needs_review, reasons) where
    reasons lists which check(s) fired -- an empty list on a clean, current, unsanctioned file.
    Returns (None, []) when the inputs needed to compute at all are missing.
    """
    effective = _parse_date(values.get("credentialing_effective_date"))
    if effective is None:
        return None, []

    reasons = []

    expiration = _parse_date(values.get("license_expiration_date"))
    license_expired = bool(expiration is not None and expiration < effective)
    if license_expired:
        reasons.append("license_expired")

    psv_date = _parse_date(values.get("psv_check_date"))
    psv_stale = bool(psv_date is not None and (effective - psv_date).days > PSV_LOOKBACK_DAYS)
    if psv_stale:
        reasons.append("psv_stale")

    adverse = values.get("sanction_or_adverse_action_found") == "yes"
    if adverse:
        reasons.append("adverse_action")

    needs_review = license_expired or psv_stale or adverse
    return needs_review, reasons


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one file. `complete` is injectable so the eval harness, the
    app and tests all drive the same code path against a stub provider."""
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    parsed_ok = bool(values) and any(v is not None for v in values.values())

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):
            v = None
        spannable = f.get("type") != "enum"
        span = segment.locate(doc_text, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }

    flat = {name: out[name]["value"] for name in out}
    needs_review, reasons = compute(flat)

    return {
        "fields": out,
        "needs_review": needs_review,
        "review_reasons": reasons,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
