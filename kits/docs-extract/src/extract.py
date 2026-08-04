"""Extract one document's fields: segment, select, prompt, one model call, attach spans.

This is the whole AI layer of the kit, and it is deliberately short. Everything above it
(segment, select) and below it (the judge) is pure code, which is the point the flow figure makes
by labelling those nodes "pure code": the model is doing one job here, and it is possible to see
exactly which one.
"""
import json
import os

from . import adapters, segment, select as selector, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = os.path.join(HERE, "data", "fields.json")
CORPUS = os.path.join(HERE, "data", "corpus")


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(nct_id):
    with open(os.path.join(CORPUS, "%s.txt" % nct_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def extract(cfg, doc_text, fields, complete=None):
    """Return the full record for one document.

    `complete` is injectable so the eval harness, the app and the tests all drive the SAME code
    path against a stub provider. UC001 learned this the expensive way from the other direction:
    the ranker had to be ported to JS and then held identical by a gate, because two copies of one
    behaviour drift. Here there is one copy and the seam is a parameter.
    """
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], max_tokens=1024)
    values = P.parse(res.get("text", ""), fields)

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):        # a model writing the word rather than the value
            v = None
        span = segment.locate(doc_text, v) if v is not None else None
        out[name] = {
            "value": v,
            # ⚠︎ A SPAN IS EVIDENCE, SO IT IS NEVER GUESSED. `locate` is a literal search; a
            # paraphrased value gets value-without-span, and the app renders that honestly
            # rather than pointing a reader at approximately the right place.
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }
    return {
        "fields": out,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "raw_text": res.get("text", ""),
    }
