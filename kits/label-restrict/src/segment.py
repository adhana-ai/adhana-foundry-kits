"""Cut a document into addressable sections, and locate a value inside one. Pure code.

A segment exists so that an extracted value can name WHERE it was read from -- the span is the
proof, and a value with no span is an assertion.

The cut is on the underlined headings tools/build_corpus.py writes ("Label Restrictions" over a run
of dashes). That is a property of this corpus's own layout, so `sections()` falls back to a single
whole-document segment when it finds no headings at all rather than pretending: a forker's documents
will not have these headings, and one honest segment beats a spurious carve-up.

⚑ AND THIS KIT NEEDED ONE MORE LEVEL THAN A SECTION -- `locate_in_line`, which is a real difference
from the sibling extraction kits and not a flourish. EIGHT RESTRICTIONS SHARE ONE SECTION HERE, and
they are numbers. A section-scoped search for the buffer `5` matches the `5` inside `2.5 L/ha` two
lines above it, on a word boundary, correctly by the regex and wrongly by every other measure: the
span would point a reader at the rate line and invite them to check a citation that appears to hold.
So a field carries the LABEL LINE it is stated on, the search is anchored to that line first, and
the section-wide search survives only as the fallback for a layout that does not carry the line.
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


def _renderings(value):
    """The strings a value could plausibly appear as. A number the model returned as 3.0 is stated
    on the page as `3`, and a span that fails on that is a span lost to formatting rather than to a
    misreading. Ordered longest-first so `12` is never matched by the `1` rendering of something
    else."""
    out = [str(value)]
    if isinstance(value, float) and abs(value - round(value)) < 1e-9:
        out.append("%d" % round(value))
    if isinstance(value, int):
        out.append("%.1f" % value)
    seen, uniq = set(), []
    for s in sorted(out, key=len, reverse=True):
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def locate(text, value):
    """Where in `text` does `value` appear? Returns (start, end) or None.

    Used to turn a model's answer into a span AFTER the fact. It is deliberately literal: if the
    model paraphrased, this returns None and the value ships WITHOUT a span rather than with a
    guessed one. An approximate span pointing at roughly-the-right-place is worse than none -- it
    invites a reader to check, and the check appears to succeed.

    ⚠︎ IT MATCHES ON WORD BOUNDARIES, NOT ON A BARE SUBSTRING. A bare `str.find` would match a
    short value inside an unrelated longer word or number.
    """
    if value in (None, ""):
        return None
    for v in _renderings(value):
        left = r"\b" if re.match(r"\w", v[0]) else ""
        right = r"\b" if re.search(r"\w$", v) else ""
        m = re.search(left + re.escape(v) + right, text, re.IGNORECASE)
        if m:
            return (m.start(), m.end())
    return None


def locate_in_line(text, line_prefix, value):
    """Locate `value` on the line that starts with `line_prefix:`, and nowhere else.

    Returns (start, end) into `text`, or None -- and None here is a real answer, not a fallback
    trigger: it means the value the model returned is not on the line the label states that
    restriction on. The caller decides what to do with that; this function does not widen its own
    search to make a hit appear.
    """
    if not line_prefix or value in (None, ""):
        return None
    pat = re.compile(r"^%s\s*:\s*(.*)$" % re.escape(line_prefix), re.M | re.I)
    for m in pat.finditer(text):
        hit = locate(m.group(1), value)
        if hit:
            base = m.start(1)
            return (base + hit[0], base + hit[1])
    return None


def span_label(secs, start):
    """The human name for an offset: which section it landed in."""
    for s in secs:
        if s["start"] <= start < s["end"]:
            return s["name"]
    return "document"
