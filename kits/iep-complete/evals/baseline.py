"""A free, rules-and-regex extractor. No model, no key, no spend -- scored by the same judge as a
paid run, so the two are directly comparable.

⚑ THIS FLOOR IS A CHECKBOX REVIEW, AND THAT IS THE WHOLE POINT OF IT. It finds each component's
section heading, checks the body is not a placeholder, and ticks the box. A section that is there
is `present_complete`; a section that is not is `absent`. It NEVER returns
`present_not_measurable`, because counting headings cannot see inside one, and it NEVER returns
`not_required`, because ticking boxes does not read the pupil's age.

That is not a weak implementation of the model's job -- it is a faithful implementation of the job
a completeness checklist actually does today, and the gap between the two numbers is the only thing
on this kit's pages worth buying a model for. Two consequences follow by construction and both are
published:

  - EVERY PRESENT-BUT-UNMEASURABLE COMPONENT IS WAVED THROUGH. The floor's
    `passed_unmeasurable_rate_pct` is 100 by design: a goal with no criterion is a section with a
    heading and some prose in it, and a checkbox review has nothing to say about it. This is the
    headline number this kit exists to move.
  - EVERY YOUNGER PUPIL'S PLAN COLLECTS A FALSE DEFECT. The floor reports the missing transition
    section as `absent` on every plan whose stated age is below the rulebook's threshold, where the
    component was never required. That is the `false_defect_count`, and on a worklist a false alarm
    costs a person's time on every single row.

⚠︎ IT WOULD BE TRIVIAL TO MAKE THIS FLOOR BETTER, AND THAT IS THE POINT OF NOT DOING IT. It already
parses the pupil's age perfectly by regex, so awarding `not_required` correctly is one comparison;
and the goal blocks are labelled, so a stricter reader could count the three elements. Doing either
would measure this repository's regex-writing rather than a model's reading. The floor stays the
shortcut the industry actually uses, and the gap it opens is the gap between counting sections and
reading them.

⚠︎ AND NOTE WHAT THE FLOOR DOES TO THE GUARDRAIL DOWNSTREAM. src/extract.py::compute() is run over
the floor's own output exactly as it is run over a model's, so a checkbox-derived outcome produces a
checkbox-derived worklist flag: the floor reads plan_status correctly by regex every time and the
outcome wrong on every unmeasurable plan, and the flag inherits the error. A business-condition
guardrail is only ever as good as the field it reads.
"""
import re

from src import rulebook as RB
from src.extract import compute as _compute

PLACEHOLDERS = {p.lower() for p in RB.M["placeholder_bodies"]}


def _section(text, name):
    m = re.search(r"%s\n-+\n(.*?)(?:\n\n|\Z)" % re.escape(name), text, re.S)
    return m.group(1).strip() if m else None


def _state(text, key):
    """The checkbox reading of one component. Two answers only, and never the other two."""
    body = _section(text, RB.SECTION_BY_KEY[key])
    if body is None or body.strip().lower().rstrip(".") in PLACEHOLDERS:
        return "absent"
    return "present_complete"


def _age(text):
    raw = _section(text, "Pupil Age")
    if raw is None:
        return None
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


def _claim(text):
    raw = _section(text, "Checklist Completed By") or ""
    if "all required components present: yes" in raw:
        return "all_present"
    if "items outstanding" in raw:
        return "items_outstanding"
    return "not_completed"


def extract_one(text, fields):
    values = {
        "plan_id": _section(text, "Plan"),
        "pupil_ref": _section(text, "Pupil Reference"),
        "pupil_age": _age(text),
        "plan_status": _section(text, "Plan Status"),
        "checklist_claim": _claim(text),
        "case_manager_note": _section(text, "Case Manager Note"),
    }
    for key in RB.COMPONENTS:
        values[key] = _state(text, key)

    # The floor DOES run the rulebook's arithmetic -- a real checklist reviewer applies "a required
    # component is missing, so this plan is not complete". What it cannot do is feed that
    # arithmetic anything but a tick or a cross, which is where all of its error comes from.
    values["plan_outcome"] = RB.required_outcome({k: values[k] for k in RB.COMPONENTS},
                                                 values["pupil_age"])

    out = {f["name"]: {"value": values.get(f["name"]), "spannable": f.get("type") != "enum",
                       "span": None} for f in fields}
    return {"fields": out, "on_worklist": _compute(values), "recomputed_outcome": None,
            "recomputed_reason": None, "recomputed_missing": [], "recomputed_unmeasurable": [],
            "sections_used": [], "prompt_parts": [], "input_tokens": 0, "output_tokens": 0,
            "parsed": True}


def extract(text, fields):
    return extract_one(text, fields)
