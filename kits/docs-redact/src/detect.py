"""Detect one document's sensitive spans: prompt, one model call, locate, done. This is the whole
AI layer of the kit, deliberately short — everything below it (`redact.py`) is pure code, the same
split docs-extract's extract.py makes and names in its own docstring: the model does one job, and
this file is small enough that it is possible to see exactly which one.

There is no segment/select layer here the way docs-extract has one. Those exist there because a
ClinicalTrials.gov record runs to several thousand tokens and sending the whole thing nine times
would be nine times the bill for no benefit. These documents are a few hundred words — HR letters,
support emails, intake notes — so the whole document goes in the one call this kit ever makes, and
the section-picking machinery simply has nothing to select from.
"""
import json
import os

from . import adapters, redact as R, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATEGORIES = os.path.join(HERE, "data", "categories.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as docs-extract's MAX_TOKENS: a number a
# reader can reason about belongs to one named place, not a literal repeated at every call site.
#
# ⚠︎ UNMEASURED, ON PURPOSE, UNTIL A RUN HAS FIRED. docs-extract's first paid run clipped 20 of 42
# documents at 1024 tokens and the clipping was invisible until someone counted; docs-route's first
# run spent 120 calls discovering its ceiling was 400 against a real maximum of 373. Both defects
# were found by RUNNING, not by picking a bigger number up front. 800 here is a guess sized off the
# shape of the output — at most a handful of spans, each a short JSON object, nowhere near a full
# document's worth of text — not a measurement. If a real run truncates, that is the finding, and
# `finish_reason` below is what will say so.
MAX_TOKENS = 800


def load_categories():
    with open(CATEGORIES, encoding="utf-8") as f:
        return json.load(f)["categories"]


def load_doc(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def detect(cfg, doc_text, categories, complete=None, thinking=None):
    """Return the full record for one document: the located spans, and what the call cost.

    `complete` is injectable so the eval harness, the app and a test all drive the SAME code path
    against a stub provider — the reason docs-extract's extract() takes the same parameter.
    """
    msgs, parts = P.build(doc_text, categories)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    spans = P.parse(raw, categories)
    # ⚑ THE THIRD STATE — same lesson docs-extract's extract() paid a run to learn. "The model
    # found zero spans" and "the model's reply could not be read at all" are different facts, and
    # only the first is a claim about the document. A genuinely clean document (no PII at all) also
    # parses to zero spans, so `parsed` distinguishes "read successfully, found nothing" from
    # "could not be read" rather than collapsing both into an empty list a caller cannot tell apart.
    parsed_ok = bool((raw or "").strip()) and bool(spans or "{" in (raw or ""))
    located = R.locate(doc_text, spans)
    # A span the model reported but code could not find in the document is not silently kept as if
    # it had a location, and not silently dropped as if the model said nothing — it is counted, so
    # a caller can see the gap between "detected" and "detected AND locatable".
    unlocated = sum(1 for s in located if s["start"] is None)

    return {
        "spans": located,
        "unlocated": unlocated,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
        "prompt_parts": [{"name": p["name"], "chars": len(p["text"])} for p in parts],
    }
