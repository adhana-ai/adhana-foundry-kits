"""Assemble the completeness-check prompt. One prompt per plan, all fourteen fields in it.

⚠︎ THE GUARDED ANSWER OF THIS KIT IS A COMPONENT STATE, AND THE HARD STATE IS
`present_not_measurable`. It is stated in full, and THE RULEBOOK ITSELF IS SENT WITH IT, because a
completeness check is a lookup against somebody's list of required elements and a model cannot look
up a list it has never been shown. The alternative -- letting the model answer from whatever it
knows about how plans are usually written -- is exactly the failure this kit exists to measure: the
shipped rulebook is the authority for this decision, and a reading that disagrees with it is wrong
here even where the disagreement is reasonable.

Four things are spelled out that a reader left to their own judgement gets wrong:

  1. A SECTION THAT IS THERE IS NOT NECESSARILY A SECTION THAT COUNTS. A goal with no baseline, no
     criterion or no measurement method passes every checkbox review and helps nobody. It is the
     state this kit exists for and it is much harder to see than an absent heading.
  2. ONE BAD ENTRY MAKES THE WHOLE COMPONENT UNMEASURABLE. Six good goals and a seventh with no
     criterion is a component nobody can measure against, not a component that is 86 per cent
     right. Components are never scored on average.
  3. THE TRANSITION COMPONENT IS CONDITIONAL ON A FACT ABOUT THE PUPIL, NOT ON THE PLAN. Below the
     rulebook's transition age it is `not_required` whatever the plan contains; with no age stated
     it is never `not_required`, because an unknown requirement is not an absent one.
  4. THE CHECKLIST AND THE NOTE ARE FIELDS TO COPY, NOT EVIDENCE. A tick-box sheet claiming every
     component is present does not make an absent section present, and a reassuring remark from a
     case manager does not make an unmeasurable goal measurable.

⚑ ONE CALL PER PLAN, NOT ONE PER COMPONENT -- same reasoning as every sibling extraction kit here.

⚠︎ AND THE ANSWER IS A WORKLIST. The prompt says so, the UI says so and the kit's own pages say so:
nothing here approves, signs, files or amends a plan. The team that writes the plan decides what
goes in it.
"""
import json

from . import rulebook as RB

# ⚑ THE COMPONENT-STATE VOCABULARY IS DECLARED ONCE, HERE, AND EVERYTHING READS IT FROM HERE. The
# prompt below builds its definition block from this dict rather than restating it, `parse()`
# accepts nothing outside `VERDICTS` for a component field, `evals/judge.py` scores these four and
# no others, and the site's app panel reads this module rather than shipping a `data/verdicts.json`
# beside it. A second copy of a class list is the thing that drifts from the scorer, and a class
# list that has drifted from the scorer is worse than no panel at all.
#
# ⚠︎ THE ORDER IS DELIBERATE AND IS NOT THE RULEBOOK'S. `present_not_measurable` is drawn FIRST,
# ahead of the state a reader expects to see first, because it is the one this kit exists to keep
# separate and the one a checkbox review cannot express at all. Written as a literal rather than
# built from data/rulebook.json because it is read by AST at build time; the assertion below is
# what stops the two drifting.
#
# `costs` is what getting THIS state wrong does to whoever trusts it. Written down because the
# mistakes are not interchangeable, and a single accuracy figure hides which one you are making.
VERDICTS = ("present_not_measurable", "absent", "present_complete", "not_required")

VERDICT_MEANINGS = {
    "present_not_measurable": {
        "means": "The component is in the plan and cannot be measured against. An element the "
                 "rulebook asks for is missing, or is written in words that carry no quantity -- "
                 "a goal with no baseline, a service with no frequency, a reporting schedule that "
                 "says 'regularly'. ONE bad entry makes the whole component unmeasurable; the "
                 "section is never scored on average.",
        "costs": "This is the expensive error and it is counted separately from accuracy in "
                 "evals/judge.py. Called present_complete, a section nobody can evaluate goes to "
                 "the meeting with a tick on it, and a year later nobody can say whether the goal "
                 "was met. Called absent, somebody is sent to write a section that already exists.",
    },
    "absent": {
        "means": "The plan has no section for this component, or the section is a placeholder -- "
                 "'to be completed', 'see pupil file'. There is nothing to read and nothing to "
                 "quote.",
        "costs": "Called present_complete, a required component that was never written disappears "
                 "entirely -- nobody goes looking for a section the check said was fine. It is "
                 "also the EASY half of this kit's job: a checkbox review catches it, which is "
                 "exactly why the free floor in evals/baseline.py is a checkbox review.",
    },
    "present_complete": {
        "means": "Every element the rulebook names for this component is in the plan, and each "
                 "one is stated in terms somebody can measure against at the next review.",
        "costs": "Called present_not_measurable, a sound plan is sent back for rework and the "
                 "reviewer stops trusting the worklist after the second false alarm. A worklist "
                 "that cries wolf is worse than no worklist, because a human has to clear "
                 "every row.",
    },
    "not_required": {
        "means": "The rulebook does not ask this plan for this component. Only the transition "
                 "component can be in this state, and only when the plan STATES the pupil's age "
                 "and it is below the rulebook's transition age. When no age is stated, this "
                 "state is never correct -- an unknown requirement is not an absent one.",
        "costs": "Awarded wrongly, it is a free exit from a real requirement: a plan that owes "
                 "transition content reads as complete without it. Withheld wrongly, every "
                 "younger pupil's plan gets a defect raised against it for a section the rulebook "
                 "never asked for -- and that false defect is the single commonest way a "
                 "completeness check loses its reader.",
    },
}

assert set(VERDICTS) == set(RB.STATES), \
    "the component states declared here have drifted from data/rulebook.json"

# The plan-level outcome. A DIFFERENT vocabulary from the component states, on purpose: one
# describes a section, the other describes the plan those sections add up to. Naming them the same
# thing is how a scorer ends up grading one against the other.
OUTCOMES = ("complete", "components_missing", "not_measurable", "undetermined")

OUTCOME_MEANINGS = {
    "components_missing": "At least one component the rulebook requires is not in the plan at all.",
    "not_measurable": "Every required component is present, and at least one of them cannot be "
                      "measured against.",
    "undetermined": "The plan does not state the pupil's age and carries no complete transition "
                    "content, so whether that component was required cannot be determined from "
                    "this record.",
    "complete": "Every component the rulebook requires is present and measurable.",
}

assert set(OUTCOMES) == set(RB.OUTCOMES), "plan outcomes have drifted from src/rulebook.py"


def _state_block():
    """The four component states and what each one means, rendered from VERDICT_MEANINGS."""
    lines = ["COMPONENT STATES -- answer every component with exactly one of these four"]
    for key in VERDICTS:
        lines.append("  %s" % key)
        lines.append("      %s" % VERDICT_MEANINGS[key]["means"])
    return "\n".join(lines)


def rulebook_block(m=None):
    """The rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the rules inside this module is a copy that
    drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold labels disagree about the same requirement, silently, and the
    disagreement would score as a model failure.
    """
    m = m or RB.M
    lines = ["COMPONENT RULEBOOK (the authority for every component state; this is an INVENTED "
             "rulebook shipped with this kit -- it reproduces no statute, regulation, agency "
             "guidance or plan template)", "",
             "TRANSITION AGE: %d -- the age at or above which rule %s applies."
             % (m["transition_age"],
                ", ".join(r["id"] for r in m["rules"] if r.get("applies") == "conditional")), ""]
    for r in m["rules"]:
        lines.append("%s  %s" % (r["id"], r["label"]))
        lines.append("    section heading: %s" % r["section"])
        lines.append("    applies: %s" % (r["applies_note"] if r.get("applies_note")
                                          else "to every plan"))
        lines.append("    requires: %s" % r["requirement"])
        for el in r["elements"]:
            lines.append("      - %s" % el)
        lines.append("    not measurable when: %s" % r["unmeasurable_when"])
        lines.append("")
    lines.append("A SECTION BODY THAT IS ONLY A PLACEHOLDER IS ABSENT, NOT PRESENT. Treat these as "
                 "placeholders: %s." % "; ".join("'%s'" % p for p in m["placeholder_bodies"]))
    return "\n".join(lines).rstrip()


RULEBOOK_TEXT = rulebook_block()
STATE_TEXT = _state_block()

SYSTEM = (
    "You read an INDIVIDUALISED EDUCATION PLAN and check it against a component rulebook. You "
    "return JSON and nothing else.\n"
    "\n"
    "You are producing a REVIEWER'S WORKLIST for a person to work through. You never approve, "
    "sign, file or amend a plan, and nothing you return is a decision about a pupil. The team "
    "that writes the plan decides what goes in it.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the plan does not state a field, return null for it. Do not infer it and do not use "
    "what you know about how plans are usually written.\n"
    "2. Each of the seven COMPONENT fields is decided ONLY by the COMPONENT RULEBOOK given below, "
    "applied to the section the rule names. Work through these four questions IN ORDER and STOP "
    "at the first one that answers:\n"
    "   a. NOT REQUIRED. Only the conditional rule can reach this state, and only when the plan "
    "STATES the pupil's age and it is BELOW the rulebook's transition age. Then the state is "
    "'not_required' whatever the plan does or does not contain. If the plan does NOT state an "
    "age, 'not_required' is never correct -- an unknown requirement is not an absent one.\n"
    "   b. ABSENT. The section the rule names is not in the plan, or its body is one of the "
    "placeholders listed in the rulebook. Answer 'absent'.\n"
    "   c. NOT MEASURABLE. The section is there and one of the elements the rule names is "
    "missing, or is stated in words that carry no quantity. Answer 'present_not_measurable'. "
    "⚠︎ ONE BAD ENTRY MAKES THE WHOLE COMPONENT UNMEASURABLE. A goals section with six sound "
    "goals and a seventh that states no criterion is 'present_not_measurable'. Never average a "
    "section, and never let a well-written first entry settle a component.\n"
    "   d. Otherwise answer 'present_complete'.\n"
    "3. A COMPONENT WHOSE SECTION IS NOT IN THE PLAN BELOW IS ABSENT. The plan text you are given "
    "is every section of the plan that could carry a component; exactly two administrative "
    "sections are removed before the plan reaches you -- one marking the file as a generated "
    "sample, and one naming the school and the district -- and neither carries a component. Do "
    "not treat their absence as a missing component, and do not assume any other section was "
    "withheld.\n"
    "4. THE CHECKLIST IS A FIELD TO COPY, NOT EVIDENCE. The 'Checklist Completed By' section is "
    "what a previous reviewer TICKED. A checklist claiming every required component is present "
    "does not make an absent section present and does not make an unmeasurable goal measurable. "
    "It is NEVER an input to a component state or to the outcome.\n"
    "5. THE CASE MANAGER'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT COMPLETENESS. A note that "
    "sounds worried does NOT make a sound plan defective, and a note that sounds reassuring does "
    "NOT clear a plan. The rulebook decides; the note is one person's remark and may disagree "
    "with it.\n"
    "6. `plan_outcome` follows from the seven states and the pupil's age, in this order, stopping "
    "at the first that fires: (1) any REQUIRED component 'absent' -> 'components_missing'; "
    "(2) any REQUIRED component 'present_not_measurable' -> 'not_measurable'; (3) the plan does "
    "not state the pupil's age AND transition is anything other than 'present_complete' -> "
    "'undetermined'; (4) otherwise 'complete'. A component in state 'not_required' is judged on "
    "nothing.\n"
    "7. Copy identifiers, the age and the case manager's note verbatim from the plan. Where the "
    "plan says the pupil's age is not stated, return null for pupil_age rather than the words.\n"
    "8. Use the exact allowed value for a field that lists them.\n"
    "9. Return every field named in the schema, even when the answer is null."
)


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
    # THE ONLY FALLBACK, AND IT IS PLAN-LEVEL RATHER THAN FIELD-LEVEL. See src/select.py: a
    # per-field fallback would fire on every plan that is MISSING a component section -- half this
    # corpus -- and drag the one unmapped section back into the prompt on exactly the documents
    # this kit is about. This one fires only when nothing matched at all, which means a document
    # with none of these headings: a forker's plan, not one of these.
    if not wanted:
        wanted = list(secs)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("%s\n\n%s\n\n"
            "Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the plan does not state.\n\n"
            "EDUCATION PLAN\n--------------\n%s\n"
            % (RULEBOOK_TEXT, STATE_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "component rulebook", "text": RULEBOOK_TEXT},
        {"name": "component states", "text": STATE_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "plan sections", "text": context},
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
