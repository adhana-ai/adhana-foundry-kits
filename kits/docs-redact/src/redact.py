"""Turn detected spans into a redacted document and a highlighted one. PURE CODE — no model call
anywhere in this file, and that split is the whole architecture of this kit in one sentence: the
model's only job is to SAY WHERE the sensitive text is; deciding what to do with that answer is
arithmetic on string offsets, the same division of labour as docs-extract's segment.locate()
turning a model's answer into a citation after the fact.

⚠︎ SPANS ARE LOCATED, NOT TRUSTED. A model asked to copy text verbatim occasionally paraphrases or
retypes it anyway — a comma dropped, a dash turned into a space. `locate()` searches for the exact
substring in the source document and reports `start=end=None` when it is not there, rather than
guessing a nearby position. An unlocated span cannot be masked (there is nothing to replace) and
that is surfaced rather than silently dropped: see `detect.py`, which counts it as a leak, because
"the model claimed to see something and code could not find it" is closer to a miss than a hit.

⚠︎ OVERLAPPING SPANS ARE RESOLVED BY POSITION, NOT BY CATEGORY. Two categories occasionally claim
the same or overlapping text — an address span that swallows a phone number sitting on the next
line, say. `_dedupe()` walks spans in document order and keeps the first one to claim each stretch
of text, which is a deliberate, simple tie-break: it means every character of the document is
covered by at most one placeholder, so the redacted output never doubles up `[PHONE][ADDRESS]`
where the source had one span of text.
"""
import html

# category name -> the class the UI's stylesheet keys color on. Lower-cased and ADDRESS shortened
# to match the legend chip labels approved in the wireframe (docs-redact-wireframe.html).
CSS_CLASS = {"NAME": "name", "SSN": "ssn", "EMAIL": "email", "PHONE": "phone",
             "ADDRESS": "addr", "DOB": "dob", "CARD": "card"}


def locate(text, spans):
    """Given `text` and a list of {"text", "category"} (in the order they were reported), find
    where each occurrence actually sits. Returns the same list with "start"/"end" added — both
    None when the exact substring could not be found at all.

    REPEATED IDENTICAL TEXT IS MATCHED IN ORDER, NOT ALL AT ONCE. If a document states the same
    phone number twice and the model reports it twice, the first report is matched to the first
    occurrence and the second to the second — a running cursor per distinct span text, so two
    genuinely different occurrences never collapse onto the same offset.
    """
    cursor = {}
    out = []
    for sp in spans:
        t = sp["text"]
        start_from = cursor.get(t, 0)
        idx = text.find(t, start_from)
        if idx == -1 and start_from > 0:
            # The cursor ran past a real occurrence — e.g. three reports of the same text but only
            # two of them distinguishable in the source. Fall back to the first occurrence rather
            # than reporting "not found" for a span that plainly is in the document.
            idx = text.find(t)
        if idx == -1:
            out.append(dict(sp, start=None, end=None))
            continue
        end = idx + len(t)
        cursor[t] = end
        out.append(dict(sp, start=idx, end=end))
    return out


def _dedupe(located_spans):
    """Sorted, non-overlapping spans, first-claimed wins. Drops anything unlocated."""
    usable = [s for s in located_spans if s.get("start") is not None]
    usable.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    kept, last_end = [], -1
    for s in usable:
        if s["start"] < last_end:
            continue
        kept.append(s)
        last_end = s["end"]
    return kept


def mask(text, located_spans):
    """The redacted document: every claimed span replaced with `[CATEGORY]`. Plain text — this is
    the actual output of the kit, not a display artefact, so it carries no markup to strip later.
    """
    keep = _dedupe(located_spans)
    out, pos = [], 0
    for s in keep:
        out.append(text[pos:s["start"]])
        out.append("[%s]" % s["category"])
        pos = s["end"]
    out.append(text[pos:])
    return "".join(out)


def highlight(text, located_spans):
    """The highlighted document: every claimed span wrapped in `<mark class="span CATEGORY">`,
    left unmasked, for the UI's side-by-side view — never the redacted output itself.

    HTML-ESCAPED HERE, NOT IN THE BROWSER. Every character of the source document passes through
    `html.escape`, spans and gaps alike, before this function returns — so the caller can drop the
    result straight into the page with no further sanitising step for a caller to forget.
    """
    keep = _dedupe(located_spans)
    out, pos = [], 0
    for s in keep:
        out.append(html.escape(text[pos:s["start"]]))
        cls = CSS_CLASS.get(s["category"], s["category"].lower())
        out.append('<mark class="span %s">%s</mark>'
                   % (cls, html.escape(text[s["start"]:s["end"]])))
        pos = s["end"]
    out.append(html.escape(text[pos:]))
    return "".join(out)


def redact(text, spans):
    """Convenience: locate + mask in one call, for a caller that only wants the redacted text."""
    return mask(text, locate(text, spans))


def highlighted(text, spans):
    """Convenience: locate + highlight in one call, for a caller that only wants the display HTML."""
    return highlight(text, locate(text, spans))
