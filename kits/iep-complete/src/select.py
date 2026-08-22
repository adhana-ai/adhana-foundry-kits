"""Pick which sections plausibly carry each field. Pure code -- the last deterministic step before
the model.

⚑ TWO SECTIONS ARE MAPPED BY NOTHING, AND THAT IS THE VISIBLE SAVING. Every plan in this corpus
opens with a `Synthetic Record` banner saying what the file is, and closes by naming the school and
the district it was written at. No field asks for either, so the union of the mapped sections
leaves both out and neither reaches the provider. They are the two sections a reader can point at
and say "that is what selection did".

⚠︎ AND THEY ARE THE ONLY TWO SECTIONS THAT CAN BE DROPPED SAFELY, WHICH ON A COMPLETENESS KIT IS A
SHARPER CONSTRAINT THAN IT LOOKS. Here an ABSENT SECTION IS THE FINDING. A selector that quietly
withheld `Accommodations` would be indistinguishable, to the model, from a plan that never had one
-- so the saving cannot come from dropping component sections, however clever the mapping. Every
section that could carry a component is mapped by its own field and is always sent when it exists;
neither dropped section carries a component, so removing them cannot be mistaken for a defect, and
the system prompt says in as many words that two administrative sections are removed and that a
component whose section is not present is absent from the plan.

⚠︎ NO PER-FIELD FALLBACK TO THE WHOLE DOCUMENT -- A DELIBERATE DIVERGENCE FROM THE SIBLING KITS.
Every other kit in this series returns the whole document when a field's section is not found:
slower, more expensive, always correct. Here it would be WRONG rather than merely expensive. Half
this corpus is missing at least one component section, so a per-field fallback would fire on half
the plans and drag `School and District` back into the prompt on exactly the documents this kit is
about. The fallback moved up one level instead: `plan()` and `src/prompt.py::build()` send the
whole document only when the union across every field is empty -- a plan with no recognisable
headings at all, which is a forker's document rather than one of these.

⚑ `plan_outcome` IS MAPPED TO THE SEVEN COMPONENT SECTIONS AND THE PUPIL'S AGE, AND TO NEITHER
DECOY. That is a statement of the rule rather than a saving, and it is the map of this kit's two
decoys at once:

  - the CHECKLIST is a previous reviewer's own tick-box result, and on this corpus it often claims
    everything is present on a plan that is missing a component or carries a goal nobody can
    measure. It is the checkbox review this kit exists to go past;
  - the CASE MANAGER'S NOTE is prose written by somebody who did not open the rulebook, and its
    tone often points the opposite way from the components.

Both still reach the model -- each is a field in its own right, and the union of every field's
sections is what gets sent -- so this mapping is not a filter that hides either decoy. It is the
map of where the answer actually lives.
"""
from .rulebook import COMPONENTS, SECTION_BY_KEY

# Every component field maps to its own rule's section, read out of data/rulebook.json rather than
# retyped here -- one file names the section headings, and the prompt, the corpus generator and
# this mapping all read it.
SECTION_HINTS = {
    "plan_id": ["Plan"],
    "pupil_ref": ["Pupil Reference"],
    "pupil_age": ["Pupil Age"],
    "plan_status": ["Plan Status"],
    "checklist_claim": ["Checklist Completed By"],
    "case_manager_note": ["Case Manager Note"],
}
for _key in COMPONENTS:
    SECTION_HINTS[_key] = [SECTION_BY_KEY[_key]]

SECTION_HINTS["plan_outcome"] = ["Pupil Age"] + [SECTION_BY_KEY[k] for k in COMPONENTS]

# The sections no field maps to. Named so a reader can check the claim above against the code
# instead of taking it on trust, and asserted in evals/check_labels.py against every plan.
NEVER_SENT = ["Synthetic Record", "School and District"]


def for_field(secs, field):
    """The sections to send for one field, in document order.

    MAY BE EMPTY, unlike every sibling kit's version of this function -- see the module note. An
    empty list means "this field's section is not in this document", which on this kit is a fact
    about the plan rather than a failure of the mapping.
    """
    want = SECTION_HINTS.get(field)
    if not want:
        return list(secs)
    return [s for s in secs if s["name"] in want]


def plan(secs, fields):
    return {f: [s["name"] for s in for_field(secs, f)] for f in fields}
