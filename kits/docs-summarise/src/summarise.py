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
#
# ⚠︎ 4000 WAS STILL TOO LOW, AND RUN r001 PAID 42 CALLS TO FIND OUT — 2026-08-05. It wrote 6 briefs
# and lost 36, and the split is exactly the ceiling: every one of the 36 failures came back at
# 3999–4000 output tokens, every one of the 6 successes at 1634–3898. No reply that fit failed to
# parse and no reply that hit the cap survived, so this is the harness, not the model — and a
# score computed from it would have published a harness defect as a model-quality figure, the
# exact failure `parsed` was separated out to prevent.
#
# ⚑ BUT THE 36 ARE NOT ALL THE SAME FAILURE, AND THE TIDY VERSION OF THIS STORY IS WRONG.
# Only 8 of them captured any text at all. Of those 8:
#   * GAO-08-1075R ran 3,909 chars through five of the six keys in order, no repetition anywhere,
#     and stopped mid-sentence — a real brief that needed more room.
#   * GAO-08-525 and GAO-08-825 hold ~765 chars, roughly 200 tokens of visible text, while the
#     provider reported 4,000 output tokens. That gap is REASONING TOKENS: DeepSeek counts them in
#     completion_tokens and never returns them as content. The remaining 28 captured nothing at
#     all, which is what it looks like when reasoning consumes the whole budget before the first
#     character of the answer is emitted.
# So max_tokens here has to cover reasoning AND the brief, and on the evidence reasoning is the
# larger consumer. 8000 buys room for both — the largest SUCCESSFUL reply was already 3,898, so
# half the old ceiling was gone before reasoning was accounted for at all.
#
# ⚠︎ THIS IS A HYPOTHESIS WITH ONE RUN BEHIND IT, NOT A SETTLED NUMBER. `finish_reason` is
# recorded now and raw_text is kept, so the next run says which mode dominated instead of leaving
# it to be inferred from a token count. If reasoning is the whole story, the fix is a provider
# parameter, not a bigger ceiling. It is a ceiling, not a quota: it costs nothing on the replies
# that finish early.
MAX_TOKENS = 8000


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
        # Carried so a failure can say WHY in the provider's own word rather than having it
        # reconstructed from a token count. "length" means the reply was cut off, full stop.
        "finish_reason": res.get("finish_reason"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
