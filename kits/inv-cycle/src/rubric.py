"""The rubric this kit's drafted cause is graded against -- the fixed five-member cause vocabulary
and the weights the three eval axes are read at. Declared once and imported by `src/prompt.py`
(what the model is told), `src/app.py` (what the UI labels) and `evals/scoring.py` (what the
grader checks), so the prompt and the grader can never silently drift apart -- same discipline as
gap-brief's own `src/rubric.py`, the primary template this kit mirrors.

⚠︎ 'unresolved' IS A VOCABULARY MEMBER, NOT AN ESCAPE HATCH FROM IT. Every drafted cause must be
one of these five values -- there is no sixth "not sure" the model can invent instead, and
'unresolved' is the one this kit exists to make SAFE to say: the guardrail is drafted cause
limited to what the log actually supports, flagged unresolved rather than guessed when the log
doesn't point to one clear cause.
"""

CAUSE_VOCAB = (
    "mis_receipt",
    "unrecorded_transfer",
    "uom_error",
    "unscanned_movement",
    "unresolved",
)

CAUSE_MEANINGS = {
    "mis_receipt": "a receiving log line's recorded quantity doesn't reconcile with the "
                   "variance -- a receiving correction that was logged but never actually "
                   "applied to on-hand, or a received quantity that itself looks miscounted "
                   "against the PO.",
    "unrecorded_transfer": "the variance size lines up with what a transfer to or from another "
                           "location would explain, but no transfer log line covering that "
                           "quantity or window exists here.",
    "uom_error": "the variance is a clean multiple of a common case-pack size, and a specific "
                "log line shows eaches and cases were mixed up for this item -- not just that "
                "the number happens to divide evenly.",
    "unscanned_movement": "a scan, pick or sale log line's quantity, summed with the rest of "
                          "the history, doesn't fully reconcile against the variance -- some "
                          "movement happened with no corresponding log entry.",
    "unresolved": "the transaction history genuinely doesn't support any of the four causes "
                 "above cleanly. This is the correct answer when the evidence isn't there -- "
                 "guessing a specific cause is a worse answer than saying so.",
}

# Common case-pack sizes this corpus plants consistently -- the constant itself lives in
# src/segment.py (the pure-code module that actually does arithmetic on it) and is imported from
# there by tools/build_corpus.py and evals/scoring.py, so there is exactly one copy.

# The three axes `evals/scoring.py` grades a drafted cause on, per the use case's own eval_intent:
# replay historical variances against the confirmed root cause, grade whether the drafted cause
# matches, and catch the uom/transfer confusion specifically.
RUBRIC_AXES = (
    {
        "key": "cause_accuracy",
        "label": "Cause accuracy",
        "weight": 0.50,
        "asks": "Does the drafted cause match what inventory control actually confirmed for "
               "this variance -- including correctly saying unresolved when gold says "
               "unresolved, not just when gold has a traceable cause?",
    },
    {
        "key": "citation_validity",
        "label": "Citation validity",
        "weight": 0.30,
        "asks": "For a non-unresolved cause, is the cited log line real, and does it actually "
               "support the stated cause -- not merely a real line from this event's own log?",
    },
    {
        "key": "narrative_faithfulness",
        "label": "Narrative faithfulness",
        "weight": 0.20,
        "asks": "Does the drafted narrative's stated cause match the structured cause field, "
               "with nothing claimed that the citation doesn't support?",
    },
)

# The guardrail metric this kit's security posture rests on -- fabricating a citation is a
# different failure than missing the right cause, and the two must never be averaged together.
FABRICATION_GUARDRAIL = (
    "A cause other than 'unresolved' whose cited log line index does not exist, or exists but "
    "does not actually evidence that cause, is a fabrication -- counted on its own and never "
    "folded into cause accuracy."
)

# THE metric this kit exists to measure -- named in the use case's own eval_intent. Of the gold
# unrecorded_transfer cases whose variance_qty is ALSO a clean multiple of a case-pack size (the
# trap), how often does the drafted cause say uom_error instead. A model that pattern-matches
# "divides evenly by 12, must be UOM" without reading the log produces exactly this error, and it
# is the expensive direction: the two causes point to different corrective actions.
CONFUSION_GUARDRAIL = (
    "uom_transfer_confusion: of the gold unrecorded_transfer cases whose variance is also a "
    "clean case-pack multiple, how many were drafted as uom_error. Denominator is the trap "
    "cases specifically, never all unrecorded_transfer cases."
)
