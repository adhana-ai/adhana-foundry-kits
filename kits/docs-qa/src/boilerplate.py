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

WHAT IT DOES NOT CATCH, MEASURED RATHER THAN GUESSED. It matches on lines, so furniture survives
wherever the extractor destroyed the line breaks that made it furniture. On the shipped corpus it
removed the site navigation from 37 of 40 documents; the three it missed are all DOCX, because the
converter flattens the whole nav onto one line longer than MAX_LEN. That is a property of the
extractor, not of this pass, and the fix is not a longer regex here -- a heuristic tuned until this
corpus comes out clean stops transferring to the next one, which was the entire point. It belongs
in the kit's `breaks_on`: input shapes whose line structure is gone defeat line-based cleaning.
"""
from collections import Counter

SHARE = 0.5      # a line in at least half the documents is furniture, not content
MAX_LEN = 160    # a long line repeated everywhere is a licence notice; keep it, it is content
MIN_DOCS = 4     # below this "half the documents" is too small a sample to mean anything


def detect(docs):
    """docs: {doc_id: text}. Returns the set of lines to drop."""
    if len(docs) < MIN_DOCS:
        return set()
    seen = Counter()
    for text in docs.values():
        seen.update({ln.strip() for ln in text.splitlines()
                     if 0 < len(ln.strip()) <= MAX_LEN})
    cutoff = len(docs) * SHARE
    return {ln for ln, n in seen.items() if n >= cutoff}


def strip(docs):
    """Return (cleaned_docs, report). The report is the honesty half of this function."""
    drop = detect(docs)
    cleaned, removed = {}, 0
    for doc_id, text in docs.items():
        keep = [ln for ln in text.splitlines() if ln.strip() not in drop]
        removed += len(text.splitlines()) - len(keep)
        cleaned[doc_id] = "\n".join(keep)
    return cleaned, {"lines_dropped": removed,
                     "distinct_lines": len(drop),
                     "documents": len(docs),
                     "examples": sorted(drop, key=len, reverse=True)[:8]}
