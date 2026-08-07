"""Align two document texts and return the candidate changed spans. Pure code, no model.

⚑ THIS IS THE "Align" NODE ON THE KIT'S FLOW FIGURE — the deterministic step that runs before the
model, the same role `tools.py`'s taxonomy lookup plays in docs-route and `sel` plays in
docs-extract. The model's job is judging what a change MEANS; finding that a change exists is
arithmetic, and doing it in the prompt would hide a bug in this file behind a bad model answer.

⚑ WORD-LEVEL, NOT CHARACTER-LEVEL. A character diff on prose reports every re-wrapped line as a
change; a word diff reports what a person circling the two texts would circle. `autojunk=False`
because SequenceMatcher's default heuristic exists for source code with repeated boilerplate
lines, and it can drop a genuinely repeated regulatory phrase as "junk" — wrong instinct here.

⚠︎ THE LARGEST SPAN IS TAKEN AS *THE* CHANGE, NOT ALL OF THEM. A correction usually has one point;
a word-level diff of two independently-worded abstracts about the same point often returns several
small spans (a re-ordered clause, a changed date) either side of the real one. Publishing a verdict
per span would let one document cast several votes. `evals/score.py` is scored one verdict per
document pair for exactly this reason — see the note there.
"""
import difflib
import re

_TOKEN = re.compile(r"\S+|\s+")


def _tokens(text):
    return _TOKEN.findall(text or "")


def align(v1_text, v2_text, min_chars=6):
    """Return every non-equal opcode as a span, largest first.

    Each span is {"tag", "v1", "v2"} — v1/v2 are the surface text on each side; `tag` is
    difflib's own word for what happened ("replace", "delete", "insert"), kept because a pure
    insertion or deletion has an empty side and a caller needs to know that is not a bug.
    """
    t1, t2 = _tokens(v1_text), _tokens(v2_text)
    sm = difflib.SequenceMatcher(a=t1, b=t2, autojunk=False)
    spans = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        v1_span = "".join(t1[i1:i2]).strip()
        v2_span = "".join(t2[j1:j2]).strip()
        if len(v1_span) < min_chars and len(v2_span) < min_chars:
            continue                              # whitespace / single-character noise
        spans.append({"tag": tag, "v1": v1_span, "v2": v2_span})
    spans.sort(key=lambda s: len(s["v1"]) + len(s["v2"]), reverse=True)
    return spans


def primary(v1_text, v2_text):
    """The one span this kit asks the model about. None means the two texts are identical after
    tokenising — a real state (see `tools/build_corpus.py`'s skip count), not an error."""
    spans = align(v1_text, v2_text)
    return spans[0] if spans else None
