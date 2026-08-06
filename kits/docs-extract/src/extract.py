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

# ⚑ THE OUTPUT CEILING, NAMED ONCE. It used to be a literal in the call below, and the run
# harness printed its own sentence about "3000 output tokens" without being able to say whether
# 3000 was the reply or the limit. It was both, and a reader of the artifact could not tell:
# run 2's four failures each consumed the entire budget and were cut off mid-JSON, and that got
# recorded as an unexplained defect for a day. A number two files reason about belongs to one.
#
# ⚠︎ LEFT AT 3000 ON PURPOSE, 2026-08-05, AFTER THE SIBLING KIT RAISED ITS OWN. docs-summarise hit
# the identical wall — 36 of 42 briefs lost, every failure sitting exactly on its ceiling — and
# raised 4000 to 8000 on evidence: it still had its truncated replies, and one showed a real answer
# running orderly through five of six sections before it stopped mid-sentence. THIS kit has no such
# evidence. Run 2 kept `output_tokens` and threw the text away, so all four of its failures carry
# an EMPTY raw_text, and the question above — why does a NINE-FIELD record run to 3000 tokens? —
# is still unanswered.
#
# Raising it here would be a guess, and the two candidate explanations want opposite fixes. If the
# model is emitting a genuinely long record, the ceiling is too low. If it is emitting reasoning
# tokens — DeepSeek counts those in completion_tokens and never returns them as text, which is what
# docs-summarise's evidence suggests dominated there, two of its captured replies holding ~200
# tokens of visible text against a reported 4,000 — then a bigger ceiling just buys more of the
# same and the fix is a provider parameter. `finish_reason` is recorded now and raw_text is kept,
# so the next run answers it outright. Raise this WHEN that run says which one it is, not before.
MAX_TOKENS = 3000


def load_fields():
    with open(FIELDS, encoding="utf-8") as f:
        return json.load(f)["fields"]


def load_doc(nct_id):
    with open(os.path.join(CORPUS, "%s.txt" % nct_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def extract(cfg, doc_text, fields, complete=None, thinking=None):
    """Return the full record for one document.

    `complete` is injectable so the eval harness, the app and the tests all drive the SAME code
    path against a stub provider. UC001 learned this the expensive way from the other direction:
    the ranker had to be ported to JS and then held identical by a gate, because two copies of one
    behaviour drift. Here there is one copy and the seam is a parameter.

    `thinking` reaches the provider untouched, or is omitted when None. It is threaded rather than
    read from cfg so that a stub `complete` -- which takes no such argument -- is never handed one:
    the harness leaves it None on every free path, and a run that sent nothing records nothing.
    """
    secs = segment.sections(doc_text)
    msgs, parts, used = P.build(doc_text, secs, fields, selector)
    call = complete or adapters.complete
    # ⚠︎ 1024 CLIPPED 20 OF 42 DOCUMENTS ON THE FIRST PAID RUN, and the clipping was invisible:
    # a truncated JSON object fails to parse, parse() returns {}, and nine empty fields read as
    # nine model misses. The header fields gave it away -- nct_id missed on exactly the same 20
    # documents it missed brief_title, on a value printed at the top of the page.
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    values = P.parse(raw, fields)
    # ⚑ THE THIRD STATE, AGAIN, AND IT COST A PAID RUN TO LEARN. "The model returned nothing for
    # this field" and "the model's whole reply was unreadable" are different facts, and only the
    # first one is about the model's judgement. An unparseable reply is reported to the caller so
    # the run can record it as a FAILED DOCUMENT rather than scoring it as nine refusals.
    parsed_ok = bool(values) and any(v is not None for v in values.values())

    out = {}
    for f in fields:
        name = f["name"]
        v = values.get(name)
        if v in ("", "null", "None"):        # a model writing the word rather than the value
            v = None
        # ⚑ AN ENUM CAN NEVER HONESTLY CARRY A SPAN, AND THAT IS NOT A FAILURE.
        #
        # The prompt tells the model two things that conflict for exactly these fields: "copy
        # values verbatim" and "use the exact allowed value for a field that lists them". For
        # `sex` the document says "both males and females" and the answer is ALL; for `allocation`
        # it says "randomly assigned" and the answer is RANDOMIZED. The canonical token is not IN
        # the document, by design, so searching for it can only ever return nothing — or, before
        # the word-boundary fix, something spurious.
        #
        # So spannable is a property of the FIELD, and a non-spannable field is a third state:
        # not "no span found" (a miss) but "a span was never applicable". Rolling those together
        # is what would make span_rate look like a failing guardrail when it is a category error.
        spannable = f.get("type") != "enum"
        span = segment.locate(doc_text, v) if (v is not None and spannable) else None
        out[name] = {
            "value": v,
            "spannable": spannable,
            # ⚠︎ A SPAN IS EVIDENCE, SO IT IS NEVER GUESSED. `locate` is a literal, word-boundary
            # search; a paraphrased value gets value-without-span, and the app renders that
            # honestly rather than pointing a reader at approximately the right place.
            "span": ({"start": span[0], "end": span[1],
                      "section": segment.span_label(secs, span[0])} if span else None),
        }
    return {
        "fields": out,
        "sections_used": used,
        "prompt_parts": parts,
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        # ⚠︎ THESE TWO WERE DROPPED HERE, AND ONE OF THEM SILENTLY DISABLED A FIX MADE THE SAME DAY.
        # The adapter began returning `finish_reason` on 2026-08-05 so a failure could say why it
        # stopped IN THE PROVIDER'S OWN WORD instead of leaving a reader to compare output_tokens
        # against the cap by eye — and evals/run.py duly reads `r.get("finish_reason")`. But this
        # dict is what `r` IS, and it never carried the key, so that read was always None and the
        # only thing still classifying a ceiling stop was the token-count fallback beside it. The
        # fix compiled, shipped and did nothing; no run has been fired since, so it would have
        # written `finish_reason: null` on every failure of the next one.
        #
        # A seam that drops a field is indistinguishable from a provider that never sent it.
        "finish_reason": res.get("finish_reason"),
        "token_details": res.get("token_details"),
        "raw_text": raw,
        "parsed": parsed_ok,
    }
