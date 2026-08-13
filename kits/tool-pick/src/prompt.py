"""The prompt, assembled in one place so the published one is the one that ran.

⚑ THE CATALOGUE IS RENDERED FROM `tools.CATALOGUE`, NOT RETYPED HERE. Two descriptions of the same
four tools is two descriptions that drift, and the one that drifts is always the one the model
reads. The guard and the prompt therefore cannot disagree about what exists.

⚑ THE STOP INSTRUCTION IS PART OF THE TASK, NOT A FORMATTING NOTE. This kit measures whether the
model knows when to stop, so "stop when you have enough" has to be asked for explicitly — grading a
model on an instruction it was never given measures the prompt, not the model.

⚠︎ AND DECLINING IS OFFERED, NOT IMPLIED. UC011 offered `UNSURE` 78 times and the model used it 0
times, which is only interpretable because the option was on the wire. `NONE` here is the same
move: if the model never uses it, that is a measurement about the model rather than an ambiguity
about the prompt.

⚑ THERE ARE TWO PROMPTS IN THIS FILE AND THE OLDER ONE IS PINNED, NOT DEAD. `SYSTEM_R015` is the
exact wire text that produced every published number on this kit. Editing it in place would have
left the app rendering a prompt that never ran — the spec carries this text verbatim — and this
estate's rule is that nothing is authored from intent. So the correction is a NEW version, and the
old one stays byte-for-byte as the provenance of r015.

⚠︎ WHAT WAS WRONG: THE PROMPT AND THE CORPUS DISAGREED ABOUT `calc`. The prompt said "call a tool
only when you cannot answer without it"; the corpus labelled `calc` REQUIRED on every two-step
request. 14 requests were scored `stopped_early` for obeying the prompt, and all 14 answers were
correct (verified against the shipped database — see `evals/rescore.py`). That is a specification
defect, not a model failure, and it is the reason the fix belongs here.

⚠︎ AND THIS IS NOT TUNING THE PROMPT TO THE OBSERVED FAILURE, which this estate forbids. The change
settles a contradiction and touches nothing else: the rules governing the traps the model actually
failed — `unanswerable`, and the 26 requests that came back empty — are unchanged, word for word.
A prompt edited toward the failures would have started there.

⚠︎ NOT RUN. `SYSTEM_V2` has never been sent to a model. No number on this kit comes from it, and
the difference between "the fix is written" and "the fix is measured" is the whole of what a future
run would buy.

⚑ AND THE RULER MOVES WITH IT. `evals/rescore.py` scores `calc` as OPTIONAL, which is right for
r015 because r015 was told it was. Under V2 `calc` is required in as many words, so a run on V2
must be scored STRICTLY — `src/score.py:outcome`, not `rescore.outcome_v2`. Carrying r015's lenient
ruler onto a V2 run would forgive exactly the instruction V2 adds.
"""
from __future__ import annotations

from . import tools

# ⚠︎ PINNED — THE WIRE TEXT OF r015. Do not edit. Every published figure on this kit was produced
# under this exact string, and the app spec carries a verbatim copy of it.
SYSTEM_R015 = (
    "You answer a request by calling tools, one at a time, and you stop as soon as you can "
    "answer.\n\n"
    "The tools you may call, and there are no others:\n%s\n\n"
    "Reply with EXACTLY ONE line, and nothing else:\n"
    "  CALL <tool> | <argument>   to call a tool\n"
    "  DONE | <answer>            when you can answer, including from what you already know\n"
    "  NONE | <why>               when no tool here can answer it and you should not guess\n\n"
    "Rules:\n"
    "- Call a tool only when you cannot answer without it. Calling one you did not need is a "
    "failure, not caution.\n"
    "- Some requests need two tools in order, where the second needs what the first returned.\n"
    "- Some requests need no tool at all. Answer those with DONE straight away.\n"
    "- Some requests cannot be answered by these tools. Answer those with NONE. Do not guess and "
    "do not run a query that cannot contain the answer.\n"
) % tools.catalogue_text()

# The corrected prompt. ONE rule is added and one is qualified; every other line is identical to
# `SYSTEM_R015`, which is checked mechanically below rather than left to the eye.
SYSTEM_V2 = (
    "You answer a request by calling tools, one at a time, and you stop as soon as you can "
    "answer.\n\n"
    "The tools you may call, and there are no others:\n%s\n\n"
    "Reply with EXACTLY ONE line, and nothing else:\n"
    "  CALL <tool> | <argument>   to call a tool\n"
    "  DONE | <answer>            when you can answer, including from what you already know\n"
    "  NONE | <why>               when no tool here can answer it and you should not guess\n\n"
    "Rules:\n"
    "- Call a tool only when you cannot answer without it. Calling one you did not need is a "
    "failure, not caution.\n"
    "- Arithmetic is the one exception: put EVERY calculation through calc, including ones you "
    "could do in your head. The number in your answer has to be one a reader can check, and a "
    "number you worked out yourself leaves nothing to check.\n"
    "- Some requests need two tools in order, where the second needs what the first returned.\n"
    "- Some requests need no tool at all. Answer those with DONE straight away.\n"
    "- Some requests cannot be answered by these tools. Answer those with NONE. Do not guess and "
    "do not run a query that cannot contain the answer.\n"
) % tools.catalogue_text()

# What a NEW run would send. `loop.py` reads this name, so the version in use is one line, in one
# place, and a run cannot quietly disagree with what this file says is current.
SYSTEM = SYSTEM_V2
VERSION = "v2"

VERSIONS = {
    "r015": {"text": SYSTEM_R015, "ran": True, "run_id": "r015-tool-pick-flash",
             "note": "every published number on this kit"},
    "v2": {"text": SYSTEM_V2, "ran": False, "run_id": None,
           "note": "calc made unambiguous; NEVER RUN, so no published number comes from it. Score "
                   "a v2 run with src/score.py:outcome, not evals/rescore.py:outcome_v2."},
}


# ⚑ THE PIN IS SELF-CHECKING, BECAUSE A COMMENT SAYING "DO NOT EDIT" HAS NEVER STOPPED AN EDIT.
# This is the SHA-256 of the exact string r015 was run with. If someone improves the wording of the
# pinned prompt, every published number on this kit silently loses its provenance and nothing else
# in the repo would notice — so importing this module fails instead.
#
# ⚠︎ It covers the whole assembled string, catalogue included, so a change to `src/tools.py` breaks
# it too. That is deliberate and not over-reach: the catalogue is interpolated INTO the prompt, so
# editing a tool description changes what r015 was sent just as surely as editing a rule.
R015_SHA256 = "b6d97214135a6dfc3e2d2ddf4cd7f490a986a51f6376ff5e956645504c12a694"


def _check_pin():
    import hashlib
    got = hashlib.sha256(SYSTEM_R015.encode("utf-8")).hexdigest()
    if got != R015_SHA256:
        raise AssertionError(
            "SYSTEM_R015 has been edited. It is the wire text of the published run and every "
            "number on this kit is traceable to it.\n  expected %s\n  got      %s\n"
            "If a tool description changed, r015's prompt changed with it — re-pin only when you "
            "have decided the published numbers no longer describe this prompt." % (R015_SHA256, got))


def diff_from_r015():
    """The exact lines V2 adds or drops, so the claim "one rule added, nothing else touched" is
    something a reader can check rather than something this file asserts about itself."""
    a = SYSTEM_R015.splitlines()
    b = SYSTEM_V2.splitlines()
    return {"added": [l for l in b if l not in a], "removed": [l for l in a if l not in b]}


_check_pin()


def user(request_text, transcript):
    """The request, plus every tool result so far, verbatim and in order."""
    out = ["REQUEST: %s" % request_text]
    if transcript:
        out.append("\nWhat you have called so far:")
        for step in transcript:
            out.append("  CALL %s | %s" % (step["tool"], step["arg"]))
            out.append("  -> %s" % (step["result"] if step["ok"] else "REFUSED: " + step["result"]))
    else:
        out.append("\nYou have not called anything yet.")
    out.append("\nYour one line:")
    return "\n".join(out)


def parts(request_text, transcript):
    return [{"name": "system", "text": SYSTEM},
            {"name": "request and transcript", "text": user(request_text, transcript)}]
