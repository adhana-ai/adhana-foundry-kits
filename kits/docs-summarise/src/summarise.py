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

from . import adapters, boilerplate, segment, pack, prompt as P

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
# ⚑ RUN r002 SETTLED IT, AND BOTH HALVES OF THE ABOVE WERE RIGHT — 2026-08-05, 42 more calls.
# At 8000 the yield went from 6 briefs to 27 of 42, so the ceiling WAS a real constraint and
# raising it was not a guess. But all 15 remaining failures came back at exactly 8000 with
# finish_reason "length", and the shape of them is the answer:
#     11 of 15 returned ZERO characters of visible text
#      1 returned a measurable 2,825 chars — roughly 706 tokens — against 8,000 spent
#      3 were INDETERMINATE, because the recorder's own 4000-char cap truncated them, not the model
# A reply that spends 8,000 output tokens and returns nothing has spent them where `content` cannot
# show them. On a reasoning model that is reasoning, and reasoning is therefore the binding
# constraint now — not the size of the brief.
#
# ⚠︎ SO DO NOT RAISE THIS AGAIN ON THE STRENGTH OF r002. Another doubling buys more room for
# reasoning to fill and costs a call per document to discover it; the yield curve, 6 -> 27, is a
# ceiling being cleared, not a ceiling that wants clearing twice. The next lever is request-side,
# and `token_details` exists so that the run which pulls it does so on a measured reasoning-token
# count rather than on this paragraph. It is a ceiling, not a quota: it costs nothing on the replies
# that finish early, which is now 27 of 42.
MAX_TOKENS = 8000


def load_rubric():
    with open(RUBRIC, encoding="utf-8") as f:
        return json.load(f)


def sections_spec():
    return load_rubric()["sections"]


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def _read(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


_CLEANED = {}            # doc_id -> text with front and back matter removed
_FURNITURE = None        # the report, and the flag that says the pass has run


def corpus_furniture():
    """Run the front/back-matter pass over the whole corpus, once, and cache it.

    ⚑ IT HAS TO BE A CORPUS-WIDE PASS, WHICH IS WHY IT IS NOT INSIDE `load_doc`. Furniture is
    detected by repetition ACROSS documents; a file read on its own carries no evidence that its
    own opening paragraph is a template. So the boundary is the corpus, not the file, and the
    price is one read of everything on first use.
    """
    global _FURNITURE
    if _FURNITURE is None:
        docs = {d: _read(d) for d in documents()}
        cleaned, report = boilerplate.matter(docs)
        _CLEANED.update(cleaned)
        _FURNITURE = report
    return _FURNITURE


def load_doc(doc_id, raw=False):
    """The corpus boundary. The run harness, the `--lead` baseline and the app all read documents
    through here, so the cleaning reaches all three or none of them.

    ⚠︎ AND THAT IS THE POINT, NOT A CONVENIENCE — 2026-08-06. The defect was found in the baseline:
    `lead_summary` takes the first 2,000 characters, and a median of 74.6% of those characters was
    the GAO accessibility notice. `b000` was measuring how well "print the first 2,000 characters"
    summarises a boilerplate notice, and the answer to that is not interesting. But fixing it only
    in the baseline would have left the baseline reading a different document from the model it
    exists to be compared against — two measurements over two inputs, differenced, and the
    difference called a result. That is worse than the defect it fixes.

    `raw=True` returns the file verbatim, for anything that has to show what was removed.
    """
    if raw:
        return _read(doc_id)
    corpus_furniture()
    return _CLEANED.get(doc_id) or _read(doc_id)


def summarise(cfg, doc_text, sections, complete=None, budget_tokens=None, thinking=None):
    """Return the full record for one document.

    `complete` is injectable so the eval harness, the app and the stub all drive the SAME code
    path. One copy of the behaviour, and the seam is a parameter — UC001 learned the cost of the
    alternative, having to port its ranker to JS and then hold two copies identical with a gate.

    `thinking` reaches the provider untouched, or is omitted when None. It is threaded rather than
    read from config here so the stub — which takes no such argument — keeps driving this same
    path, and so a run states its own setting instead of inheriting one from the environment.
    """
    secs = segment.sections(doc_text)
    msgs, parts, plan = P.build(doc_text, secs, sections, pack, budget_tokens)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
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
        # How the output budget was actually spent (reasoning vs visible answer), when the provider
        # reports it. None where it does not — an honest absence, not a fabricated zero.
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
