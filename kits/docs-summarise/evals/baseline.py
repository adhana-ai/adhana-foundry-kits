"""The null grader and the null summariser. Neither costs anything, and both belong on the board.

⚑ THE NULL BASELINE IS THE FIRST ROW OF THE EVALS BOARD, NEVER A FOOTNOTE.
The kit standard is explicit about this and the reason is arithmetic: a grader that scores every
section 3 already earns 60 of 100 on this rubric, because 3 of 5 is 60% of every weight. Put that
first and a real score of 62 reads as barely better than doing nothing, which it is. Bury it and 62
reads as a pass.

⚑ AND A SECOND BASELINE THIS KIT NEEDS AND THE OTHERS DID NOT: THE LEAD-PARAGRAPH SUMMARISER.
"Take the first N characters of the document" is a summariser. It costs nothing, calls nothing, and
on a well-written report it is not bad — the opening of a GAO letter genuinely says what the report
is about. If a model priced in tokens cannot beat text[:2000], the honest finding is that this task
did not need a model, and that is a finding worth publishing rather than one to avoid discovering.

⚠︎ IT IS NOT SCORED AUTOMATICALLY. Both baselines produce BRIEFS, which a person grades through
`evals/grade.py` exactly like the model's. There is no shortcut where the baseline gets a number
from code while the model gets one from a human — that would compare two different measurements
and call the difference a result.
"""

NULL_GRADE = 3


def null_grades(sections):
    """What a grader who read nothing and gave everything a 3 would produce. Used to compute the
    floor the real score must clear, printed as the board's first row."""
    return {s["key"]: NULL_GRADE for s in sections}


def null_score(sections):
    """The weighted total of that floor. 60.0 on the shipped rubric, and it is 60.0 for ANY rubric
    whose weights total 100 — which is the point. The floor is a property of the scale, not of the
    weights, so re-weighting the rubric does not move it and cannot be used to flatter a run."""
    return round(sum(s["weight"] * NULL_GRADE / 5.0 for s in sections), 2)


def lead_summary(doc_text, sections, chars=2000):
    """The zero-cost summariser: the document's own opening, split across the rubric's sections.

    Every section gets the SAME text, which is deliberately crude and honestly labelled. A cleverer
    split — first paragraph for 'about', any sentence with a digit for 'numbers' — would be a small
    rules engine, and then a low score would be a measurement of my rules rather than of the
    baseline idea. The idea being tested is "the opening of a well-written report is most of a
    brief". This tests exactly that and nothing else.
    """
    lead = (doc_text or "").strip()[:chars]
    return {s["key"]: {"name": s["name"], "weight": s["weight"], "text": lead,
                       "state": "written" if lead else "missing", "grade": None}
            for s in sections}
