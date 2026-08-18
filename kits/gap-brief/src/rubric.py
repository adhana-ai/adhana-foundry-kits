"""The rubric this kit's brief is graded against -- the sections a gap brief must carry, the fixed
cause vocabulary, and the weights the three eval axes are read at. Declared once and imported by
`src/prompt.py` (what the model is told), `src/app.py` (what the UI labels) and `evals/scoring.py`
(what the grader checks), so the prompt and the grader can never silently drift apart -- the same
discipline docs-summarise's own rubric.json enforces from a data file rather than two copies of
prose.

⚠︎ 'unknown' IS A VOCABULARY MEMBER, NOT AN ESCAPE HATCH FROM IT. Every entry the model returns must
carry one of these six values -- there is no seventh "not sure" the model can invent instead, and
"unknown" is the one this kit exists to make SAFE to say, per the guardrail: cause 'unknown' is
allowed but never fabricated.
"""

CAUSE_VOCAB = (
    "timing_lag",
    "assumption_mismatch",
    "data_entry_error",
    "scope_mismatch",
    "unknown",
)

CAUSE_MEANINGS = {
    "timing_lag": "one view has not been refreshed since a change (a price move, a promo date, "
                  "a schedule slip) that the other views already reflect.",
    "assumption_mismatch": "two views were built on different stated assumptions for the same "
                           "line -- a different price point, a different promo condition, a "
                           "different scope of what counts.",
    "data_entry_error": "a transcription or unit mistake in how a number was carried from one "
                        "planning system into another.",
    "scope_mismatch": "one view rolls in a sub-line item (an allowance, an add-on, a phase-out) "
                      "that another view excludes.",
    "unknown": "the notes do not support any of the four causes above for this specific line "
              "item. This is the correct answer when the evidence is not there -- guessing a "
              "specific cause is a worse answer than saying so.",
}

# The three axes `evals/scoring.py` grades a brief on, per the atlas facet sheet's own
# `eval_intent`: replay prior cycles, grade completeness against the human-built gap list,
# cause-tag agreement against the lead's final deck, and narrative faithfulness.
RUBRIC_AXES = (
    {
        "key": "gap_completeness",
        "label": "Gap completeness",
        "weight": 0.40,
        "asks": "Does the brief itemize every material gap it was handed, and nothing it was "
               "not -- no dropped line, no invented one?",
    },
    {
        "key": "cause_tag_agreement",
        "label": "Cause-tag agreement",
        "weight": 0.35,
        "asks": "For each itemized gap, does the assigned cause match the gold cause -- "
               "including saying 'unknown' when gold says unknown, not just when gold has a "
               "traceable cause?",
    },
    {
        "key": "narrative_faithfulness",
        "label": "Narrative faithfulness",
        "weight": 0.25,
        "asks": "Does every quantified claim in the drafted narrative text trace to a number "
               "actually present in the packed gap list -- no figure invented or misremembered "
               "in the prose?",
    },
)

# The guardrail metric this kit's security posture rests on, reported alongside the three axes
# above rather than folded into any of them -- fabricating a citation is a different failure than
# missing a gap or picking the wrong (but real) cause, and the two must never be averaged together.
FABRICATION_GUARDRAIL = (
    "A cause other than 'unknown' with a citation that is not a verbatim line from that cycle's "
    "own notes is a fabrication, counted on its own and never folded into cause-tag agreement."
)
