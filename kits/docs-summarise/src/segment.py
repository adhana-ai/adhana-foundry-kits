"""Cut a long document into addressable sections. Pure code — no model, no network.

Same node as UC002's, and deliberately the same NAME on the flow: cutting a document into
addressable sections is one operation whether a field or a paragraph is read out of it. Inventing
a synonym per kit is how two kits stop looking like one product.

WHAT DIFFERS IS WHAT THE SECTIONS ARE FOR. In UC002 a section exists so an extracted value can
name where it was read from — the span is the proof. Here nothing is spanned: a section is a unit
of BUDGET. `pack.py` orders these and fits as many as the context allows, and what falls outside
the budget is what the brief will not have seen. So the honest failure of a bad cut is different
too: there it produced a citation pointing at the wrong place, here it produces a brief that
silently missed a part of the document.

The cut is on the underlined headings `tools/build_corpus.py` writes. That is a property of this
corpus's layout, so `sections()` falls back to a paragraph-block carve-up when it finds no
headings — a forker's documents will not have them, and one long section would defeat packing
entirely by making the whole document indivisible.
"""
import re

# A heading is a short line followed by a line of --- or === at least as long as it is.
_RULE = re.compile(r"^(?P<h>[A-Z][^\n]{2,80})\n(?P<r>[-=]{3,})$", re.M)

# ⚑ THE FALLBACK IS BLOCKS OF PARAGRAPHS, NOT ONE SECTION — and this is the difference from
# UC002's fallback, which returns a single whole-document segment. There, one honest segment is
# correct: the document is small and the span is what matters. Here a single section is a
# document that cannot be packed at all, so a 200-page report with no headings would either fit
# whole or be dropped whole. Neither is a summarisation kit. 40 paragraphs per block is arbitrary
# and says so; it exists to make the fallback USABLE, not to be a tuned parameter.
_FALLBACK_PARAS = 40


def sections(text):
    """[{name, start, end, text}] in document order, covering the whole document.

    Offsets are into the ORIGINAL string. Every character belongs to exactly one section; there is
    no gap for content to disappear into unnoticed, which matters more here than in a kit that
    reads single values out — a dropped run of text is exactly what a summariser cannot report.
    """
    marks = [(m.start(), m.group("h").strip()) for m in _RULE.finditer(text)]
    if not marks:
        return _blocks(text)

    out = []
    if marks[0][0] > 0:
        out.append({"name": "header", "start": 0, "end": marks[0][0], "text": text[:marks[0][0]]})
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append({"name": name, "start": pos, "end": end, "text": text[pos:end]})
    return out


def _blocks(text):
    """Headingless documents, cut on blank lines into blocks. Named 'part N' rather than given a
    guessed title: a section name is shown to the reader and printed in the run record, and a
    made-up one reads as structure the document does not have."""
    paras, pos = [], 0
    for chunk in re.split(r"\n\s*\n", text):
        start = text.find(chunk, pos)
        if start < 0:
            continue
        paras.append((start, start + len(chunk)))
        pos = start + len(chunk)
    if not paras:
        return [{"name": "document", "start": 0, "end": len(text), "text": text}]

    out = []
    for i in range(0, len(paras), _FALLBACK_PARAS):
        grp = paras[i:i + _FALLBACK_PARAS]
        s, e = grp[0][0], grp[-1][1]
        out.append({"name": "part %d" % (len(out) + 1), "start": s, "end": e, "text": text[s:e]})
    # Cover the tail so the union of sections is still the whole document.
    if out and out[-1]["end"] < len(text):
        out[-1] = dict(out[-1], end=len(text), text=text[out[-1]["start"]:])
    return out


def coverage(secs, text):
    """How much of the document the sections actually account for, 0.0-1.0.

    ⚑ IT EXISTS BECAUSE A CUT THAT LOSES TEXT IS SILENT. A heading regex that stops matching
    partway through a document produces fewer, larger sections and nothing errors; the brief is
    then written from a document the pipeline quietly truncated. The run record carries this
    number so a low score can be read against it instead of being blamed on the model.
    """
    if not text:
        return 1.0
    return round(sum(s["end"] - s["start"] for s in secs) / float(len(text)), 4)
