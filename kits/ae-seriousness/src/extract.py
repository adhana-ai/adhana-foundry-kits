"""Extract one case report's fields: segment, select, prompt, one model call, then a pure-code
review-routing computation downstream. This is the whole AI layer of the kit -- everything above
it (segment, select) and below it (the routing decision) is pure code.

MAX_TOKENS -- a ten-field JSON record; the sibling extraction kits in this series needed 3000-4000
for the same shape of task. Set here on that evidence rather than guessed at from zero.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")

MAX_TOKENS = 4000

# ⚠︎ THIS KIT'S OWN SIMPLIFICATION, NOT A REAL PHARMACOVIGILANCE PROGRAM'S RULE. A real expedited
# reporting obligation is a CLOCK -- it starts on a defined awareness event and runs a defined
# number of calendar days, and which cases start it depends on the product, the market and the
# report type. None of that is modelled here. All this kit does is route a case towards a human
# case processor sooner when it is both regulatorily serious AND the reporter thinks the drug may
# have caused it. Replace it with your own program's actual documented criteria before trusting
# the flag for anything real. See README.md and data/SOURCES.md.
CAUSALITY_TRIGGERS = ("related", "possibly-related")

_CAUSALITY_VALUES = ("related", "possibly-related", "unrelated", "not-assessed")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(stmt_id):
    with open(os.path.join(CORPUS, "%s.txt" % stmt_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def compute(values):
    """PURE CODE, run on whatever the model returned -- never on gold.

    Returns needs_review: True only when the case is BOTH regulatorily serious AND the reporter's
    own causality assessment is one this kit routes on. A serious case the reporter calls
    unrelated -- a hospitalised patient who was hit by a car -- is still a serious case and is
    still a case; it just does not get the same urgency here.

    Returns None when the inputs needed to compute at all are missing or out of vocabulary. None
    is a THIRD state and never a False: "we could not decide" and "we decided no" route
    differently for anyone reading this downstream.
    """
    is_serious = values.get("is_serious")
    causality = values.get("causality_assessment")
    if is_serious not in ("yes", "no") or causality not in _CAUSALITY_VALUES:
        return None
    return (is_serious == "yes") and (causality in CAUSALITY_TRIGGERS)


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one case. `complete` is injectable so the eval harness, the app
    and tests all drive the same code path against a stub provider."""
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
    needs_review = compute(flat)

    return {
        "fields": out,
        "needs_review": needs_review,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
