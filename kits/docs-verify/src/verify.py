"""Check one document's claims: resolve the citation, one model call, check the quotes, done.

This is the whole AI layer of the kit, deliberately short — the same split docs-extract's
extract.py and docs-redact's detect.py both make and name: the model does one job, and this file
is small enough that you can see exactly which one.

⚠︎ THERE IS NO RETRIEVAL HERE, AND THAT IS THE KIT'S DEFINING DECISION rather than a shortcut. A
claim arrives already naming its source, and `load_doc` resolves that name — no index, no top-k,
no embedding. Two reasons, and the second is the one that matters:

  1. It is the real question. In production the model has already cited something; what you need
     to know is whether the thing it cited actually says what it claimed. Retrieving a *different*
     document and checking against that answers a question nobody asked.
  2. Without it, this kit would be UC001 with a different prompt. Retrieval is docs-qa's subject.
     Reusing it here would have produced two kits that teach the same lesson twice.

The cost of that decision is stated on the page rather than hidden: this kit cannot catch a claim
that cites the WRONG document. It checks fidelity to the cited source, not choice of source.
"""
import json
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")
CLAIMS = os.path.join(HERE, "data", "claims.jsonl")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as every sibling kit's MAX_TOKENS.
#
# ⚠︎ SIZED FOR A BATCH, WHICH MAKES IT DIFFERENT FROM ITS SIBLINGS' AND WORTH SAYING WHY. The other
# kits answer about one thing per call; this one answers about 8-10 claims per call, each with a
# verdict AND a verbatim quote, so the reply is genuinely longer than docs-redact's handful of
# short span objects. docs-route spent 120 calls discovering a 400-token ceiling was too small and
# docs-extract clipped 20 of 42 documents at 1024, both found by RUNNING rather than by guessing
# bigger. 2000 is a guess sized off the shape of the output, not a measurement. If a real run
# truncates, that is the finding, and `finish_reason` is what will say so.
MAX_TOKENS = 2000


def load_doc(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def load_claims():
    """The labelled set, keyed by document id. Labels are NEVER read by verify() — they exist for
    the scorer. Passing them anywhere near the prompt would be the oldest mistake in evaluation."""
    rows = {}
    with open(CLAIMS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["doc"][:-4]] = r["claims"]
    return rows


def claims_for(doc_id):
    return load_claims().get(doc_id, [])


def _quote_is_real(quote, doc_text):
    """Is the model's cited sentence actually in the document, or did it write one?

    THIS IS THE CHEAPEST HALLUCINATION CHECK IN THE KIT and it is pure code, so it costs nothing
    per run. A model that invents its supporting quote has invented its verdict; the quote is the
    part we can mechanically check, so we check it. Whitespace is normalised before comparing
    because a model reflowing a line it copied correctly is not a fabrication, and failing it for
    that would make the measure useless.
    """
    if not quote:
        return None                      # nothing claimed — not a pass and not a failure
    norm = " ".join(quote.split()).lower()
    hay = " ".join(doc_text.split()).lower()
    return norm in hay


def verify(cfg, doc_text, claims, complete=None, thinking=None):
    """Return the full record for one document: a verdict per claim, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the SAME code
    path — the reason every sibling kit's entry point takes the same parameter.
    """
    msgs, parts = P.build(doc_text, claims)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw, len(claims))

    # ⚑ THE THIRD STATE, the lesson docs-extract paid a run to learn, in this kit's own terms.
    # "The model returned no verdict for claim 4" and "the model said claim 4 is not_stated" are
    # different facts and only the second is a judgement about the document. `parse` already keeps
    # them apart by returning None; this preserves that all the way into the record rather than
    # defaulting a missing verdict to the most common label, which would quietly award a silent
    # model the score of a careful one.
    rows = []
    for i, c in enumerate(claims):
        got = parsed[i]
        rows.append({
            "id": c.get("id"),
            "claim": c["text"],
            "verdict": (got or {}).get("verdict"),        # None = never answered
            "quote": (got or {}).get("quote", ""),
            "quote_in_doc": _quote_is_real((got or {}).get("quote", ""), doc_text),
        })

    answered = sum(1 for r in rows if r["verdict"] is not None)
    parsed_ok = bool((raw or "").strip()) and answered > 0
    return {
        "claims": rows,
        "answered": answered,
        "asked": len(claims),
        "parsed": parsed_ok,
        "raw": raw,
        "parts": parts,
        # ⚠︎ READ FROM THE TOP LEVEL, WHICH IS WHERE adapters.complete() ACTUALLY PUTS THEM. The
        # first version of this file read `res["usage"]["input_tokens"]`, a dict the adapter has
        # never returned, so the first real run recorded 0 input and 0 output tokens for all 20
        # calls — and 0 is a plausible-looking number, so nothing failed. Found by reading the run
        # record rather than by any check, which is the argument for reading run records.
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        "reasoning_tokens": res.get("reasoning_tokens"),
        "model": res.get("model"),
    }
