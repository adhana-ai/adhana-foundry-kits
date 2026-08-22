"""Assemble the label-restriction prompt. One prompt per case, all twenty-two fields in it.

⚠︎ THIS KIT HAS TWO GUARDED FIELDS, NOT ONE. `verdict` says whether the proposed application sits
inside the label; `deciding_restriction` says WHICH restriction settled it. They are scored
separately and on purpose: a `wait_required` that names the pre-harvest interval on a case that
actually turns on the re-entry interval is a right answer for the wrong reason, and a grower told
to wait the wrong number of the wrong unit from the wrong date has not been helped by the verdict
being right.

⚑ AND THE CHECK SET ITSELF IS SENT WITH EVERY CALL, RENDERED FROM data/checks.json RATHER THAN
RETYPED HERE. A precedence walk the model has never been shown is not a precedence walk. A second
prose copy of the eight checks inside this module is a copy that drifts from the file the corpus
generator and the scorer both read -- which would make the model's instructions and the gold labels
disagree about the same rule, silently, and the disagreement would score as a model failure.

Five things are spelled out that a model left to its own reading gets wrong:

  1. HARD BEATS TIMING. A case that breaches both a hard restriction and an interval is
     `outside_label`, not `wait_required`. Telling somebody to wait a fortnight before making an
     application the label does not permit at all is the most expensive wrong answer here.
  2. EVERY LIMIT IS INCLUSIVE EXCEPT THE SEASON COUNT. A rate exactly on the maximum is inside the
     label; three applications already made against a maximum of three is not, because this one
     would be the fourth.
  3. THE RE-ENTRY INTERVAL IS IN HOURS AND EVERY OTHER INTERVAL IS IN DAYS. Its numbers sit in the
     same range as the day counts, and a comparison made without the unit clears it by accident.
  4. NOT APPLICABLE IS NOT UNKNOWN. A check that does not apply is skipped and passes; a value the
     page does not state stops the walk with `insufficient_information`, naming the restriction.
  5. NEITHER DECOY DECIDES ANYTHING. The agronomist's note is one person's remark and may point
     the opposite way. The PREVIOUS season's application count is a real number about a different
     season and is part of no check, because the maximum is per season.

⚑ ONE CALL PER CASE, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit here.

⚠︎ AND THE VERDICT IS A PROPOSAL. The prompt says so, the UI says so and the kit's own pages say
so: nothing here authorises an application. A qualified adviser does, against the approved label.
"""
import json

from .checks import C, CHECKS

SYSTEM = (
    "You read a CROP-PROTECTION PRODUCT LABEL EXTRACT together with ONE PROPOSED APPLICATION, and "
    "you extract structured fields from them. You return JSON and nothing else.\n"
    "\n"
    "You are PROPOSING a reading of the label for a qualified adviser to act on. You never "
    "authorise an application, and your answer is not a substitute for the approved label for this "
    "product in this territory.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the page does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world. The label extract and the proposal are the only facts.\n"
    "2. `verdict` and `deciding_restriction` are decided ONLY by the CHECK SET given below. Walk "
    "the eight checks IN THEIR STATED ORDER and STOP at the first one that fires. "
    "`deciding_restriction` is the id of that check. If none fires, the verdict is 'within_label' "
    "and the deciding restriction is 'none'.\n"
    "3. A CHECK THAT IS NOT APPLICABLE IS SKIPPED AND PASSES. The re-treatment interval does not "
    "apply when no application has been made to this crop this season. The tank-mix prohibition "
    "does not apply when no tank mix is planned, or when the label prohibits none. Skipping is "
    "not the same as failing and it is not the same as not knowing.\n"
    "4. A CHECK WHOSE LABEL VALUE OR PROPOSAL VALUE IS NOT STATED CANNOT BE PERFORMED. Stop there, "
    "answer 'insufficient_information', and name that check as the deciding restriction. Do not "
    "skip past it to the checks below, and never guess what an unstated interval probably is.\n"
    "5. HARD RESTRICTIONS OUTRANK TIMING ONES, WHICH IS WHY THEY COME FIRST. Checks 1-5 (the crop, "
    "the tank mix, the rate, the season count, the buffer) breach to 'outside_label' and no amount "
    "of waiting cures any of them. Checks 6-8 (the three intervals) breach to 'wait_required'. If "
    "a case breaches both kinds, the walk stops at the hard one and the answer is 'outside_label'; "
    "answering 'wait_required' there tells somebody to wait before doing something they must not "
    "do at all.\n"
    "6. EVERY NUMERIC LIMIT IS INCLUSIVE EXCEPT THE SEASON COUNT. A rate exactly equal to the "
    "maximum is inside the label. A pre-harvest interval of 35 days is satisfied by exactly 35 "
    "days to harvest. A buffer of 5 m is satisfied by exactly 5 m. But 'maximum applications per "
    "season' is a TOTAL, so a proposal made when that many have already been applied would be the "
    "next one and is over the maximum.\n"
    "7. THE RE-ENTRY INTERVAL IS MEASURED IN HOURS. Every other interval on the label is in days. "
    "Compare hours with hours.\n"
    "8. THE AGRONOMIST'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds worried does "
    "NOT put a compliant application outside the label, and a note that sounds relaxed does NOT "
    "bring a non-compliant one inside it. The check set decides; the note is one person's remark "
    "and may disagree with it.\n"
    "9. THE PREVIOUS SEASON'S APPLICATION COUNT IS A FIELD TO COPY, NOT AN INPUT. The label "
    "maximum is per season, so applications made in a previous season are never added to this "
    "season's count.\n"
    "10. Copy crop names, product names and notes verbatim from the page. Return numbers as "
    "numbers, with no unit attached.\n"
    "11. Use the exact allowed value for a field that lists them, and return every field named in "
    "the schema, even when the answer is null."
)

_OP_TEXT = {
    "member_of": "%(proposal)s must be one of the values listed in %(label)s",
    "not_member_of": "%(proposal)s must NOT be any of the values listed in %(label)s",
    "le": "%(proposal)s <= %(label)s",
    "lt": "%(proposal)s < %(label)s   (strictly less than -- this is the one exclusive limit)",
    "ge": "%(proposal)s >= %(label)s",
}


def check_block(c=None):
    """The check set, rendered for the prompt out of data/checks.json.

    ⚑ RENDERED, NEVER RETYPED. src/checks.py walks this same file to write gold and to score, and
    the UI serves it verbatim beside the answer. One file, four readers.
    """
    c = c or C
    lines = [
        "CHECK SET (the authority for `verdict` and `deciding_restriction`; this is an "
        "ILLUSTRATIVE set written for this kit, not a real product label and not any regulator's "
        "guidance)",
        "",
        "WALK THESE IN ORDER AND STOP AT THE FIRST ONE THAT FIRES.",
        "",
    ]
    for k in sorted(c["checks"], key=lambda x: x["order"]):
        lines.append("  %d. %-28s %s -> %s" % (k["order"], k["id"], k["kind"].upper(),
                                               k["breach_verdict"]))
        lines.append("     compare: " + _OP_TEXT[k["op"]] % {"label": k["label_field"],
                                                             "proposal": k["proposal_field"]})
        lines.append("     %s" % k["test"])
        skips = k.get("skip_when") or []
        if skips:
            bits = ["%s is %s" % (s["field"], s["equals"]) for s in skips]
            lines.append("     NOT APPLICABLE (skip it, and it passes) when " + " or ".join(bits))
    lines += [
        "",
        "PRECEDENCE: " + c["precedence"],
        "",
        "SKIPPED IS NOT UNKNOWN: " + c["skipped_is_not_unknown"],
        "",
        "AT THE LIMIT: " + c["at_the_limit"],
        "",
        "WHAT EACH VERDICT MEANS",
    ]
    for name in ("within_label", "wait_required", "outside_label", "insufficient_information"):
        lines.append("  %-26s %s" % (name + ":", c["verdicts"][name]))
    return "\n".join(lines)


CHECK_TEXT = check_block()


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("%s\n\n"
            "Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the page does not state.\n\n"
            "LABEL EXTRACT AND PROPOSED APPLICATION\n"
            "--------------------------------------\n%s\n"
            % (CHECK_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "check set", "text": CHECK_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "case sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
