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

⚑ AND WHY A SECOND, BLOCK-SHAPED RULE HAD TO BE ADDED FOR SUMMARISATION — 2026-08-06.
Everything above was written for RETRIEVAL, where a bare heading line is worth nothing: nobody
asks a question that "Background" answers, so dropping it costs the index nothing. Summarisation
inverts that. The headings ARE the skeleton the brief is built on, and this corpus proved it the
first time the line rule was pointed at it:

    Results in Brief                     repeated in 39 of 42 documents
    Background                           38 of 42
    Conclusions                          27 of 42
    Recommendations for Executive Action 22 of 42

Every one of those is furniture by the line rule and content by any reader. `strip()` would have
removed all four from all 42 documents — quietly, because it removes lines and reports counts, and
"7,579 lines dropped" reads like a success. That is the failure this module's own preamble warns
about, arriving through the module itself.

WHAT ACTUALLY SEPARATES THEM IS RUN LENGTH, NOT REPETITION. The GAO accessibility notice is twelve
repeated lines in a row. The ordering/mission/contact block at the end is forty. A section heading
is ONE repeated line — two with its underline — surrounded by prose that is unique to the document.
So: a repeated line inside a run of `RUN` or more repeated lines is furniture; an isolated one is a
structural label and stays. Measured over this corpus at RUN=4, no body heading is lost in any of
the 42 documents. The single heading that does disappear is a table-of-contents entry in
GAO-08-896, a document that has no such section — the listing goes and nothing else does.

⚠︎ RUN IS THE ONLY KNOB, AND A POSITION GATE WAS TRIED AND THROWN AWAY. Restricting the pass to
the first 15% and last 25% of each document was the obvious extra guard. It changed the result by
exactly zero lines — every furniture run in this corpus already sits in the front or back matter —
so it was removed rather than shipped. A knob that cannot move the output is not a safeguard, it
is a second thing to explain and a second thing to get wrong on the next corpus.
"""
from collections import Counter

SHARE = 0.5      # a line in at least half the documents of a group is furniture, not content
MAX_LEN = 160    # a long line repeated everywhere is a licence notice; keep it, it is content
MIN_DOCS = 3     # below this there is no group, only a coincidence
SMALL = 5        # groups smaller than this must be unanimous
RUN = 4          # repeated lines in a run this long are furniture; fewer is a heading


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
    """Return (cleaned_docs, report). The report is the honesty half of this function.

    ⚠︎ LINE-SHAPED. This removes every repeated line wherever it sits, including section headings.
    Correct for retrieval, wrong for summarisation — use `matter()` there, and read the preamble
    for the measurement that separates them."""
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


def _blocks(text, drop, run):
    """Mark the lines of one document that belong to a furniture RUN.

    Blank lines neither start a run nor end one — the accessibility notice is a paragraph with
    blank lines in it, and counting them as content would split one twelve-line block into four
    three-line blocks and save every one of them from a threshold of 4. They extend a run without
    counting toward its length, so the threshold still means "four repeated lines".
    """
    lines = text.splitlines()
    furniture = [ln.strip() in drop for ln in lines]
    blank = [not ln.strip() for ln in lines]
    marked = [False] * len(lines)
    i = 0
    while i < len(lines):
        if not furniture[i]:
            i += 1
            continue
        j, count, last = i, 0, i
        while j < len(lines) and (furniture[j] or blank[j]):
            if furniture[j]:
                count += 1
                last = j
            j += 1
        if count >= run:
            for x in range(i, last + 1):      # to `last`, not to `j` — a run ends on its last
                marked[x] = True              # repeated line, not on the blanks trailing it
        i = max(j, i + 1)
    return marked


def matter(docs, formats=None, run=RUN):
    """Drop front and back matter, keeping the headings. Returns (cleaned_docs, report).

    The block-shaped counterpart of `strip()`, and the one a summarisation kit wants. Same
    detection, different removal: a repeated line is only dropped when it sits in a run of `run`
    or more of them.

    The report carries `kept_isolated` — the repeated lines this pass deliberately LEFT — because
    the interesting question about a cleaner is never what it removed, it is what it decided was
    content. That list is where a heading being eaten would show up as an absence.
    """
    drop = detect(docs, formats)
    cleaned, removed, dropped_lines = {}, 0, set()
    kept = set()
    for doc_id, text in docs.items():
        lines = text.splitlines()
        marked = _blocks(text, drop, run)
        cleaned[doc_id] = "\n".join(ln for ln, m in zip(lines, marked) if not m)
        removed += sum(marked)
        for ln, m in zip(lines, marked):
            if ln.strip() in drop:
                (dropped_lines if m else kept).add(ln.strip())
    return cleaned, {"rule": "run>=%d" % run,
                     "lines_dropped": removed,
                     "distinct_dropped": len(dropped_lines),
                     "documents": len(docs),
                     "per_format": bool(formats),
                     "kept_isolated": sorted(k for k in kept if len(k.strip("-= ")) > 2)[:12],
                     "examples": sorted(dropped_lines, key=len, reverse=True)[:8]}
