"""Drop the navigation, headers and footers that every document in a corpus repeats.

WHY THIS EXISTS. The first index built from the shipped corpus put the site's navigation chrome
into 41 chunks spread across all 40 documents. Those chunks retrieve -- they contain real words --
and they can never answer anything, so they crowd out passages that could. Left in, the eval would
have been measuring how well the pipeline copes with boilerplate rather than how well it retrieves.

WHY IT IS A CROSS-DOCUMENT PASS AND NOT A PER-FILE RULE. The obvious fix is a selector or a regex
that knows what this corpus's nav looks like. That fix works exactly once, for one website, and
makes the kit worse for the forker pointing it at their own files. Repetition is the actual signal:
a line that appears in most documents of a collection is furniture, whatever the collection is. So
the rule is corpus-shaped rather than source-shaped, and it transfers.

IT REPORTS WHAT IT REMOVED. Silent cleaning is how a corpus quietly stops containing the thing you
were trying to retrieve. Every dropped line is returned and printed at index time, so if this pass
ever eats real content the evidence is on screen rather than in a diff nobody reads.

WHY IT LOOKS WITHIN A FORMAT AS WELL AS ACROSS THE CORPUS. The first version counted lines over the
whole corpus and missed nearly everything it was built for. The reason is the corpus's own design:
it is deliberately heterogeneous, and each converter renders the SAME furniture differently -- the
site nav arrives as "- home" in markdown, "•home" in docx, and "sqlite search documentation go" in
PDF. No single spelling reached half the corpus, so a corpus-wide threshold saw three rare lines
instead of one piece of furniture in three costumes. Furniture is a property of the template a
document came from, and in a mixed corpus the format is the closest available proxy for template.
So detection runs per format group as well as globally, and the two drop sets are unioned.

Small groups get a stricter rule, not a looser one: a line has to be in EVERY document of a group
with fewer than SMALL documents, because "2 of 3" is a coincidence and "3 of 3" is a template.

WHAT IT STILL DOES NOT CATCH, MEASURED RATHER THAN GUESSED. It matches on lines, so furniture
survives wherever the extractor destroyed the line breaks that made it furniture. The fix for that
is not a longer regex here -- a heuristic tuned until this corpus comes out clean stops
transferring to the next one, which was the entire point. It belongs in the kit's `breaks_on`:
input shapes whose line structure is gone defeat line-based cleaning.
"""
from collections import Counter

SHARE = 0.5      # a line in at least half the documents of a group is furniture, not content
MAX_LEN = 160    # a long line repeated everywhere is a licence notice; keep it, it is content
MIN_DOCS = 3     # below this there is no group, only a coincidence
SMALL = 5        # groups smaller than this must be unanimous


def _repeated(texts):
    if len(texts) < MIN_DOCS:
        return set()
    seen = Counter()
    for text in texts:
        seen.update({ln.strip() for ln in text.splitlines()
                     if 0 < len(ln.strip()) <= MAX_LEN})
    share = 1.0 if len(texts) < SMALL else SHARE
    return {ln for ln, n in seen.items() if n >= len(texts) * share}


def detect(docs, formats=None):
    """docs: {doc_id: text}. formats: {doc_id: format}. Returns the set of lines to drop."""
    drop = _repeated(list(docs.values()))
    if formats:
        groups = {}
        for doc_id, fmt in formats.items():
            if doc_id in docs:
                groups.setdefault(fmt, []).append(docs[doc_id])
        for texts in groups.values():
            drop |= _repeated(texts)
    return drop


def strip(docs, formats=None):
    """Return (cleaned_docs, report). The report is the honesty half of this function."""
    drop = detect(docs, formats)
    cleaned, removed = {}, 0
    for doc_id, text in docs.items():
        keep = [ln for ln in text.splitlines() if ln.strip() not in drop]
        removed += len(text.splitlines()) - len(keep)
        cleaned[doc_id] = "\n".join(keep)
    return cleaned, {"lines_dropped": removed,
                     "distinct_lines": len(drop),
                     "documents": len(docs),
                     "per_format": bool(formats),
                     "examples": sorted(drop, key=len, reverse=True)[:8]}
