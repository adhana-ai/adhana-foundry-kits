"""Order the sections and fit them to a token budget. Pure code — the last deterministic step
before the model, and this kit's counterpart of UC001's `retrieve` and UC002's `select`.

⚑ WHY THIS NODE EXISTS AT ALL, AND WHY IT IS THE HONEST ONE TO LOOK AT.
UC002's documents fit in a context window whole; selecting sections there is a cost optimisation.
Here the premise is the opposite — the corpus is 40-80 page reports and a whole one does NOT
reliably fit, so something must decide what the model sees. That decision is the single biggest
lever on the brief's quality and it is made HERE, in pure code, before any model is called.

⚠︎ SO THE FAILURE MODE OF THIS FILE IS NOT A CRASH, IT IS A CONFIDENT BRIEF ABOUT HALF A REPORT.
Whatever is dropped is invisible in the output: the brief reads fluently, every section is filled,
and the grader has no way to know that the findings on page 60 were never sent. That is why
`plan()` returns what was dropped as data and `summarise.py` puts it in the run record — a
measurement about the MODEL is only readable next to what the model was actually given.

THE ORDER IS DOCUMENT ORDER, NOT A RELEVANCE RANKING, and that is a deliberate refusal. Ranking
sections by similarity to the rubric would be a retrieval step, which is UC001's shape wearing
this kit's name — and it would mean the brief's "key findings" came from whichever sections a
scorer liked, with the ranking itself unevaluated. Document order plus an explicit budget is a
decision a reader can audit in one line.
"""

# ⚑ CHARACTERS PER TOKEN, AND IT IS AN ESTIMATE THAT SAYS SO. There is no tokenizer in the
# standard library and this kit has no dependencies, so the budget is enforced on a ratio. 4 is
# the usual English approximation; it is wrong for tables and wrong for code, both of which appear
# in these reports. It is used to decide what to SEND, never to report what was spent — the token
# counts in every run record come from the provider's own usage block.
CHARS_PER_TOKEN = 4

# The default input budget in tokens. Set below what any current model accepts, on purpose: a
# budget that tracks the largest available context makes the kit's result depend on which model
# happened to be configured, and then "we swapped the model" and "we changed the input" are the
# same experiment.
DEFAULT_BUDGET_TOKENS = 24000


def plan(secs, budget_tokens=DEFAULT_BUDGET_TOKENS, reserve_chars=0):
    """Which sections to send, in document order, and what that leaves out.

    Returns {sent, dropped, chars_sent, chars_total, fits} where `sent`/`dropped` are section
    dicts. `reserve_chars` is the room the caller needs for its own prompt scaffolding, subtracted
    from the budget rather than hoped to fit alongside it.

    ⚑ A SECTION IS TAKEN WHOLE OR NOT AT ALL. Cutting one mid-sentence to use the last of the
    budget would produce a brief written partly from a fragment, and nothing downstream could tell
    that from a brief written from the section. A dropped section is a fact the record can carry;
    half a section is a fact nothing can express.
    """
    limit = max(0, budget_tokens * CHARS_PER_TOKEN - reserve_chars)
    sent, dropped, used = [], [], 0
    for s in secs:
        n = len(s["text"])
        if used + n <= limit:
            sent.append(s)
            used += n
        else:
            dropped.append(s)
    # ⚠︎ NEVER SEND NOTHING. A single section larger than the whole budget would otherwise drop
    # the entire document and produce a brief written from an empty context — which the model will
    # cheerfully write anyway. Sending one oversized section and recording the overrun is honest;
    # an empty prompt with a confident answer is the defect this whole estate keeps paying for.
    overran = False
    if not sent and secs:
        sent, dropped, used = [secs[0]], list(secs[1:]), len(secs[0]["text"])
        overran = used > limit

    total = sum(len(s["text"]) for s in secs)
    return {
        "sent": sent,
        "dropped": dropped,
        "chars_sent": used,
        "chars_total": total,
        # ⚑ `fits` USED TO BE `not dropped`, AND THAT WAS A LIE IN EXACTLY THE CASE THAT MATTERS.
        # A headingless 122,000-character report is ONE section: the loop sends nothing, the
        # fallback above sends that one section, `dropped` is empty — and `fits` came back True
        # for a document that overran the budget by 28%. The first real document this kit built
        # was that shape, and the plan line printed "whole document sent" about a prompt three
        # times the size it had budgeted for. A summary field that is right in the ordinary case
        # and wrong in the failure case is worse than no field.
        "fits": (not dropped) and not overran,
        "overran": overran,
        "budget_tokens": budget_tokens,
        "est_tokens_sent": used // CHARS_PER_TOKEN,
    }


def summary(p):
    """The plan as a printable line, for the run harness and the record. Names what was dropped
    rather than only how much — 'Recommendations' being dropped is a different fact from
    'Appendix III' being dropped, and a percentage says neither."""
    if p.get("overran"):
        return ("OVERRAN the budget: one indivisible section of ~%d tokens sent against a budget "
                "of %d. The document could not be cut, so it was sent whole rather than dropped "
                "whole — expect the provider to refuse it or truncate it."
                % (p["est_tokens_sent"], p["budget_tokens"]))
    if p["fits"]:
        return "whole document sent (%d sections, ~%d tokens)" % (len(p["sent"]),
                                                                  p["est_tokens_sent"])
    names = ", ".join(s["name"] for s in p["dropped"][:4])
    more = "" if len(p["dropped"]) <= 4 else " … +%d more" % (len(p["dropped"]) - 4)
    return ("%d of %d sections sent (~%d tokens); DROPPED: %s%s"
            % (len(p["sent"]), len(p["sent"]) + len(p["dropped"]), p["est_tokens_sent"],
               names, more))
