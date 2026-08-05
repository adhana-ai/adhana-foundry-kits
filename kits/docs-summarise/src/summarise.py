"""Summarise one document to the fixed brief: segment, pack, prompt, one model call, mark absences.

This is the whole AI layer of the kit, and it is deliberately short. Everything above it (segment,
pack) is pure code, and — unlike the two kits before it — everything BELOW it is a person. There
is no judge module here that scores a brief, because a weighted rubric is not something code can
apply: two correct summaries of one document share almost no words.

⚑ SO WHAT THIS FILE RETURNS IS EVIDENCE, NOT A SCORE. Each section comes back with its text and
one of three states — written, absent (the model declined, in the words the prompt asked for), or
missing (the reply had no such key, which is a parsing fault and not a judgement). The only
mechanical verdict in the whole kit is `absent`, and it is mechanical precisely because the prompt
made the refusal explicit.
"""
import json
import os

from . import adapters, segment, pack, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUBRIC = os.path.join(HERE, "data", "rubric.json")
CORPUS = os.path.join(HERE, "data", "corpus")

# ⚑ THE OUTPUT CEILING, NAMED ONCE. UC002 learned this the expensive way: a literal in the call
# below meant the run harness printed a sentence about "3000 output tokens" without being able to
# say whether 3000 was the reply or the limit. It was both, and four truncated replies were
# recorded as an unexplained defect for a day. A brief is longer than a field record, so this is
# higher — six sections of prose, with room for the model to be wordy before it is cut off.
MAX_TOKENS = 4000


def load_rubric():
    with open(RUBRIC, encoding="utf-8") as f:
        return json.load(f)


def sections_spec():
    return load_rubric()["sections"]


def load_doc(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def summarise(cfg, doc_text, sections, complete=None, budget_tokens=None):
    """Return the full record for one document.

    `complete` is injectable so the eval harness, the app and the stub all drive the SAME code
    path. One copy of the behaviour, and the seam is a parameter — UC001 learned the cost of the
    alternative, having to port its ranker to JS and then hold two copies identical with a gate.
    """
    secs = segment.sections(doc_text)
    msgs, parts, plan = P.build(doc_text, secs, sections, pack, budget_tokens)
    call = complete or adapters.complete
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], max_tokens=MAX_TOKENS)
    raw = res.get("text", "")
    values = P.parse(raw, sections)
    parsed_ok = bool(values) and any(v for v in values.values())

    out = {}
    for sec in sections:
        key = sec["key"]
        v = values.get(key)
        text = (v or "").strip() if isinstance(v, str) else ""
        if not text:
            # ⚑ THE THIRD STATE, AND IT IS NOT THE MODEL'S FAULT. "The model declined this
            # section" and "the reply had no such key" are different facts, and only the first is
            # a judgement about the document. Rolling them together would publish a parsing defect
            # as a model-quality figure — which is precisely what UC002's first run did before
            # `parsed` was separated out.
            state = "missing"
        elif P.is_absent(text):
            state = "absent"
        else:
            state = "written"
        out[key] = {
            "name": sec["name"],
            "weight": sec["weight"],
            "text": text or None,
            "state": state,
            # No score here, ever. A grade is a person's and it is attached later, by
            # evals/grade.py, against the same rubric this record already names.
            "grade": None,
        }
    return {
        "sections": out,
        "prompt_parts": parts,
        "pack": {"sent": [s["name"] for s in plan["sent"]],
                 "dropped": [s["name"] for s in plan["dropped"]],
                 "fits": plan["fits"],
                 "chars_sent": plan["chars_sent"],
                 "chars_total": plan["chars_total"],
                 "est_tokens_sent": plan["est_tokens_sent"],
                 "budget_tokens": plan["budget_tokens"]},
        # ⚠︎ CARRIED SO A LOW SCORE CAN BE READ AGAINST WHAT THE MODEL WAS ACTUALLY GIVEN. A
        # heading regex that stops matching partway through a report produces fewer, larger
        # sections, the packer drops more, and the brief is written from a document the pipeline
        # quietly truncated. Without this number that reads as the model being bad at its job.
        "segment_coverage": segment.coverage(secs, doc_text),
        "section_count": len(secs),
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
