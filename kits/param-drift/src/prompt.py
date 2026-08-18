"""SEAM 3 -- the verdict vocabulary and the prompt. Declared once, here, and read from here by
the app, the parser, the scorer and the eval harness -- a second copy is a silent disagreement
waiting for the day somebody edits one of them.

⚠︎ TWO VERDICTS, NOT THREE. See ops-triage's own note on the same choice: a review queue is a
binary gate at the point this kit decides anything -- a parameter lands in front of a person or it
does not. An UNSURE verdict would still have to be mapped onto one of the two before anything
happened, and mapping it quietly to HOLD (the tempting direction, since it surfaces nothing) turns
every hesitation into a missed drift hidden inside a calm-looking score. If a genuine third state is
wanted here it needs a real destination -- a lower-priority queue, a re-check next cycle -- which is
a product decision and a different flow, not a word in a prompt.

── WHAT THE MODEL IS SHOWN, AND WHY IT IS NOT ONLY THE RAW READINGS ─────────────────────────────

⚑ THE TREND AND THE OUTLIERS ARE COMPUTED BY CODE AND HANDED OVER AS FACTS. A window that creeps
35-55% off configured across ten periods contains, in its own average, very little that says so --
averaging a fine beginning together with a bad ending is exactly what hides a creep from a number.
`src/aggregate.py::trend` compares the first half of the window against the second half and states
the result in one line, and that line goes in the prompt. Likewise `outliers` names any reading far
from the window's own centre, together with whatever note the corpus logged against it.

⚠︎ THIS IS THE SAME DIVISION OF LABOUR ops-triage's prompt.py NAMES EXPLICITLY: **code establishes
what is true, the model judges what it means.** The code does not decide whether a trend or an
outlier is worth a review -- it states the trend's direction and size, and whether a reading is
unusual and why the corpus says it happened. Whether that adds up to something a person should look
at is the judgement being bought. Handing the model only the raw numbers and asking it to notice a
trend or an outlier on its own, then publishing the result as evidence models cannot reason about
drift, would be the classic failure of putting the fact nowhere in the prompt.

⚠︎ AND THE SAME FACTS ARE AVAILABLE TO THE FLOOR'S OWN DOCSTRING, EVEN THOUGH THE FLOOR CANNOT ACT
ON THEM. `src/formulas.py` says plainly that its threshold reads only mean and std -- so the
comparison between the model and the floor stays honest: the model is not shown anything the corpus
withheld from the floor, it is simply asked to use more of what the corpus already computed.

── THE CORRECTED VALUE IS NEVER ASKED OF THE MODEL ────────────────────────────────────────────

The model returns a verdict and a one-sentence reason, nothing else. `src/formulas.py::corrected_value`
computes the proposed number from the observed window alone, regardless of what the model said --
see its own header for why.
"""
import json

VERDICTS = ("FLAG", "HOLD")

MEANS = {
    "FLAG": "surface this parameter for review, with a proposed corrected value attached",
    "HOLD": "leave it as configured -- nothing here needs a person yet",
}

CATEGORY_LABEL = {
    "lead_time": "a configured lead time (a duration)",
    "safety_margin": "a configured safety margin (a buffer sized to cover variability)",
    "service_target": "a configured service target (a rate or threshold)",
}

# ⚑ HEADROOM, NOT A TARGET -- carried over from every sibling kit on this shared key, all pointed
# at a reasoning model that bills a `reasoning_content` pass inside `completion_tokens` before the
# answer. A cap low enough to bite saves no money (output is billed per token generated, not per
# token allowed) and returns nothing at all. Never tune this down until finish_reason across a real
# run says it is safe to.
MAX_TOKENS = 4096

SYSTEM = (
    "You are the parameter-review step in a monitoring system. You are shown one configured "
    "operating parameter -- a lead time, a safety margin, or a service target -- alongside the "
    "system's own rolling window of what it has actually observed for that parameter, plus two "
    "facts computed from that window: the trend across the window (first half vs second half) "
    "and any outlier readings, each with whatever note was logged against it. "
    "Decide whether this parameter should be FLAGGED for a person to review, or HELD. "
    "Return a JSON object with exactly these keys: "
    "{\"verdict\": \"FLAG\" or \"HOLD\", \"reason\": \"<one sentence, citing the specific fact you "
    "relied on>\"}."
)

RULES = (
    "How to decide:\n"
    "- START WITH THE BASIC COMPARISON: does the configured value match what most of the window "
    "actually shows? If the readings CONSISTENTLY sit well away from the configured value -- even "
    "with no trend and no outlier, even if the gap has been stable the whole window -- that IS a "
    "real, sustained mismatch and should be FLAGGED. 'Stable' is not a reason to hold; a parameter "
    "that has been wrong the same way for the whole window is exactly the case this exists to "
    "catch, and it is usually the easiest call to make.\n"
    "- The trend and outlier facts are for the HARDER cases, not a replacement for the basic "
    "comparison above: a steady one-directional trend across the window can be worth flagging even "
    "when the whole-window average still looks mild, because the average hides a trend that is "
    "still under way -- read the trend fact, not just the average, in that case. And a single "
    "unusual reading with a logged one-time-event note is NOT a sustained mismatch, however large "
    "that one reading is, when the rest of the window otherwise matches the configured value -- "
    "HOLD that case specifically.\n"
    "- If the window's readings are close to the configured value with only ordinary noise, HOLD.\n"
    "- This is decision-free: nothing you say changes anything automatically. FLAG means 'a person "
    "should look at this', not 'change it now'.\n"
    "Answer with the JSON object only."
)


def _fmt_window(window):
    lines = []
    for r in window:
        note = ("   NOTE: %s" % r["note"]) if r["note"] else ""
        lines.append("  %-5s %10.1f%s" % (r["period_label"], r["observed"], note))
    return "\n".join(lines)


def _fmt_trend(trend):
    if trend["direction"] == "flat" or trend["delta_pct"] is None:
        return ("Trend: first-half mean %.2f, second-half mean %.2f -- no material trend "
                "(%.1f%% change)." % (trend["first_half_mean"] or 0, trend["second_half_mean"] or 0,
                                      trend["delta_pct"] or 0.0))
    return ("Trend: first-half mean %.2f, second-half mean %.2f -- %s, %.1f%% change across the "
            "window." % (trend["first_half_mean"], trend["second_half_mean"], trend["direction"],
                         trend["delta_pct"]))


def _fmt_outliers(outliers):
    if not outliers:
        return "Outliers: none -- every reading is within 2.5 standard deviations of the window mean."
    lines = ["Outliers: %d reading(s) far from the window's own mean:" % len(outliers)]
    for o in outliers:
        note = (" -- %s" % o["note"]) if o["note"] else " -- no note logged against it"
        lines.append("  %-5s %10.1f%s" % (o["period_label"], o["observed"], note))
    return "\n".join(lines)


def build(param, window, facts):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    head = ("Parameter %s -- %s\nCategory: %s\nConfigured value: %s %s\n"
           % (param["parameter_id"], param["entity"], CATEGORY_LABEL[param["category"]],
              param["configured_value"], param["unit"]))
    window_block = "Observed window, oldest to most recent:\n" + _fmt_window(window)
    facts_block = _fmt_trend(facts["trend"]) + "\n" + _fmt_outliers(facts["outliers"])
    user = "%s\n%s\n\n%s\n\n%s\n\nJSON:" % (head, window_block, facts_block, RULES)
    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "parameter", "text": head},
        {"name": "window", "text": window_block},
        {"name": "facts", "text": facts_block},
        {"name": "rules", "text": RULES},
    ]
    return ([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], parts)


def parse(raw):
    """A {verdict, reason} dict, or {verdict: None, reason: None} when nothing usable came back.

    ⚠︎ None IS A THIRD OUTCOME AND MUST NOT DEFAULT TO 'HOLD'. Falling back to HOLD would be the
    safe-looking choice -- it surfaces nothing -- and would silently convert every failed call into
    a held parameter, hiding a total reliability failure inside the best-looking score this kit can
    produce. Callers count this apart, same discipline as ops-triage's `no_verdict`.
    """
    out = {"verdict": None, "reason": None}
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    v = obj.get("verdict")
    if isinstance(v, str) and v.strip().upper() in VERDICTS:
        out["verdict"] = v.strip().upper()
    r = obj.get("reason")
    if isinstance(r, str):
        out["reason"] = r
    return out
