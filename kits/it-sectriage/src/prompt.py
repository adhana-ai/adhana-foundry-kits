"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER CASE WINDOW, NOT PER ALERT. The model reads every alert in a small candidate group
(2-4 alerts, already bundled because they occurred close in time and/or share an entity) together,
and in one call: classifies each alert true_positive/false_positive, decides which of the
true-positive alerts actually correlate into one incident, and drafts a containment recommendation
per incident, citing the indicator(s) that justify it.

⚠︎ THE JOB IS BOTH CLASSIFICATION AND CORRELATION, AND NEITHER ONE ALONE IS THE POINT. A model that
gets every disposition right but merges two unrelated true positives into one case has produced a
wrong incident count; a model that groups correctly but calls a real phishing report a false
positive has missed an incident entirely. Both are scored, apart, in evals/scoring.py.

⚠︎ TWO PIECES OF GENERAL GUIDANCE ARE STATED BECAUSE THEY ARE TRUE OF REAL TRIAGE, NOT BECAUSE THIS
CORPUS PLANTS THEM. A calm-sounding report is not evidence of nothing; a shared network address is
not evidence of one incident. Both are ordinary SOC judgement calls, stated here the same way
ops-triage's RULES states "volume alone is not a reason to page" -- domain guidance, not a hint
about this specific dataset.

⚠︎ THIS KIT NEVER EXECUTES A CONTAINMENT ACTION, AND THE PROMPT SAYS SO IN AS MANY WORDS. The reply
drafts a recommendation for the named on-call analyst to approve -- account lockout, mail-flow
block, endpoint isolation are all things a person does after reading the draft, never something
this call performs. See src/triage.py's module docstring for where that boundary is enforced in
code, not just here.

⚠︎ A CITATION MUST NAME A REAL INDICATOR ON A REAL ALERT IN THAT CASE, NEVER AN INVENTED ONE. Every
alert's indicators are shown in `name=value` form precisely so a citation can be checked by exact
string lookup (see evals/scoring.py::citation_is_real) rather than by asking a second model whether
a citation sounds plausible.
"""
import json

DISPOSITIONS = ("true_positive", "false_positive")

# r001 measured finish_reason="length" on 7 of 33 calls at 3000; raised to 4096 (matching
# fin-invval's fix) still left 5 of 33 truncated, with reasoning_chars up to 13,497 on windows
# that DID complete -- this task's multi-alert correlation reasoning is heavier than fin-invval's.
# Raised again, well past the observed ceiling rather than nudging incrementally a third time.
MAX_TOKENS = 8192

SYSTEM = (
    "You are a SOC triage analyst. You are shown one case window: a small group of 2-4 security "
    "alerts that were bundled together because they occurred close in time and/or share an "
    "entity. Your job has three parts, in one reply:\n\n"
    "1. DISPOSITION -- for every alert in the window, decide true_positive (a real security "
    "event) or false_positive (benign, correctly explained away). Judge each alert on its own "
    "evidence.\n"
    "   - A calm or routine-sounding report is not evidence of a false positive. Genuine phishing "
    "reports are often written as an ordinary 'is this legit?' question, not an alarm -- judge "
    "the sender domain, the link and the ask, not the tone.\n"
    "   - A loud description is not automatically a true positive either -- read whether it is "
    "actually explained (a confirmed backup window, a confirmed travelling user, an approved "
    "software request).\n\n"
    "2. CORRELATION -- among the alerts you called true_positive, decide which ones are genuinely "
    "the SAME incident and which are separate. Two alerts belong in the same case only when the "
    "evidence connects them causally, not just superficially.\n"
    "   - Do not merge two alerts into one incident merely because they share an entity, a close "
    "timestamp, or one matching indicator value. A shared source IP can mean one attacker, or it "
    "can mean two unrelated users behind the same building's network or the same VPN "
    "concentrator -- read what the shared value actually is before treating it as a link.\n"
    "   - A true positive with no genuine partner is its own case, alone.\n"
    "   - Never place a false_positive alert into any case -- a case exists only where there is a "
    "real incident.\n\n"
    "3. RECOMMENDATION -- for every case with at least one true-positive alert, draft one short "
    "containment recommendation (account lockout, mail-flow block, or endpoint isolation, "
    "whichever fits). Cite the specific indicator(s) that justify it, in the exact form they "
    "appear in the alert data (name=value). Never cite an indicator that is not actually present "
    "on an alert in that case, and never invent one.\n\n"
    "YOU NEVER EXECUTE CONTAINMENT. You only draft the recommendation. The named on-call analyst "
    "shown to you reviews and approves it before anything is done -- your recommendation text "
    "should read as a draft awaiting that approval, not as an action taken.\n\n"
    "Reply with ONLY a JSON object, no other text, with exactly these three keys:\n"
    '  "alert_dispositions": {"<alert_id>": "true_positive"|"false_positive", ... one entry per '
    "alert in the window}\n"
    '  "case_groups": [[<alert_id>, ...], ...]  -- one list per incident, true-positive alert '
    "ids only, every true positive in exactly one group\n"
    '  "recommendations": [{"case": [<alert_id>, ...], "action": "<one or two sentences>", '
    '"citations": ["<indicator_name>=<value>", ...]}, ...]  -- one entry per case_groups group'
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _alert_block(a):
    ind = ", ".join("%s=%s" % (k, v) for k, v in a["indicators"].items())
    return ("  %s  [%s]  entity=%s  %s\n    %s\n    indicators: %s"
            % (a["alert_id"], a["alert_type"], a["entity"], a["ts"][11:19], a["description"], ind))


def build(window, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes -- every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    alert_ids = [a["alert_id"] for a in window["alerts"]]
    block = "\n".join(_alert_block(a) for a in window["alerts"])
    user = (
        "Case window %s, starting %s. On-call analyst: %s.\n\n"
        "Alerts in this window (%s):\n%s\n\n"
        "Return the JSON object described in the system message. Every one of these alert ids "
        "must appear in alert_dispositions, exactly once: %s"
        % (window["id"], window["window_start"], window["on_call_analyst"],
           ", ".join(alert_ids), block, ", ".join(alert_ids))
    )
    parts = [{"name": "system", "text": system}, {"name": "alerts", "text": block}]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def _strip_fence(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text


def parse(raw):
    """Pull the field set out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-empty result -- read as "this call produced no
    usable answer", never as evidence about any alert. No regex fallback that scrapes a plausible
    disposition out of raw text -- that would silently turn a broken call into a mediocre triager.
    """
    out = {"alert_dispositions": {}, "case_groups": [], "recommendations": [], "parsed": False}
    if not raw:
        return out
    text = _strip_fence(raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out

    disp = obj.get("alert_dispositions")
    if isinstance(disp, dict):
        out["alert_dispositions"] = {str(k): v for k, v in disp.items() if v in DISPOSITIONS}

    groups = obj.get("case_groups")
    if isinstance(groups, list):
        out["case_groups"] = [[str(a) for a in g] for g in groups
                              if isinstance(g, list) and g]

    recs = obj.get("recommendations")
    if isinstance(recs, list):
        clean = []
        for r in recs:
            if not isinstance(r, dict):
                continue
            case = r.get("case")
            action = r.get("action")
            citations = r.get("citations")
            clean.append({
                "case": [str(a) for a in case] if isinstance(case, list) else [],
                "action": action if isinstance(action, str) else None,
                "citations": [str(c) for c in citations] if isinstance(citations, list) else [],
            })
        out["recommendations"] = clean

    out["parsed"] = True
    return out
