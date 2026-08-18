"""The rule-and-threshold floor, and the deterministic corrected-value calculator. Pure code, no
model -- same discipline data-match's decide.py and change-impact's impact.py both state for their
own thresholds: the number a reader trusts must be arithmetic on the observed window, never
something the model asserted about its own answer.

⚑ WHY THE MODEL NEVER COMPUTES THE CORRECTED VALUE ITSELF. Asking a model "what should the buffer
be" invites it to do arithmetic in its head and round confidently to a wrong number -- the same
failure mode change-impact's own header warns against for its dollar figure. The model's whole job
in this kit is the FLAG/HOLD judgement call (see src/prompt.py); this module computes the proposed
value from the observed window alone, so a value can be wrong only because the window's own
readings were noisy, never because a model miscalculated.

THREE CATEGORIES, THREE FORMULAS:

    lead_time        proposed = the observed window's own mean. Reset the configured duration to
                     what has actually been happening.
    safety_margin    proposed = Z_SAFETY x the observed window's sample std. The standard
                     buffer-covers-variability shape: a margin sized to the variability actually
                     seen, not the variability assumed when the parameter was last set.
    service_target   proposed = the observed window's own mean. Reset the configured target to
                     what the system has actually been achieving.

⚑ Z_SAFETY = 1.65 IS AN ASSUMED CONSTANT, NOT A MEASURED ONE -- same honesty as change-impact's
EXPEDITE_RATE_PER_UNIT_DAY. It is the z-score for a 95% one-sided service level, a common working
default; a real deployment supplies its own target and its own z.

⚑ THE THRESHOLDS ARE STATED ONCE, HERE, NOT FITTED TO THIS CORPUS AFTER THE FACT -- same claim
change-impact's MATERIALITY_THRESHOLD_USD makes. Each is a judgement, not a tuning knob: raise it
and a real drift goes unflagged for longer; lower it and noise starts arriving as if it mattered.

⚠︎ THE FLOOR READS ONLY MEAN AND STD, STRUCTURALLY. It has no access to the trend or outlier facts
`src/aggregate.py` computes -- and that is not an oversight, it is the shape of a threshold. A
`slow_creep` parameter's whole-window mean can still read mild while the trend is unmistakable; a
`one_off_spike` parameter's mean or std can read as drift when the underlying behaviour never
moved. **A floor that cannot see the shape of the window is not a defect in this kit -- it is the
reason there is a second station after it.**
"""
DEVIATION_THRESHOLD_PCT = 20.0        # lead_time: |mean - configured| / configured
SAFETY_GAP_THRESHOLD_PCT = 32.0       # safety_margin: |configured - required| / required
SERVICE_GAP_THRESHOLD_PTS = 3.0       # service_target: |mean - configured|, in points

Z_SAFETY = 1.65


def required_buffer(std):
    return Z_SAFETY * std


def deviation(category, configured, window_stats):
    """The one number the floor thresholds on, in this category's own units. Returns None if the
    window has no usable stats (n < 2)."""
    mean, std = window_stats["mean"], window_stats["std"]
    if mean is None:
        return None
    if category == "lead_time":
        return round(100.0 * (mean - configured) / configured, 1) if configured else None
    if category == "safety_margin":
        req = required_buffer(std)
        return round(100.0 * (configured - req) / req, 1) if req else None
    if category == "service_target":
        return round(mean - configured, 1)
    raise ValueError(category)


def decide_floor(category, configured, window_stats):
    """The floor's verdict on one parameter, and why. Returns (verdict, reasons)."""
    dev = deviation(category, configured, window_stats)
    if dev is None:
        return "HOLD", ["not enough readings to judge"]
    if category == "lead_time":
        fires = abs(dev) >= DEVIATION_THRESHOLD_PCT
        reason = ("observed mean %.1f%s vs configured %s%s -- %.1f%% deviation, threshold %.0f%%"
                  % (window_stats["mean"], "d", configured, "d", dev, DEVIATION_THRESHOLD_PCT))
    elif category == "safety_margin":
        req = required_buffer(window_stats["std"])
        fires = abs(dev) >= SAFETY_GAP_THRESHOLD_PCT
        reason = ("configured buffer %s vs required (z*std) %.1f -- %.1f%% gap, threshold %.0f%%"
                  % (configured, req, dev, SAFETY_GAP_THRESHOLD_PCT))
    else:
        fires = abs(dev) >= SERVICE_GAP_THRESHOLD_PTS
        reason = ("observed mean %.1f%% vs configured target %s%% -- %.1f pt gap, threshold %.1f pt"
                  % (window_stats["mean"], configured, dev, SERVICE_GAP_THRESHOLD_PTS))
    return ("FLAG" if fires else "HOLD"), [reason]


def corrected_value(category, window_stats):
    """The proposed corrected value, computed from the observed window alone -- never asked of the
    model, and computed the SAME way regardless of what flagged the parameter (floor or model)."""
    mean, std = window_stats["mean"], window_stats["std"]
    if mean is None:
        return None
    if category == "safety_margin":
        return round(required_buffer(std), 1)
    return round(mean, 1)
