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
"""
from __future__ import annotations

from . import tools

SYSTEM = (
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
