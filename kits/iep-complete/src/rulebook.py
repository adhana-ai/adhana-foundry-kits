"""THE COMPONENT RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. What counts as a complete
plan is a policy question somebody has to be able to open, read, disagree with and replace — not a
dict buried in a Python module. `data/rulebook.json` is that file. Everything below is the
arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS INVENTED AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no statute, no regulation, no state or district plan template, no agency guidance and no
published checklist, and its transition age (14) is a number this kit chose rather than one taken
from anywhere. See data/SOURCES.md, and the same sentence is printed on the kit's own UI where a
reader actually reads the answer.

⚑ TWO LAYERS, AND KEEPING THEM APART IS THE WHOLE DESIGN.

  1. THE COMPONENT STATE — one per rule, per plan. `absent`, `present_not_measurable`,
     `present_complete`, or `not_required`. It describes THE DOCUMENT, with exactly one exception
     the rulebook states out loud: `not_required` is awarded to `transition` when the plan states
     an age below the transition age, because the rulebook then does not ask for it at all.

     ⚠︎ `present_not_measurable` IS THE ONE THIS KIT EXISTS FOR. A section that is there, is full
     of prose, and states no baseline, no criterion and no measurement method passes every
     checkbox review — the box gets ticked and the pupil gets a year of provision nobody can
     evaluate. It is much harder to detect than an absent section, and evals/baseline.py is a
     checkbox reviewer precisely so the gap between the two is a measured number rather than a
     claim.

  2. THE PLAN OUTCOME — one per plan, computed from the seven states by `decide()` below, in a
     stopping order. The model never decides this; it reports the seven states and the outcome
     that follows from them, and the same function re-derives it in evals/judge.py.

⚑ FOUR CHECKS, IN THIS ORDER, AND THE ORDER IS A DECISION RATHER THAN AN ACCIDENT:

  1. MISSING COMPONENTS. Any REQUIRED component absent -> `components_missing`.
  2. NOT MEASURABLE. Any REQUIRED component present and not measurable -> `not_measurable`.
  3. NOT DETERMINABLE. The plan does not state the pupil's age AND transition content is anything
     other than present-and-complete -> `undetermined`. The rulebook cannot say whether that
     section was required, and it says so rather than guessing.
  4. Otherwise -> `complete`.

  ⚠︎ WHY `undetermined` IS THIRD AND NOT FIRST. The sibling kit this shape was taken from puts its
  unknown FIRST, because an unrecorded prior cargo makes every later check unanswerable. Here a
  missing age makes exactly ONE component unanswerable and leaves the other six perfectly
  readable, so reporting `undetermined` ahead of a genuinely absent section would hide a defect the
  reviewer can act on today behind one they cannot. `undetermined` here means something narrow and
  useful: this plan is otherwise complete, and somebody has to go and find out the pupil's age.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


M = load()

RULES = list(M["rules"])
COMPONENTS = [r["key"] for r in RULES]
RULE_BY_KEY = {r["key"]: r for r in RULES}
SECTION_BY_KEY = {r["key"]: r["section"] for r in RULES}

# The four component states, and the four plan outcomes. Two different vocabularies on purpose —
# see the two-layer note at the top. src/prompt.py declares the reader-facing meanings of both.
STATES = tuple(M["states"])
OUTCOMES = ("complete", "components_missing", "not_measurable", "undetermined")

TRANSITION_AGE = int(M["transition_age"])
CONDITIONAL = [r["key"] for r in RULES if r.get("applies") == "conditional"]
ALWAYS = [r["key"] for r in RULES if r.get("applies") != "conditional"]


def transition_state_is_awarded(pupil_age):
    """Is `not_required` the correct state for the conditional component at this age?

    True only when an age is STATED and is below the threshold. A plan with no age stated never
    earns `not_required` — that is the whole difference between "the rulebook does not ask for
    this" and "nobody can tell whether the rulebook asks for this", and collapsing the two is the
    defect this predicate exists to prevent.
    """
    return pupil_age is not None and int(pupil_age) < TRANSITION_AGE


def required_components(states, pupil_age):
    """Which components this plan is actually judged on.

    The six unconditional ones always. The conditional one only when the plan states an age at or
    above the threshold — never when the age is missing, because an unknown requirement is not a
    requirement, and asserting one would turn a question into a finding.
    """
    out = list(ALWAYS)
    for key in CONDITIONAL:
        if pupil_age is None:
            continue
        if int(pupil_age) >= TRANSITION_AGE:
            out.append(key)
    return out


def _age(pupil_age):
    """An age as an int, or None. A value the plan states in words is not an age."""
    if pupil_age in (None, "", "null"):
        return None
    try:
        return int(str(pupil_age).strip())
    except (TypeError, ValueError):
        return None


def decide(states, pupil_age):
    """THE RULE, in one place. {outcome, reason, missing, unmeasurable, undetermined_because}.

    ⚑ ONE DEFINITION, THREE READERS — tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    states for the no-gold consistency diagnostic. They cannot drift about what an outcome means.

    ⚠︎ IT PROPOSES A WORKLIST. IT DECIDES NOTHING. The return value names what a reviewer should
    look at and why; it never approves, signs, files or amends a plan, and nothing in this kit
    writes anything anywhere.
    """
    out = {"outcome": None, "reason": None, "missing": [], "unmeasurable": [],
           "undetermined_because": None}

    age = _age(pupil_age)
    clean = {}
    for key in COMPONENTS:
        v = states.get(key)
        clean[key] = v if v in STATES else None

    unknown = [k for k in COMPONENTS if clean[k] is None]
    if unknown:
        out["outcome"] = "undetermined"
        out["undetermined_because"] = ("no state was returned for %s, so the rulebook has nothing "
                                       "to judge" % ", ".join(unknown))
        out["reason"] = out["undetermined_because"]
        return out

    required = required_components(clean, age)

    # ⚑ `not_required` ON A COMPONENT THE RULEBOOK DOES REQUIRE IS A CONTRADICTION, NOT A PASS.
    # Without this clause the state is a free exit from every requirement: answer `not_required`
    # for transition on a 16-year-old's plan and the component drops out of `missing` and out of
    # `unmeasurable` at once, and the plan reads `complete`. The gold set never contains it; a
    # reply can, which is exactly why the check belongs in the rule the scorer re-runs rather
    # than in the corpus generator. Named as undetermined because the record and the state
    # disagree and neither one wins on its own.
    contradictory = [k for k in required if clean[k] == "not_required"]
    if contradictory:
        out["outcome"] = "undetermined"
        out["undetermined_because"] = (
            "%s is recorded as not required, and this plan's stated age is at or above the "
            "rulebook's transition age of %d, which requires it"
            % (", ".join(contradictory), TRANSITION_AGE))
        out["reason"] = out["undetermined_because"]
        return out

    out["missing"] = [k for k in required if clean[k] == "absent"]
    out["unmeasurable"] = [k for k in required if clean[k] == "present_not_measurable"]

    if out["missing"]:
        out["outcome"] = "components_missing"
        out["reason"] = ("%d required component(s) are not in this plan at all: %s. A section that "
                         "is not there cannot be reviewed, corrected or delivered against."
                         % (len(out["missing"]),
                            ", ".join(RULE_BY_KEY[k]["label"] for k in out["missing"])))
        return out

    if out["unmeasurable"]:
        out["outcome"] = "not_measurable"
        out["reason"] = ("Every required component is present, and %d of them cannot be measured "
                         "against: %s. Each is written, each would pass a checkbox review, and "
                         "none of them can be shown to have been met or missed."
                         % (len(out["unmeasurable"]),
                            ", ".join(RULE_BY_KEY[k]["label"] for k in out["unmeasurable"])))
        return out

    if age is None and clean.get("transition") != "present_complete":
        out["outcome"] = "undetermined"
        out["undetermined_because"] = "the plan does not state the pupil's age"
        out["reason"] = ("Every component this rulebook can judge is complete, and the plan does "
                         "not state the pupil's age — so nobody can say whether transition "
                         "content was required. Find the age before calling this plan complete.")
        return out

    out["outcome"] = "complete"
    out["reason"] = ("Every component this rulebook requires is present and is stated in terms "
                     "somebody can measure against at the next review.")
    return out


def required_outcome(states, pupil_age):
    """Just the outcome string, or None when the states are outside the rulebook's vocabulary."""
    o = decide(states, pupil_age)["outcome"]
    return o if o in OUTCOMES else None
