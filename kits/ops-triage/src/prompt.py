"""The verdict vocabulary and the prompt. Declared once, here, and read from here by everything.

⚑ THIS MODULE IS THE SINGLE SOURCE OF THE TWO VERDICTS. The prompt, the parser, the scorer and the
app panel all read `VERDICTS` from this file rather than each holding a copy — a second copy is a
silent disagreement waiting for the day somebody edits one of them.

⚑ TWO VERDICTS, AND THE ABSENCE OF A THIRD IS A DESIGN DECISION, NOT AN OVERSIGHT. See
`src/decide.py`: a pager is a binary actuator. UNSURE would have to be mapped onto ring or
do-not-ring before anything happened, and mapping it quietly to "hold" — the tempting direction,
because it wakes nobody — turns every hesitation into a missed incident hidden inside a calm score.

── WHAT THE MODEL IS SHOWN, AND WHY IT IS NOT ONLY THE RAW LINES ─────────────────────────────────

⚑ THE ABSENCE IS COMPUTED BY CODE AND HANDED OVER AS A FACT. A window in which `payments` emitted
nothing contains, by definition, no line saying so. A model shown only the lines cannot perceive
the absence — not because it is not clever enough, but because the evidence is not in the input.
`src/window.py::gone_silent` compares the window against its history and states the result in one
sentence, and that sentence goes in the prompt.

⚠︎ THIS IS A REAL ARCHITECTURAL CHOICE AND IT MUST BE READ AS ONE. It is the division of labour the
whole kit argues for: **code establishes what is true, the model judges what it means.** The code
does not decide whether silence is an incident — it says "payments emitted nothing here and
averaged 7 lines in the previous six windows", and whether that warrants waking somebody at 03:14
is the judgement being bought. Getting this boundary wrong in the other direction is the classic
failure: hand the model raw lines and ask it to notice what is missing, then publish the result as
evidence that models cannot reason about absence, when in fact nobody put the absence in the
prompt.

⚠︎ AND THE SAME FACT IS AVAILABLE TO THE FLOOR, SO THE COMPARISON STAYS FAIR. `evals/baseline.py`
scores a rules-plus-absence floor alongside the plain one, precisely so nobody can claim the model
won on evidence the rules were never given.

── THE LINES THEMSELVES ───────────────────────────────────────────────────────────────────────────

Collapsed, never paraphrased. 47 identical timeouts become one line reading `×47`, with its first
and last timestamp, because 47 copies of one string is one fact and sending it 47 times is paying
to say it again. Order of first appearance is preserved: a deploy line followed by errors is a
different window from errors followed by a deploy line, and that sequence is most of what
distinguishes the `deploy` trap from a real outage.
"""
VERDICTS = ("PAGE", "HOLD")

# ⚑ THE OUTPUT BUDGET IS PART OF THE PROMPT CONTRACT, SO IT LIVES BESIDE IT — carried over from
# UC011, where `max_tokens=16` cost a run of 78 calls and bought one answer.
#
# The reasoning there was sound and the number was wrong: the prompt asks for one word, one word is
# one or two tokens, so 16 looked generous. It is generous for the ANSWER and says nothing about
# what a model emits BEFORE the answer. The model on this repo's shared `.env` is a REASONING
# model: it emits `reasoning_content` beside `content`, billed inside `completion_tokens`, and
# `content` receives the word only once reasoning has finished. A three-call probe on that kit
# measured 159, then 1,260, then 2,159 characters of reasoning on three pairs — the third exhausted
# a 512-token ceiling mid-thought and returned an empty string with `finish_reason: "length"`.
#
# ⚠︎ A CEILING LOW ENOUGH TO BITE SAVES NO MONEY. Output is billed per token GENERATED, not per
# token allowed, so headroom is free until it is used; a cap that truncates spends the whole call
# and returns nothing, which is the most expensive outcome available. 4096 is headroom, not a
# target, and it is never to be tuned until a score improves. `finish_reason` on every row is what
# proves truncation is not the thing under measurement — not this comment.
MAX_TOKENS = 4096

MEANS = {
    "PAGE": "wake somebody now — this is an incident or is about to become one",
    "HOLD": "do not wake anybody — noise, or something that can wait for the morning",
}

SYSTEM = (
    "You are the on-call triage step for a production system. You are shown one five-minute window "
    "of logs and you decide whether it should wake a human being right now. "
    "Answer with exactly one word: PAGE or HOLD. No explanation, no punctuation."
)

RULES = (
    "How to decide:\n"
    "- PAGE means a person is woken at 3am. Volume alone is not a reason: a check that has been "
    "failing identically for days, a retry storm that recovers, and errors that start at a deploy "
    "and stop on their own are all noise, however many lines they produce.\n"
    "- A single quiet line can be an emergency. An expiring certificate, a replication slot filling "
    "a disk, a batch nobody acknowledged — nothing is on fire yet and something will be.\n"
    "- A service that has stopped logging entirely may be down. If the window states that a service "
    "emitted nothing while it was talking steadily before, treat the silence as evidence.\n"
    "- Do not page for something already recovering inside the same window.\n"
    "- If it can safely wait until the morning, HOLD."
)


def render(win, collapsed, silent=None, history=None):
    """The exact user message sent for one window.

    `silent` is `window.gone_silent`'s answer and `history` the per-service line counts behind it —
    both computed by code, both stated as fact rather than as a hint about what to conclude.
    """
    lines = ["Window %s, five minutes beginning %s." % (win["id"], win["start"]), ""]
    if silent:
        for svc in silent:
            past = (history or {}).get(svc) or []
            lines.append("NOTE: %s emitted no lines at all in this window. In the previous %d "
                         "windows it emitted %s."
                         % (svc, len(past), ", ".join(str(n) for n in past) or "lines steadily"))
        lines.append("")
    if not collapsed:
        lines.append("(no log lines at all in this window)")
    for row in collapsed:
        stamp = row["first"][11:19]
        times = ("  x%d, %s to %s" % (row["count"], row["first"][11:19], row["last"][11:19])
                 if row["count"] > 1 else "")
        lines.append("%s  %-9s %-5s %s%s"
                     % (stamp, row["service"], row["level"], row["message"], times))
    lines += ["", RULES, "", "One word:"]
    return "\n".join(lines)


def parse(reply):
    """A verdict, or None when nothing usable came back.

    ⚠︎ None IS A THIRD OUTCOME AND MUST NOT DEFAULT TO 'HOLD'. Falling back to HOLD would be the
    safe-looking choice — it wakes nobody — and it would silently convert every failed call into a
    held window, hiding a total reliability failure inside the best-looking score this kit can
    produce. `evals/run.py` counts these in their own bucket and excludes them from both rates.
    """
    if not reply:
        return None
    up = reply.strip().upper()
    for v in VERDICTS:                       # a bare word first, so "PAGE." and "PAGE" agree
        if up.rstrip(".!,").strip() == v:
            return v
    hits = [v for v in VERDICTS if v in up]
    return hits[0] if len(hits) == 1 else None
