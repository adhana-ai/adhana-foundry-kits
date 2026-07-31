"""SEAM 3 — how a document becomes retrievable pieces.

Chunking is the least glamorous decision in a retrieval pipeline and one of the two or three that
most changes the answers. It is its own file, with its own numbers at the top, so changing it is
one edit and one re-index rather than a hunt.

WHY PARAGRAPH-FIRST RATHER THAN FIXED-WIDTH.
A fixed character window cuts sentences in half, and half a sentence retrieved is a passage the
model has to guess the end of. Splitting on blank lines and only then packing to a target size
keeps whole paragraphs together, which costs a little size variance and buys passages a reader can
check. TARGET and OVERLAP are the knobs; the failure they trade against is real and opposite --
too small and the answer spans two chunks that never both retrieve, too large and the retrieved
context is mostly padding you pay for.
"""
import re

TARGET = 900        # characters, not tokens -- a chunker that needs a tokenizer needs a model
OVERLAP = 150       # carried from the previous chunk, so a fact on a boundary is in both
MIN = 120           # below this a chunk is a heading with nothing under it
MAX = 1800          # a hard ceiling. See below -- TARGET alone is not one.

_SENT = re.compile(r"(?<=[.!?])\s+")


def _cap(part, ceiling=None):
    """Break one oversized paragraph down, gently first and bluntly last.

    WHY THIS EXISTS. The first version of this chunker kept any paragraph whole on the reasoning
    that splitting mid-sentence produces passages a reader cannot check. That reasoning is right
    and the rule built from it was wrong: TARGET is a packing goal, not a ceiling, so a document
    whose extracted text carries few blank lines came out as one chunk. Measured on the shipped
    corpus: target 900, p90 2187, max 15623. A 15K-character passage is most of a prompt, and
    retrieving five of them is a bill with no answer in it.

    So: sentences first, and only a hard cut when a single "sentence" is itself over the ceiling
    (a table, a syntax diagram, a run of code -- text that has no sentence boundaries to find).
    """
    cap = ceiling or MAX
    if len(part) <= cap:
        return [part]
    out, buf = [], ""
    for s in _SENT.split(part):
        if buf and len(buf) + len(s) + 1 > cap:
            out.append(buf)
            buf = s
        else:
            buf = (buf + " " + s) if buf else s
    if buf:
        out.append(buf)
    capped = []
    for c in out:
        capped += [c[i:i + cap] for i in range(0, len(c), cap)] if len(c) > cap else [c]
    return capped


def split(text):
    """Paragraphs, packed to TARGET, capped at MAX.

    Paragraphs are capped at MAX minus the overlap, not at MAX. The first version of this capped
    the PARAGRAPH at MAX and then packed the overlap on top of it, so the emitted chunks ran to
    MAX + OVERLAP + 2 -- measured, exactly 1952 against a stated ceiling of 1800, on 105 of 662
    chunks. A ceiling that the thing it names can exceed is not a ceiling; it is a suggestion with
    a confident variable name.
    """
    room = MAX - OVERLAP - 2
    paras = []
    for p in text.split("\n\n"):
        p = p.strip()
        if p:
            paras += _cap(p, room)
    out, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) + 2 > TARGET:
            out.append(buf)
            buf = (buf[-OVERLAP:] + "\n\n" + p) if OVERLAP else p
        else:
            buf = (buf + "\n\n" + p) if buf else p
    if buf:
        out.append(buf)
    return [c for c in out if len(c) >= MIN]


def chunk_document(doc_id, text, fmt):
    """Chunks carry their provenance. A retrieved passage a reader cannot trace back to a file is
    a quotation with no source, and the whole point of this kit is that every published figure can
    be traced to the run that produced it."""
    return [{"id": "%s#%d" % (doc_id, i), "doc": doc_id, "format": fmt,
             "ordinal": i, "text": c, "chars": len(c)}
            for i, c in enumerate(split(text))]
