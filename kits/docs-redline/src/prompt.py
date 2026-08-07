"""Build the one message pair that asks for a materiality verdict on an already-found change.

⚑ THE MODEL NEVER SEES THE WHOLE DIFF PROBLEM. `diff.py` finds the candidate span before this is
called; the model is given the original excerpt, the corrected excerpt, and asked one question —
does this change what a regulated party must do. Splitting "find it" from "judge it" the same way
docs-route splits "classify" from "abstain": each piece is measured separately, so a bad number
has one place it could be coming from.

⚑ LEVELS COME FROM materiality.py, NEVER TYPED OUT HERE — same reasoning as docs-route's prompt.py:
one copy of the class list means the model, the scorer and this file cannot silently drift apart.
"""
import json

from . import materiality as MT

SYSTEM = (
    "You are reviewing a correction to a regulatory document. You are given the original wording "
    "and the corrected wording of the one place where they differ. You do not summarise the "
    "document, you do not advise on it, and you do not explain the regulation — your only job is "
    "whether this specific change is material or editorial."
)


def _level_block():
    lines = []
    for key in MT.ORDER:
        lines.append('  "%s"  (%s) — %s' % (key, MT.label_of(key), MT.meaning(key)))
    lines.append('  "%s" — you are not confident enough to choose. A person will read it.'
                 % MT.ABSTAIN)
    return "\n".join(lines)


def build(span):
    """span: {"v1": str, "v2": str} from diff.align(). Empty side means pure insertion/deletion —
    stated in the prompt rather than sent as an empty string, which a model tends to read as
    'nothing was given' rather than 'nothing was there'."""
    v1 = span.get("v1") or "(nothing — this text was added by the correction)"
    v2 = span.get("v2") or "(nothing — this text was removed by the correction)"
    user = (
        "Classify this one change.\n\n"
        "LEVELS:\n%s\n\n"
        "ORIGINAL WORDING:\n%s\n\n"
        "CORRECTED WORDING:\n%s\n\n"
        "Answer with JSON only, in this exact shape:\n"
        '{"materiality": "<one key from the list above>", "confidence": <0.0 to 1.0>, '
        '"why": "<one short sentence, at most 20 words>"}'
    ) % (_level_block(), v1, v2)
    return SYSTEM, user


def parse(text):
    """Reply -> {materiality, confidence, why, state}. Never raises — see docs-route's parse()
    for the same four states and why each needs a different fix:
      ok          a valid level came back
      abstained   the model declined, in the word the prompt asked for
      offmenu     valid JSON, but a level this kit does not have
      unparsed    not JSON at all
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    try:
        obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return {"materiality": None, "confidence": None, "why": "", "state": "unparsed",
                "raw": (text or "")[:400]}
    level = str(obj.get("materiality") or "").strip().lower()
    conf = obj.get("confidence")
    try:
        conf = round(float(conf), 3)
    except (TypeError, ValueError):
        conf = None
    why = str(obj.get("why") or "").strip()
    if level == MT.ABSTAIN:
        return {"materiality": None, "confidence": conf, "why": why, "state": "abstained"}
    if level in MT.LEVELS:
        return {"materiality": level, "confidence": conf, "why": why, "state": "ok"}
    return {"materiality": None, "confidence": conf, "why": why, "state": "offmenu",
            "offered": level[:60]}
