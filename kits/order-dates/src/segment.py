"""Cut a document into addressable sections. Pure code — no model, no network.

THIS IS THE NODE THAT REPLACED "Index" ON THE FLOW, and the difference is worth stating: an index
exists so that something can be RETRIEVED from a corpus. Nothing is retrieved here. A segment
exists so that an extracted value can name WHERE it was read from — the span is the proof, and a
value with no span is an assertion.

The cut is on the underlined headings build_corpus.py writes ("Recorded Events" over a run of
dashes). That is a property of this corpus's own layout, so `sections()` falls back to a single
whole-document segment when it finds no headings at all rather than pretending: a forker's
documents will not have these headings, and one honest segment beats a spurious carve-up.

⚑ THIS KIT NEEDS A SECOND, FINER CUT AND `numbered()` IS IT. A scheduling order carries many
obligations inside ONE section, so "which section did this value come from" is not a useful answer
here -- every deadline would cite "Deadlines Ordered" and the span would prove nothing. The
paragraph number is the addressable unit, so `numbered()` cuts the ordered paragraphs apart and
src/extract.py locates each row's values INSIDE the paragraph that row claims to have come from.
A value that cannot be found in its own paragraph ships with no span rather than a flattering one.
"""
import re

# A heading is a short line followed by a line of --- or === at least as long as it is.
_RULE = re.compile(r"^(?P<h>[A-Z][^\n]{2,60})\n(?P<r>[-=]{3,})$", re.M)


def sections(text):
    """[{name, start, end, text}] in document order, covering the whole document.

    Offsets are into the ORIGINAL string, so a caller can quote and highlight exactly. Every
    character belongs to exactly one section; there is no gap for a value to hide in.
    """
    marks = [(m.start(), m.group("h").strip()) for m in _RULE.finditer(text)]
    if not marks:
        return [{"name": "document", "start": 0, "end": len(text), "text": text}]

    out = []
    if marks[0][0] > 0:
        out.append({"name": "header", "start": 0, "end": marks[0][0],
                    "text": text[:marks[0][0]]})
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append({"name": name, "start": pos, "end": end, "text": text[pos:end]})
    return out


def locate(text, value):
    """Where in `text` does `value` appear? Returns (start, end) or None.

    Used to turn a model's answer into a span AFTER the fact. It is deliberately literal: if the
    model paraphrased, this returns None and the value ships WITHOUT a span rather than with a
    guessed one. An approximate span pointing at roughly-the-right-place is worse than none —
    it invites a reader to check, and the check appears to succeed.

    ⚠︎ IT MATCHES ON WORD BOUNDARIES, NOT ON A BARE SUBSTRING. A bare `str.find` would match a
    short value inside an unrelated longer word — found live in a sibling kit's very first
    extraction, before this guard existed there.
    """
    if value in (None, ""):
        return None
    v = str(value)
    left = r"\b" if re.match(r"\w", v[0]) else ""
    right = r"\b" if re.search(r"\w$", v) else ""
    m = re.search(left + re.escape(v) + right, text, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def span_label(secs, start):
    """The human name for an offset: which section it landed in."""
    for s in secs:
        if s["start"] <= start < s["end"]:
            return s["name"]
    return "document"


# A numbered ordered paragraph: "  3. The parties shall ..." running to the next number or the end
# of its section. Anchored at the line start so a "30." inside a sentence cannot open a paragraph.
_NUM = re.compile(r"^(?P<n>\d{1,2})\.\s", re.M)


def numbered(text):
    """{paragraph_number: {"n", "start", "end", "text"}} for the ordered paragraphs of a document.

    Offsets are into the ORIGINAL string, exactly as `sections()` returns them, so a caller can
    quote and highlight. A document with no numbered paragraphs returns {} rather than a guess.

    ⚠︎ THE NUMBER IS THE JOIN KEY BETWEEN THE MODEL'S REPLY AND THE ORDER, so it must be read the
    same way by everything. Duplicated numbers are dropped rather than merged: an order that
    numbers two paragraphs 4 is a defect in the order, and silently keeping the second one would
    make a span cite text the reply never read.
    """
    marks = [(m.start(), int(m.group("n"))) for m in _NUM.finditer(text)]
    out, seen = {}, set()
    for i, (pos, n) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        # Stop a paragraph at a blank line followed by a new underlined heading, so the last
        # ordered paragraph does not swallow the section beneath it.
        body = text[pos:end]
        cut = _RULE.search(body)
        if cut:
            back = body.rfind("\n", 0, cut.start())
            end = pos + (back if back > 0 else cut.start())
        if n in seen:
            continue
        seen.add(n)
        out[n] = {"n": n, "start": pos, "end": end, "text": text[pos:end]}
    return out
