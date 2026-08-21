"""Extract one statement's fields: segment, select, prompt, one model call, then two pure-code
computations downstream. This is the whole AI layer of the kit -- everything above it (segment,
select) and below it (the reserve/flag computation) is pure code, exactly as the flow figure's
"pure code" labels claim.

MAX_TOKENS -- a nine-field JSON record; docs-extract's sibling kit needed 3000 for the same shape
of task and hit its ceiling on a handful of documents. Left higher here on that evidence rather
than guessed at from zero: a ceiling this kit has never run against is a ceiling nobody has tested.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 4000

# Kit-declared policy, not a real loan program's published guideline -- see README/SOURCES.md.
LARGE_DEPOSIT_THRESHOLD_USD = 1000.0
VESTING = {"checking": 1.0, "savings": 1.0, "money_market": 1.0, "brokerage": 0.70}


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold. This is the guardrail the
    corpus's own facet sheet names: computed figures are proposals for underwriter sign-off,
    never an auto-approval input, and the large-deposit routing rule is non-configurable (a flat
    stated threshold, not a judgment call the model gets to make).

    Returns (computed_reserve_value, large_deposit_flag). Either can be None when its inputs are
    missing -- a missing input is not a zero.
    """
    acct_type = values.get("account_type")
    ending = values.get("ending_balance")
    reserve = None
    if isinstance(ending, (int, float)) and acct_type in VESTING:
        reserve = round(ending * VESTING[acct_type], 2)

    amount = values.get("largest_deposit_amount")
    documented = values.get("deposit_documented")
    flag = None
    if amount is not None:
        flag = bool(isinstance(amount, (int, float)) and amount >= LARGE_DEPOSIT_THRESHOLD_USD
                    and documented == "no")
    return reserve, flag


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one statement. `complete` is injectable so the eval harness,
    the app and tests all drive the same code path against a stub provider."""
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
    computed_reserve_value, large_deposit_flag = compute(flat)

    return {
        "fields": out,
        "computed_reserve_value": computed_reserve_value,
        "large_deposit_flag": large_deposit_flag,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
