"""Cut a payment package into addressable sections. Pure code — no model, no network.

An extracted value that cannot name WHERE it was read from is an assertion. The span is the
proof, and this is what makes one available: every character of the package belongs to exactly
one named section, so a value found in the reply can be located back to the part of the document
that states it.

The cut is on the underlined headings tools/build_corpus.py writes ("Period Through" over a run
of dashes). That is a property of THIS corpus's layout, so `sections()` falls back to a single
whole-document segment when it finds no headings at all rather than pretending: a general
contractor's own pay-application export will not have these headings, and one honest segment
beats a spurious carve-up.

⚠︎ THE PARTY BLOCKS ARE NOT SECTIONS AND THAT IS DELIBERATE. Every party in a package lives
inside the one `Waiver Coverage` section, indented under a `Party N:` line. Cutting them into
sections of their own would need a second, deeper heading rule that only this corpus satisfies —
and the coverage question is asked ACROSS parties (how many are uncovered, which is the first),
so the whole block has to reach the model together anyway.
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
    extraction, before this guard existed there. It matters more here than in most of them: this
    corpus is full of money amounts that share leading digits, and a party name is often a
    prefix of nothing but happens to sit beside four other names in the same section.
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
