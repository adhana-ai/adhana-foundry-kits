"""The rubric this kit's brief is graded against -- the sections a review brief must carry, the
fixed conflict-cause vocabulary, and the weights the eval axes are read at. Declared once and
imported by `src/prompt.py` (what the model is told), `src/app.py` (what the UI labels) and
`evals/scoring.py` (what the grader checks), so the prompt and the grader can never silently
drift apart -- same discipline gap-brief's src/rubric.py states for its own vocabulary.

⚠︎ 'unknown' IS A VOCABULARY MEMBER, NOT AN ESCAPE HATCH FROM IT. Every entry the model returns
must carry one of these five values, and 'unknown' is the one this kit exists to make SAFE to
say, per the guardrail: cause 'unknown' is allowed but never fabricated.
"""

CAUSE_VOCAB = (
    "promo_overcommit",
    "customer_overcommit",
    "demand_surge",
    "supply_shortfall",
    "unknown",
)

CAUSE_MEANINGS = {
    "promo_overcommit": "merchandising committed promo units across stores that together exceed "
                        "what the DC actually has for this SKU this week.",
    "customer_overcommit": "store reps took customer pre-orders beyond what the reservation "
                           "system had actually held for this SKU.",
    "demand_surge": "nobody over-promised anything -- a genuine, unplanned spike in sell-through "
                    "this week made the ordinary fair-share math infeasible.",
    "supply_shortfall": "the distribution center itself received fewer units than the supply "
                        "plan assumed for this week.",
    "unknown": "the notes do not support any of the four causes above for this specific event. "
              "This is the correct answer when the evidence is not there -- guessing a specific "
              "cause is a worse answer than saying so.",
}

# The three axes `evals/scoring.py` grades a brief on, per the atlas facet sheet's own
# `eval_intent`: replay historical shortage events, prove the drafted split matches what approved
# allocators did (the CODE split IS that proof, by construction -- see conservation below),
# correct conflict detection, and zero protected-class violations.
RUBRIC_AXES = (
    {
        "key": "flag_completeness",
        "label": "Flag completeness",
        "weight": 0.40,
        "asks": "Does the brief itemize every event the written policy could not cleanly "
               "resolve, and nothing it could -- no dropped conflict, no invented one?",
    },
    {
        "key": "cause_tag_agreement",
        "label": "Cause-tag agreement",
        "weight": 0.35,
        "asks": "For each itemized event, does the assigned cause match the gold cause -- "
               "including saying 'unknown' when gold says unknown, not just when gold has a "
               "traceable cause?",
    },
    {
        "key": "narrative_faithfulness",
        "label": "Narrative faithfulness",
        "weight": 0.25,
        "asks": "Does every quantified claim in the drafted narrative trace to a number actually "
               "present in the packed event list -- no figure invented or misremembered?",
    },
)

# The two guardrail metrics this kit's security posture rests on, reported alongside the three
# axes above rather than folded into any of them.
FABRICATION_GUARDRAIL = (
    "A cause other than 'unknown' with a citation that is not a verbatim line from that "
    "session's own notes is a fabrication, counted on its own and never folded into "
    "cause-tag agreement."
)
PARITY_GUARDRAIL = (
    "trade_area_tier is never a parameter of src/allocate.py -- the code-computed split cannot "
    "correlate with it by construction. evals/scoring.py::parity_check measures the actual "
    "correlation on every generated event as the proof, not the promise."
)
