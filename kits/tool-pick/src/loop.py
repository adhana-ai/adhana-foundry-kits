"""The loop: ask, parse, call, ask again — and stop.

⚑ THIS IS THE ONLY KIT HERE WHERE THE MODEL DECIDES HOW MANY CALLS THE RUN MAKES, WHICH CHANGES
WHAT A COST FIGURE MEANS. Every other kit in this repo spends one call per unit of work, so its
cost is a multiplication. Here it is a distribution with a worst case, and the worst case is the
number that matters when somebody puts this in front of real traffic.

⚑ THE STEP CAP IS THE GUARD, AND IT IS A CONTROL, NOT A CONSTANT. A model that never says DONE
would otherwise call tools until the money ran out. `MAX_STEPS` bounds the calls per request at
`MAX_STEPS` model calls, so the run's worst case is `requests × MAX_STEPS` and is stated BEFORE
the run rather than discovered on an invoice.

⚠︎ HITTING THE CAP IS RECORDED AS ITS OWN FACT, NOT SILENTLY TREATED AS AN ANSWER. `capped` rides
on every row. A run where the cap fired often is a run whose scores describe the cap as much as the
model, and a reader cannot tell that from a percentage.

⚑ AN UNPARSEABLE REPLY IS NOT A TOOL CALL. The model is asked for exactly one line in one of three
shapes; anything else ends the request with `replied=False`, which scores as `no_verdict` and is
excluded from every rate. Guessing at what a malformed line meant would silently convert a
formatting failure into a tool-choice measurement.
"""
from __future__ import annotations

import re
import time

from . import adapters, prompt, tools

# Four model calls per request. Three would not fit a two-step request plus its DONE; five buys
# nothing this corpus can use, since the longest labelled sequence is two tools. Stated here so the
# worst case is arithmetic a reader can check: 120 requests × 4 = 480 calls, absolute maximum.
MAX_STEPS = 4
MAX_TOKENS = 512

# One line, three shapes. Tolerant about spacing and case, strict about the shape — a parser that
# accepts near-misses is a parser that manufactures tool calls the model did not make.
_CALL = re.compile(r"^\s*CALL\s+([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*(.*)$", re.I | re.S)
_DONE = re.compile(r"^\s*DONE\s*\|\s*(.*)$", re.I | re.S)
_NONE = re.compile(r"^\s*NONE\s*\|\s*(.*)$", re.I | re.S)


def parse(text):
    """-> ('call', tool, arg) | ('done', answer) | ('none', why) | ('unparsed', text)."""
    line = (text or "").strip()
    # A model that prefixes its line with prose is common; take the first line that parses rather
    # than the first line, so one stray "Sure!" does not score as a formatting failure.
    for candidate in [line] + [l for l in line.splitlines() if l.strip()]:
        m = _CALL.match(candidate)
        if m:
            return ("call", m.group(1), m.group(2).strip())
        m = _DONE.match(candidate)
        if m:
            return ("done", m.group(1).strip())
        m = _NONE.match(candidate)
        if m:
            return ("none", m.group(1).strip())
    return ("unparsed", line)


def run_one(cfg, request_text, max_steps=MAX_STEPS):
    """One request, start to stop. Returns everything the eval and the page need.

    Nothing is judged here — this returns what HAPPENED, and `score.py` decides what it means.
    Keeping the two apart is what lets the recorded rows be re-scored later without spending
    again, which this estate treats as a different act from a second run.
    """
    transcript, steps = [], []
    called, capped, replied = [], False, True
    answer, ended = None, None

    for n in range(max_steps):
        t0 = time.time()
        res = adapters.complete(cfg, prompt.SYSTEM, prompt.user(request_text, transcript),
                                max_tokens=MAX_TOKENS)
        ms = (time.time() - t0) * 1000.0
        kind = parse(res["text"])
        steps.append({"n": n + 1, "raw": res["text"], "kind": kind[0],
                      "finish_reason": res.get("finish_reason"),
                      "reasoning_chars": res.get("reasoning_chars"),
                      "input_tokens": res.get("input_tokens"),
                      "output_tokens": res.get("output_tokens"),
                      "latency_ms": round(ms, 1)})

        if kind[0] == "call":
            # Recorded under its CATALOGUE name when it resolves, so `called` is a sequence of
            # tools rather than a sequence of spellings — the scorer compares it against the
            # labelled sequence and `TODAY` must not read as a different tool from `today`.
            raw_name, arg = kind[1], kind[2]
            name = tools.resolve(raw_name) or raw_name
            ok, out = tools.call(raw_name, arg)
            # ⚠︎ A REFUSED CALL STILL COUNTS AS A CALL THE MODEL CHOSE TO MAKE. It is in `called`,
            # because the decision under test is what it reached for — not whether the argument
            # happened to be well formed. Dropping refusals would flatter every model that writes
            # bad SQL into looking like one that chose well.
            called.append(name)
            transcript.append({"tool": name, "arg": arg, "ok": ok, "result": out})
            continue

        if kind[0] == "done":
            answer, ended = kind[1], "done"
            break
        if kind[0] == "none":
            answer, ended = kind[1], "declined"
            break
        # unparsed
        replied, ended = False, "unparsed"
        break
    else:
        capped, ended = True, "capped"

    return {"called": called, "transcript": transcript, "steps": steps,
            "answer": answer, "ended": ended, "capped": capped, "replied": replied,
            "model_calls": len(steps),
            "input_tokens": sum(s["input_tokens"] or 0 for s in steps),
            "output_tokens": sum(s["output_tokens"] or 0 for s in steps),
            "latency_ms": round(sum(s["latency_ms"] for s in steps), 1)}
