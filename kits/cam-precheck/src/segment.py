"""Cut a document into addressable sections. Pure code — no model, no network.

THIS IS THE NODE THAT REPLACED "Index" ON THE FLOW, and the difference is worth stating: an index
exists so that something can be RETRIEVED from a corpus. Nothing is retrieved here. A segment
exists so that an extracted value can name WHERE it was read from — the span is the proof, and a
value with no span is an assertion.

The cut is on the underlined headings build_corpus.py writes ("Cap Basis" over a run of dashes).
That is a property of this corpus's own layout, so `sections()` falls back to a single
whole-document segment when it finds no headings at all rather than pretending: a forker's
reconciliation statements will not have these headings, and one honest segment beats a spurious
carve-up.
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


def _variants(value):
    """Every spelling of one value that could legitimately appear in the document.

    ⚑ THIS IS THE ONE PLACE THIS KIT DIVERGES FROM ITS SIBLINGS' `locate`, AND IT IS A MONEY
    PROBLEM. The sibling extraction kits carry integer quantities — 16,820 kWh, 42 cartons — so
    `str(value)` is exactly what the document says and a literal search finds it. This corpus is
    dollars: the document writes `47800.00 USD` and a model that reads it correctly returns the
    JSON number `47800.0`, whose `str()` is `47800.0`. A literal search then finds NOTHING, and the
    value ships with no span — a correct answer scored as an uncited one, which would have been
    published as a span rate of about 30 pct with nothing wrong with the model at all.

    So a numeric value is searched for in every form the same number can take: as written, at two
    decimals, and as a bare integer when it is integral. It is still LITERAL — no fuzz, no
    proximity, no rounding to a neighbouring number — so the guarantee the span carries is
    unchanged: the text really does say this.
    """
    if value in (None, ""):
        return []
    out = [str(value)]
    if isinstance(value, bool):
        return out
    try:
        n = float(value)
    except (TypeError, ValueError):
        return out
    for form in ("%.2f" % n, "%d" % int(n) if float(n).is_integer() else None, "%g" % n):
        if form and form not in out:
            out.append(form)
    return out


def locate(text, value):
    """Where in `text` does `value` appear? Returns (start, end) or None.

    Used to turn a model's answer into a span AFTER the fact. It is deliberately literal: if the
    model paraphrased, this returns None and the value ships WITHOUT a span rather than with a
    guessed one. An approximate span pointing at roughly-the-right-place is worse than none —
    it invites a reader to check, and the check appears to succeed.

    ⚠︎ IT MATCHES ON WORD BOUNDARIES, NOT ON A BARE SUBSTRING. A bare `str.find` would match a
    short value inside an unrelated longer word — found live in a sibling kit's very first
    extraction, before this guard existed there. Here it also stops a two-digit month from
    matching inside a six-digit floor area.
    """
    for v in _variants(value):
        left = r"\b" if re.match(r"\w", v[0]) else ""
        right = r"\b" if re.search(r"\w$", v) else ""
        m = re.search(left + re.escape(v) + right, text, re.IGNORECASE)
        if m:
            return (m.start(), m.end())
    return None


def span_label(secs, start):
    """The human name for an offset: which section it landed in."""
    for s in secs:
        if s["start"] <= start < s["end"]:
            return s["name"]
    return "document"
