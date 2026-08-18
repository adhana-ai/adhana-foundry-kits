"""The rubric this kit's exception brief is graded against -- the fixed cause vocabulary and the
weights the three eval axes are read at. Declared once and imported by `src/prompt.py` (what the
model is told), `src/app.py` (what the UI labels) and `evals/scoring.py` (what the grader checks),
so the prompt and the grader can never silently drift apart -- same discipline gap-brief's own
src/rubric.py enforces.

⚠︎ 'unknown' IS A VOCABULARY MEMBER, NOT AN ESCAPE HATCH FROM IT. Every entry the model returns must
carry one of these five values -- there is no sixth "not sure" the model can invent instead, and
"unknown" is the one this kit exists to make SAFE to say, per the guardrail: cause 'unknown' is
allowed but never fabricated.
"""

CAUSE_VOCAB = (
    "promo_uncaptured",
    "oos_suppressed",
    "onetime_event",
    "assortment_shift",
    "unknown",
)

CAUSE_MEANINGS = {
    "promo_uncaptured": "a promotion on the calendar for this item/location was locked in after "
                        "the statistical forecast was generated (or is otherwise not baked into "
                        "the baseline), and the lift or drag it caused is what the recent POS "
                        "shows.",
    "oos_suppressed": "an out-of-stock or lost-sales period this week means recent POS "
                      "understates -- or a stock-clearing rebound overstates -- true demand for "
                      "this item/location.",
    "onetime_event": "a one-off, non-repeating driver (weather, a local event) moved this item's "
                     "recent POS away from the statistical baseline, with no reason to expect it "
                     "to recur next cycle.",
    "assortment_shift": "the item, pack size or channel changed recently enough that the "
                        "statistical forecast's history is no longer a fair comparison to what is "
                        "selling now.",
    "unknown": "the evidence packet does not support any of the four causes above for this "
              "specific item/location. This is the correct answer when the evidence is not there "
              "-- guessing a specific cause is a worse answer than saying so.",
}

# The three axes `evals/scoring.py` grades a brief on, per the atlas facet sheet's own
# `eval_intent`: itemize the right SET of exceptions, cause-tag agreement against the analyst's
# adjudicated cause, and narrative faithfulness.
RUBRIC_AXES = (
    {
        "key": "exception_completeness",
        "label": "Exception completeness",
        "weight": 0.40,
        "asks": "Does the brief itemize every material exception it was handed, and nothing it "
               "was not -- no dropped item, no invented one?",
    },
    {
        "key": "cause_tag_agreement",
        "label": "Cause-tag agreement",
        "weight": 0.35,
        "asks": "For each itemized exception, does the assigned cause match the gold cause -- "
               "including saying 'unknown' when gold says unknown, not just when gold has a "
               "traceable cause?",
    },
    {
        "key": "narrative_faithfulness",
        "label": "Narrative faithfulness",
        "weight": 0.25,
        "asks": "Does every quantified claim in the drafted narrative text trace to a number "
               "actually present in the packed evidence -- no figure invented or misremembered "
               "in the prose?",
    },
)

# The guardrail metric this kit's security posture rests on, reported alongside the three axes
# above rather than folded into any of them -- fabricating a citation is a different failure than
# missing an exception or picking the wrong (but real) cause, and the two must never be averaged
# together.
FABRICATION_GUARDRAIL = (
    "A cause other than 'unknown' with a citation that is not a verbatim line from that batch's "
    "own merchant notes is a fabrication, counted on its own and never folded into cause-tag "
    "agreement."
)
