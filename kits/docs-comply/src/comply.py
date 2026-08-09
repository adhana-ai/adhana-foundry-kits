"""Check one document against the rulebook: load the rules, one model call, check the quotes, done.

This is the whole AI layer of the kit, deliberately short — the same split docs-extract's
extract.py, docs-redact's detect.py and docs-verify's verify.py all make and name: the model does
one job, and this file is small enough that you can see exactly which one.

⚠︎ THERE IS NO RETRIEVAL HERE, AND NO RULE SELECTION EITHER. The rulebook is FIXED and every rule
in it is checked against the whole document, every time. That is the defining shape of this kit
and the reason it needed its own flow variant rather than reusing docs-verify's:

  · docs-verify runs claim -> its own cited source. The unit is a claim, and each one carries the
    document it should be checked against.
  · docs-comply runs a fixed rulebook -> one document. The unit is a RULE, the rulebook is the same
    for every document, and nothing is selected or retrieved. A compliance checker that looked at
    only the rules it thought were relevant would miss exactly the requirement nobody remembered —
    which is the failure a rulebook exists to prevent.

The cost of that decision is stated on the page rather than hidden: the whole document is sent for
every check, so cost scales with document length and rule count together, and the kit gets more
expensive on long documents rather than smarter about them.
"""
import json
import os

from . import adapters, prompt as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(HERE, "data", "corpus")
RULEBOOK = os.path.join(HERE, "data", "rulebook.json")
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚑ THE OUTPUT CEILING, NAMED ONCE — same discipline as every sibling kit's MAX_TOKENS.
#
# ⚠︎ SIZED FOR 41 RULES IN ONE REPLY, which makes it the largest ceiling in the estate and worth
# saying why. docs-verify answers 8-10 claims per call at 2000; this answers 41 rules, each with a
# verdict and a verbatim quote, so a full reply is roughly four times as long. docs-route spent 120
# calls discovering a 400-token ceiling was too small and docs-extract clipped 20 of 42 documents
# at 1024 — both found by RUNNING rather than by guessing bigger. 6000 is a guess sized off the
# shape of the output, not a measurement. If a real run truncates, that is the finding, and
# `finish_reason` is what will say so.
MAX_TOKENS = 6000


def load_doc(doc_id):
    with open(os.path.join(CORPUS, "%s.txt" % doc_id), encoding="utf-8") as f:
        return f.read()


def documents():
    return sorted(fn[:-4] for fn in os.listdir(CORPUS) if fn.endswith(".txt"))


def rulebook():
    """The transcribed rulebook. Read from disk every time rather than cached at import, so a
    regenerated rulebook takes effect without restarting a long-lived app."""
    with open(RULEBOOK, encoding="utf-8") as f:
        return json.load(f)


def rules():
    return rulebook()["rules"]


def load_gold():
    """The gold verdicts, keyed by document id.

    NEVER READ BY check() — they exist for the scorer. Passing them anywhere near the prompt would
    be the oldest mistake in evaluation, and this kit is one function call away from it, so the
    separation is stated rather than assumed.
    """
    rows = {}
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["doc"][:-4]] = r
    return rows


def _quote_is_real(quote, doc_text):
    """Is the model's cited line actually in the document, or did it write one?

    THIS IS THE CHEAPEST HALLUCINATION CHECK IN THE KIT and it is pure code, so it costs nothing
    per run. A model that invents the line satisfying a requirement has invented its verdict; the
    quote is the part we can mechanically check, so we check it. Whitespace is normalised before
    comparing because a model reflowing a line it copied correctly is not a fabrication, and
    failing it for that would make the measure useless.
    """
    if not quote:
        return None                      # nothing claimed — not a pass and not a failure
    norm = " ".join(quote.split()).lower()
    hay = " ".join(doc_text.split()).lower()
    return norm in hay


def check(cfg, doc_text, rule_list, complete=None, thinking=None, prompt=P.DEFAULT_PROMPT):
    """Return the full record for one document: a verdict per rule, and what the call cost.

    `complete` is injectable so the eval harness, the app and the stub all drive the SAME code
    path — the reason every sibling kit's entry point takes the same parameter.

    `prompt` names which SYSTEM variant to send and defaults to the one r001 and r003 ran, so the
    app and any caller that does not ask stay on the published prompt.
    """
    msgs, parts = P.build(doc_text, rule_list, prompt=prompt)
    call = complete or adapters.complete
    kw = {"max_tokens": MAX_TOKENS}
    if thinking is not None:
        kw["thinking"] = thinking
    res = call(cfg, msgs[0]["content"], msgs[1]["content"], **kw)
    raw = res.get("text", "")
    parsed = P.parse(raw, len(rule_list))

    # ⚑ THE FOURTH STATE, the lesson docs-extract paid a run to learn, in this kit's own terms.
    # "The model returned no verdict for rule 17" and "the model said rule 17 is never_addressed"
    # are different facts and only the second is a judgement about the document. `parse` already
    # keeps them apart by returning None; this preserves that all the way into the record rather
    # than defaulting a missing verdict to the most common label. That default would be especially
    # dishonest here: `met` is 74% of this corpus, so a silent model would inherit a passing score.
    rows = []
    for i, r in enumerate(rule_list):
        got = parsed[i]
        quote = (got or {}).get("quote", "")
        rows.append({
            "rule": r["id"],
            "cite": r["cite"],
            "element": r["element"],
            "verdict": (got or {}).get("verdict"),       # None = never answered
            "quote": quote,
            "quote_in_doc": _quote_is_real(quote, doc_text),
        })

    answered = sum(1 for r in rows if r["verdict"] is not None)
    parsed_ok = bool((raw or "").strip()) and answered > 0
    return {
        "rules": rows,
        "answered": answered,
        "asked": len(rule_list),
        "parsed": parsed_ok,
        "raw": raw,
        "parts": parts,
        # ⚠︎ READ FROM THE TOP LEVEL, WHICH IS WHERE adapters.complete() ACTUALLY PUTS THEM. The
        # first version of docs-verify's equivalent read `res["usage"]["input_tokens"]`, a dict the
        # adapter has never returned, so its first real run recorded 0 input and 0 output tokens
        # for all 20 calls — and 0 is a plausible-looking number, so nothing failed. Found by
        # reading the run record rather than by any check.
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
        "finish_reason": res.get("finish_reason"),
        # ⚠︎ AND THE NOTE ABOVE DID NOT SAVE THIS LINE, WHICH MADE THE SAME MISTAKE IT WARNS ABOUT.
        # It read `res["reasoning_tokens"]`, a key adapters.complete() has never returned — the
        # adapter reports the provider's `completion_tokens_details` dict under `token_details`.
        # So this field was null on every record ever written by this kit, and null is a
        # plausible-looking answer for "how much reasoning happened" when the run disabled
        # reasoning, which is exactly what r001 did. Found the moment a run turned reasoning ON:
        # the probe burned 6000 of 6000 output tokens and returned empty text, and the one field
        # that would have said WHY read null. Absent stays None — a provider that does not report
        # the split is a third state, not a zero.
        "reasoning_tokens": (res.get("token_details") or {}).get("reasoning_tokens"),
        "token_details": res.get("token_details"),
        "model": res.get("model"),
    }


def summary(record, gold_row=None):
    """The five numbers the app panel shows, computed in ONE place.

    ⚠︎ THE FIVE BOXES MUST RECONCILE: met + breached + never_addressed + no_verdict == checked.
    That identity is the whole reason there are five boxes and not four. A model that answers about
    thirty of forty-one rules has told you nothing about the other eleven, and folding those into
    "met" would award a silent model the score of a careful one — which is exactly the defect the
    Admin console shipped on all seven use-case tiles for five days before anyone subtracted.
    """
    rows = record["rules"]
    out = {"checked": len(rows), "met": 0, "breached": 0, "never_addressed": 0, "no_verdict": 0}
    for r in rows:
        if r["verdict"] is None:
            out["no_verdict"] += 1
        else:
            out[r["verdict"]] += 1
    assert out["met"] + out["breached"] + out["never_addressed"] + out["no_verdict"] \
        == out["checked"], "the summary boxes do not account for every rule"
    return out
