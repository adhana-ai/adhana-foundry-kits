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

# ⚑ 400 STAYS, AND THE RECORDS ARE WHY — measured 2026-08-09, before spending anything on the
# alternative. The obvious reading of r006 is that the ceiling is clipping answers: 51 of pro's 52
# unparsed replies carry `finish_reason=length`, and pro pays 29.4% of its output bill for silence.
# Raising it looks like the fix. It is not, and three numbers off the existing result files settle
# it without a call:
#
#   the visible answer is 18 output tokens at p50 and 46 at its LARGEST, on both tiers. The
#   ceiling has never once clipped a JSON answer — it sits at 8.7x the biggest one ever produced.
#
#   every unparsed reply spent essentially the whole budget on REASONING and emitted no visible
#   content at all: 63 of 63 across both tiers carry `reasoning_tokens` of 378-400 out of 400.
#   `token_details` is a genuine provider field, not a mirror of `output_tokens` — the two differ
#   on 252 of r006's 298 records, where reasoning is ~85-95% and the answer is the remaining sliver.
#
#   and it was probed directly. `rt003-fakeline-400` vs `rt003-fakeline-1600` is the same failing
#   case at 4x the ceiling: still `parsed: false`, still `finish_reason=length`, 1600 output tokens
#   instead of 400. Four times the bill, the same silence.
#
# So the failure is a runaway reasoning pass that never reaches the answer, and a bigger budget buys
# a longer one. Raising this constant would cost more on EVERY call to recover nothing measurable —
# which is the opposite of what the number looks like it is asking for.
#
# ⚠︎ WHAT THIS IS NOT IS A CLAIM THAT THE UNPARSED REPLIES ARE FINE. They are 4.0% of flash and
# 17.5% of pro, they are real failures, and `budget_exhausted` below exists to make them countable.
# The fix is whatever stops the reasoning loop starting, and that is not a knob in this file.
MAX_TOKENS = 400

# ⚑ TWO UNANSWERED TURNS IN A ROW IS AN INCIDENT, NOT A THIRD QUESTION — added 2026-08-09 after the
# red team. Failing safe is not the same as failing visibly: an unparsed reply carries no collected
# facts, so the set difference returns the whole checklist and the pipeline politely asks again. On
# a hostile input that loop is the attack's payoff — a full-price call per turn, no answer, and
# nothing anywhere counting how often it happens. Two is the threshold because one unparsed reply
# is ordinary (it happened once in 40 on a clean run) and two in a row is not.
UNPARSED_LIMIT = 2


def turn(cfg, intent, turns, complete=None, unparsed_before=0):
    """The whole kit for one turn.

    `complete` is injectable so the eval harness, the app and any stub drive the SAME code path —
    the reason every sibling kit's entry point takes this parameter. A demo that runs different
    code from the eval is a demo of something nobody measured.

    ⚑ `unparsed_before` RIDES IN THE REQUEST, exactly as the conversation prefix does, and for the
    same reason: this kit holds no state between calls and a streak counter is not the thing to
    break that for. The caller carries it, the same way it already carries every turn.

    ⚠︎ AND ESCALATION IS A SEPARATE FLAG, NOT A THIRD `decision`. `decision` has two values, the
    grader scores them, and every published number is over those two — quietly adding a third
    would silently change what every rate on the page means. `escalate` sits beside it.
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

    streak = 0 if parsed else int(unparsed_before or 0) + 1

    return {
        "intent": intent,
        "turns": len(turns),
        "parsed": parsed is not None,
        "collected": collected,
        "missing": still,
        # The product of the whole kit: not a value, a decision.
        "decision": "ask" if (still or not parsed) else "stop",
        "unparsed_streak": streak,
        "escalate": streak >= UNPARSED_LIMIT,
        # ⚑ THE ONE GUARDRAIL THE RED TEAM'S DATA ACTUALLY EARNED. Measured over every record that
        # carries a finish_reason: this signature fires 9 times, every one of them an attack, and
        # it explains 100% of the unparsed replies with no false positive on any control or clean
        # case. The provider was telling us the whole time — `finish_reason` arrived on every call
        # and nothing read it. It costs no model call, it is not a heuristic, and it names the
        # attack on its first appearance instead of on a red-team run.
        #
        # ⚠︎ IT IS A FLAG, NOT A REFUSAL. The decision is unchanged and stays `ask`: a caller that
        # dropped the turn on this signal would hand an attacker a way to kill any conversation.
        # What it buys is that the failure is now VISIBLE and countable rather than silent.
        "budget_exhausted": (res.get("finish_reason") == "length" and parsed is None),
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


def next_question(intent, missing, escalate=False):
    """What the app shows when the decision is `ask`.

    An escalation is NOT phrased as a question, because the whole point is that asking again is
    what stops. Whoever is watching gets told what happened rather than the customer getting a
    fourth prompt they cannot satisfy.

    ⚠︎ TEMPLATED ON PURPOSE, AND NOT A SECOND MODEL CALL. Phrasing the question well is a real
    product problem and it is NOT the one this kit measures — measuring it would need a judge, and
    the entire point here is an eval that runs for free against published ground truth. A second
    call would also double the bill for something no number on the report would cover. So the kit
    ships the plainest possible question and says so, rather than quietly spending on prose nobody
    is grading.
    """
    if escalate:
        return ("%d replies in a row could not be read. Handing this to a person rather than "
                "asking again." % UNPARSED_LIMIT)
    if not missing:
        return "Nothing further is needed."
    human = missing[0].replace("_", " ")
    return "Which %s?" % human if len(missing) == 1 else \
        "Which %s? (%d still needed: %s)" % (human, len(missing),
                                             ", ".join(m.replace("_", " ") for m in missing))
