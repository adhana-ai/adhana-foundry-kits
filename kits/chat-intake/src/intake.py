"""One turn of one conversation: what the model read, what it collected, and what to do next.

⚑ THE PIPELINE IS THREE STEPS AND ONLY THE MIDDLE ONE IS A MODEL.

    carry state   pure code. What the turns so far are, and what the checklist still owes.
    extract       one call. Which required facts the conversation has established.
    decide        pure code. `slots.missing()` — a set difference, not a judgement.

⚠︎ NOTHING PERSISTS BETWEEN CALLS, AND THAT IS WHAT KEEPS THIS INSIDE A KIT. Conversation state
rides in the request: `turn()` takes the whole prefix and returns a verdict, with no session, no
store and no id that outlives the call. A kit is four layers — a minimal UI, a pipeline, the AI
layer and the eval layer — and the moment this grows a database it has outgrown that and should be
a different thing. If a future change needs to remember something between requests, that is the
signal, not an inconvenience to work around.
"""
from . import adapters, prompt, slots

MAX_TOKENS = 400


def turn(cfg, intent, turns, complete=None):
    """The whole kit for one turn.

    `complete` is injectable so the eval harness, the app and any stub drive the SAME code path —
    the reason every sibling kit's entry point takes this parameter. A demo that runs different
    code from the eval is a demo of something nobody measured.
    """
    text = prompt.render(intent, turns)
    call = complete or adapters.complete
    res = call(cfg, prompt.SYSTEM, text, max_tokens=MAX_TOKENS)
    raw = res.get("text", "")
    parsed = prompt.parse(raw)

    # An unparseable reply is carried as None all the way to the scorer rather than defaulted to an
    # empty collection. Collecting nothing is a legitimate, often correct answer on an early turn;
    # failing to answer at all is not, and the two must not share a row.
    collected = (parsed or {}).get("collected") or {}
    still = slots.missing(intent, collected) if parsed else slots.required(intent)

    return {
        "intent": intent,
        "turns": len(turns),
        "parsed": parsed is not None,
        "collected": collected,
        "missing": still,
        # The product of the whole kit: not a value, a decision.
        "decision": "ask" if (still or not parsed) else "stop",
        "notes": (parsed or {}).get("notes", ""),
        "raw": raw,
        "prompt": text,
        # ⚠︎ CARRIED THROUGH BECAUSE AN EMPTY REPLY IS UNDIAGNOSABLE WITHOUT IT. The adapter has
        # always returned it and this function has always dropped it. The red team is what made
        # that cost something: three attacks came back with `raw == ""`, and "the model returned
        # nothing" and "the reply was cut off at max_tokens" are opposite findings — one is the
        # model declining to answer a hostile prompt, the other is our own token limit. With the
        # field dropped there was no way to tell them apart after the run, which is the same trap
        # docs-verify's r001 recorded paying for.
        "finish_reason": res.get("finish_reason"),
        # Carried for the same reason and in the same breath: `finish_reason` says the reply was
        # cut off, this says what ate the budget. On the forged-transcript attack the answer is a
        # reasoning pass, and a cut-off reply with no visible content is otherwise indistinguishable
        # from a provider returning nothing.
        "token_details": res.get("token_details"),
        "input_tokens": res.get("input_tokens"),
        "output_tokens": res.get("output_tokens"),
    }


def next_question(intent, missing):
    """What the app shows when the decision is `ask`.

    ⚠︎ TEMPLATED ON PURPOSE, AND NOT A SECOND MODEL CALL. Phrasing the question well is a real
    product problem and it is NOT the one this kit measures — measuring it would need a judge, and
    the entire point here is an eval that runs for free against published ground truth. A second
    call would also double the bill for something no number on the report would cover. So the kit
    ships the plainest possible question and says so, rather than quietly spending on prose nobody
    is grading.
    """
    if not missing:
        return "Nothing further is needed."
    human = missing[0].replace("_", " ")
    return "Which %s?" % human if len(missing) == 1 else \
        "Which %s? (%d still needed: %s)" % (human, len(missing),
                                             ", ".join(m.replace("_", " ") for m in missing))
