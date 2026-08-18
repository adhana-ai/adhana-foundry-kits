"""The free string-similarity floor, scored BEFORE any model is called. No key, no dependency,
no network -- `difflib.SequenceMatcher` over normalised text, stdlib only.

⚑ THIS IS A REAL BASELINE, NOT A STRAWMAN, AND THAT MATTERS TO EVERY NUMBER THIS KIT PUBLISHES,
same claim data-match's similarity.py makes about its own field-weighted floor. It is used only as
the LAST resort, after block.py's cheap keys (an explicit record id, an explicit SKU code) have
already settled the easy cases -- which is most of them. Where the correspondence names neither and
more than one candidate remains, this is what a quick script would actually run: compare the
message's own words against each candidate's rendered summary and take the closest one.

⚠︎ WHAT IT CANNOT DO, BY CONSTRUCTION. It cannot read "currently at 100 units" and know that is a
disambiguating clue rather than incidental text -- that is a numeric comparison, not a string
comparison, and evals/baseline.py tries the numeric read FIRST for exactly that reason. Pure text
similarity is what is left once neither an id, a SKU nor a stated number settles it.
"""
import difflib

from src import normalise


def candidate_summary(record):
    return normalise.text("%s %s %d units ship %s ships to %s"
                          % (record["sku"], record["description"], record["qty"],
                             record["ship_date"], record["ship_to"]))


def score(message_text_norm, record):
    return round(difflib.SequenceMatcher(None, message_text_norm,
                                         candidate_summary(record)).ratio(), 4)


def best_candidate(message_text, candidates):
    """The single highest-scoring candidate and its score, or (None, 0.0) for an empty candidate
    set. Ties resolve to the first candidate in the (already record_id-sorted) list -- arbitrary,
    stated, and never hidden inside a silent max()."""
    if not candidates:
        return None, 0.0
    norm = normalise.text(message_text)
    scored = [(score(norm, r), r) for r in candidates]
    scored.sort(key=lambda x: -x[0])
    return scored[0][1], scored[0][0]
