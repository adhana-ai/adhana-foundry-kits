#!/usr/bin/env python3
"""Generate synthetic individualised education plans and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one plan per file) and data/gold.jsonl, byte-identical on every run.

⚠︎ NO REAL PUPIL DATA AND NOTHING RESEMBLING IT. Every plan here is invented by this script. There
are no names -- a pupil is a reference CODE and nothing else. There are no dates of birth and no
dates of any kind. There is no disability category, no diagnosis and no eligibility label anywhere
in the corpus, and no need statement is tied to a person: the plans state performance levels and
goals in ordinary curriculum terms. Every school and district name is a made-up compound, every
plan carries a `Synthetic Record` banner as its first section saying what it is, and nothing was
fetched from anywhere. See data/SOURCES.md.

⚠︎ NO STATUTE, REGULATION, STATE TEMPLATE, AGENCY GUIDANCE OR PUBLISHED CHECKLIST IS REPRODUCED.
The rulebook this corpus is built against is `data/rulebook.json`, which was written for this kit
and is invented rather than authoritative -- including its transition age of 14, which is a number
this kit chose.

⚑ GOLD IS TWO LAYERS, AND ONLY ONE OF THEM IS A LABEL.
  - the seven COMPONENT STATES are the values this generator built the plan text FROM, and
    `_verify()` asserts every one of them is readable off the plan it labels: an `absent` component
    has no section or a placeholder body, a `present_complete` one carries every element the rule
    names, and a `present_not_measurable` one is missing exactly one of them.
  - `plan_outcome` is NOT a label at all. It is `src/rulebook.py::decide()` run over those seven
    states and the pupil's age -- the same function `src/prompt.py` states to the model in words
    and `evals/judge.py` re-runs over the model's own reply. Three readers, one definition.

⚑ THE FOUR HARD CASES, AND WHY EACH IS ITS OWN BUCKET. A reader who ticks section headings gets
every one of them wrong, and each is a different way of being wrong:

  goal_unmeasurable    -- every section is there, and a goal states no baseline, no criterion or no
                          measurement method. THIS IS THE ONE THE KIT EXISTS FOR. It passes a
                          checkbox review outright.
  services_unspecified -- every section is there, and a service line is missing its frequency, its
                          duration or its location, so nobody can reconcile what was delivered.
  transition_not_required -- the plan has no transition section AND that is CORRECT, because the
                          pupil's stated age is below the rulebook's threshold. A checker that
                          counts seven components raises a false defect on every one of these.
  undetermined_age     -- the plan does not state the pupil's age and carries no transition
                          content, so whether that component was required CANNOT BE DETERMINED. It
                          is a real answer, not a failure to produce one.

⚑ THE PLANTED AMBIGUITY IS TWO DECOYS, NOT ONE.
  - the CHECKLIST: a previous reviewer's own tick-box result, printed on the plan. On many plans it
    claims every required component is present while the rulebook finds a defect. It is the
    checkbox review this kit exists to go past, and it is never an input to anything.
  - the CASE MANAGER'S NOTE: free text whose TONE contradicts the components on `N_AMBIGUOUS` of
    plans, in both directions -- a reassuring note on a defective plan, a worried note on a sound
    one.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                    # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260822
N_RECORDS = 52

CORE = [k for k in RB.COMPONENTS if k != "transition"]

# ⚑ THE COMPOSITION IS EXACT AND THEN SHUFFLED, NOT DRAWN PER RECORD -- the fix a sibling kit in
# this series had to make after its first generator asked for 40 pct ambiguity and delivered 51.
# A count 1.7 standard deviations off its own design is not a corpus property, it is sampling noise
# being published as one. So every bucket here is a fixed COUNT, shuffled by the seeded RNG.
BUCKETS = [
    ("complete_all", 7),                  # every required component present and measurable
    ("transition_not_required", 5),       # correct AND has no transition section -- the false-alarm trap
    ("missing_one", 7),                   # exactly one required component absent
    ("missing_several", 4),               # two or three absent
    ("transition_missing_required", 4),   # age at or above the threshold, no transition section
    ("goal_unmeasurable", 8),             # THE HEADLINE CASE: a goal nobody can measure
    ("services_unspecified", 5),          # a service line with no frequency, duration or location
    ("progress_no_schedule", 4),          # a measurement method with no reporting frequency
    ("transition_unmeasurable", 3),       # a post-school goal with no steps under it
    ("undetermined_age", 5),              # no age stated and no transition content -- cannot say
]

EXPECTED_OUTCOME = {
    "complete_all": "complete",
    "transition_not_required": "complete",
    "missing_one": "components_missing",
    "missing_several": "components_missing",
    "transition_missing_required": "components_missing",
    "goal_unmeasurable": "not_measurable",
    "services_unspecified": "not_measurable",
    "progress_no_schedule": "not_measurable",
    "transition_unmeasurable": "not_measurable",
    "undetermined_age": "undetermined",
}

# Which age bands a bucket may carry. `under` is below the rulebook's transition age, `over` at or
# above it, `none` means the plan does not state an age at all.
BANDS = {
    "complete_all": ("over",),
    "transition_not_required": ("under",),
    "missing_one": ("over", "under", "none"),
    "missing_several": ("over", "under"),
    "transition_missing_required": ("over",),
    "goal_unmeasurable": ("over", "under", "none"),
    "services_unspecified": ("over", "under", "none"),
    "progress_no_schedule": ("over", "under"),
    "transition_unmeasurable": ("over",),
    "undetermined_age": ("none",),
}
N_UNDER, N_NONE = 14, 8               # the rest are `over`; 52 - 14 - 8 = 30

N_AMBIGUOUS = 21                      # 40 pct, exactly -- a case manager note from the wrong register
N_AMBIGUOUS_ON_COMPLETE = 6           # ... of which this many sit on a SOUND plan (worried note)
N_IN_EFFECT = 24                      # plan_status == "in_effect"; the rest are still "draft"
N_ALL_PRESENT_ON_DEFECTIVE = 18       # the checklist claims everything is there, and it is not
N_ALL_PRESENT_ON_COMPLETE = 8         # ... and here it is right
N_OUTSTANDING_ON_COMPLETE = 2         # ... and here it is needlessly pessimistic
N_OUTSTANDING_ON_DEFECTIVE = 14
# ⚠︎ ALL THREE CLAIM VALUES APPEAR ON BOTH SOUND AND DEFECTIVE PLANS, DELIBERATELY. Dealing every
# `complete` plan the same claim would put a perfect one-line shortcut in the corpus -- read the
# checklist, copy it -- and a run that took it would score as a run that read the plan.
N_SECONDARY_UNMEASURABLE = 12         # a SECOND unmeasurable component, on plans already defective
N_PLACEHOLDER = 5                     # absences written as 'to be completed' rather than omitted
N_GOAL_DEFECT_OMIT = 4                # of the 8 goal_unmeasurable plans: an element LINE missing
# the other 4 state the element in words carrying no quantity -- the harder half

# Invented schools and districts. No real school, district, charter network or agency is named
# anywhere in this kit, and every one of these is a made-up compound.
PLACES = [
    ("Hollowbrook Middle School", "Fenmoor Unified District"),
    ("Alderquay Elementary School", "Westbarrow County District"),
    ("Marram Ridge High School", "Cliveport Public District"),
    ("Stonepath Academy", "Ashcombe Valley District"),
    ("Farrowgate Middle School", "Quillhaven Unified District"),
    ("Kettleford Elementary School", "Northmere Public District"),
]

AREAS = ["reading fluency", "reading comprehension", "written expression",
         "mathematics problem solving", "expressive language", "organisation and task initiation",
         "attention and self-regulation", "fine motor handwriting"]

METHODS = ["a weekly curriculum-based measurement probe", "a fortnightly running record",
           "scored classroom work samples", "the school's own writing rubric",
           "a structured observation schedule", "a monthly timed fluency probe"]

SERVICE_NAMES = ["Specialist reading instruction", "Speech and language therapy",
                 "Occupational therapy", "Mathematics intervention group",
                 "Counselling support", "Assistive technology support"]
SERVICE_PLACES = ["the resource room", "the therapy room", "the general classroom",
                  "the learning support suite", "a small-group room"]

ACCOMMODATIONS = ["Extended time, 1.5x, on written assessments",
                  "Preferential seating within 2 metres of the board",
                  "Text-to-speech for reading passages",
                  "A printed copy of every set of instructions",
                  "Movement breaks of 5 minutes",
                  "A reduced number of items per worksheet"]
ACC_SETTINGS = ["in every subject", "in all classrooms", "in the resource room and at home",
                "in mathematics and science", "during all assessments"]

POST_SCHOOL = ["enrol on a college-level technology certificate",
               "take up supported employment in a retail setting",
               "complete a vocational catering course",
               "move to independent travel training and part-time work"]
STEPS = ["two supported college visits in the autumn term",
         "a work-readiness unit, 1 session per week for 12 weeks",
         "a careers meeting with the family in the spring term",
         "a 5-day supported work placement in the summer term"]

VAGUE_QUANTITIES = ["to the best of the pupil's ability", "as appropriate to the task",
                    "at an improved level", "in line with expectations"]
VAGUE_BASELINES = ["the pupil currently finds this difficult",
                   "performance is below that of peers",
                   "this is an area of ongoing need"]
VAGUE_FREQUENCIES = ["The family will be updated regularly.",
                     "Progress will be shared as needed.",
                     "The team will report periodically."]

# Notes whose TONE says "this plan is fine". Used truthfully on a plan whose outcome is `complete`,
# and against type on one that is not -- half the planted ambiguity.
CALM_NOTES = [
    "Reviewed with the team; everything is in place and ready to sign.",
    "Standard annual rewrite for this pupil. Paperwork looked in order to me.",
    "No concerns from my side. Happy for this one to go to the meeting.",
    "Straightforward plan, nothing unusual about it at all.",
]

# Notes whose TONE says "something is wrong with this plan". Used truthfully on a plan whose
# outcome is not `complete`, and against type on one that is sound -- the other half.
WORRIED_NOTES = [
    "Not confident this one is ready; asked for another look before the meeting.",
    "Something looked thin here -- flagged for a second read before it goes out.",
    "Escalated to the programme lead; the write-up did not sit right with me.",
    "The previous version of this plan is disputed by the family; under manual review this term.",
]

CHECKLIST_LINES = {
    "all_present": "Reviewer R-%04d -- all required components present: yes",
    "items_outstanding": "Reviewer R-%04d -- items outstanding at the time of checking: %d",
    "not_completed": "No completeness checklist on file for this plan.",
}


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _deal(rng, n, spec):
    """A shuffled list of exactly `n` values built from (value, count) pairs. Deterministic."""
    out = []
    for value, count in spec:
        out.extend([value] * count)
    while len(out) < n:
        out.append(spec[0][0])
    out = out[:n]
    rng.shuffle(out)
    return out


# ------------------------------------------------------------------------------------------------
# One renderer per component, per state. Each returns the SECTION BODY, or None when the component
# is absent by omission -- in which case the section itself is not written at all.
# ------------------------------------------------------------------------------------------------

def _present_levels(rng, state):
    if state == "present_complete":
        area = rng.choice(AREAS)
        return ("%s: %d of a possible %d on the autumn benchmark, against a year-group median of "
                "%d.\nThis level means the pupil cannot complete unmodified grade-level tasks in "
                "this area without the support set out below."
                % (area.capitalize(), rng.randint(3, 9), rng.randint(12, 20), rng.randint(10, 16)))
    return ("The pupil continues to find %s difficult and is working below the level of peers. "
            "Work in this area is improving but remains a need, and this affects access to the "
            "wider curriculum." % rng.choice(AREAS))


def _goal_block(rng, n, area, defect=None):
    """One numbered goal. `defect` is None, 'omit_<element>' or 'vague_<element>'."""
    baseline = "%d words correct per minute" % rng.randint(20, 60)
    criterion = "%d words correct per minute on 3 consecutive probes" % rng.randint(70, 120)
    if area != "reading fluency":
        baseline = "%d of %d on the classroom rubric" % (rng.randint(2, 5), rng.randint(8, 12))
        criterion = "%d of %d on the classroom rubric, on 4 of 5 occasions" % (
            rng.randint(6, 9), rng.randint(8, 12))
    method = rng.choice(METHODS)

    lines = ["Goal %d -- %s" % (n, area)]
    show_baseline = show_criterion = show_method = True
    if defect == "omit_baseline":
        show_baseline = False
    elif defect == "omit_criterion":
        show_criterion = False
    elif defect == "omit_method":
        show_method = False
    elif defect == "vague_baseline":
        baseline = rng.choice(VAGUE_BASELINES)
    elif defect == "vague_criterion":
        criterion = rng.choice(VAGUE_QUANTITIES)

    if show_baseline:
        lines.append("  Baseline: %s" % baseline)
    if show_criterion:
        lines.append("  Criterion: %s" % criterion)
    if show_method:
        lines.append("  Measured by: %s" % method)
    return "\n".join(lines)


def _annual_goals(rng, state, defect_kind=None):
    n_goals = rng.choice([2, 3])
    areas = rng.sample(AREAS, n_goals)
    if state == "present_complete":
        return "\n".join(_goal_block(rng, i + 1, areas[i]) for i in range(n_goals)), None
    # Exactly one goal is defective, and it is deliberately not always the first: a reader who
    # checks the first goal and moves on gets these wrong, which is the point of the bucket.
    bad = rng.randrange(n_goals)
    defect = defect_kind or rng.choice(["omit_criterion", "vague_criterion"])
    blocks = [_goal_block(rng, i + 1, areas[i], defect if i == bad else None)
              for i in range(n_goals)]
    return "\n".join(blocks), bad


def _progress(rng, state):
    method = rng.choice(METHODS)
    if state == "present_complete":
        return ("Progress against each goal is measured by %s.\nProgress is reported to the "
                "family every %d weeks, alongside the general report card."
                % (method, rng.choice([6, 9, 12])))
    return "Progress against each goal is measured by %s.\n%s" % (method,
                                                                  rng.choice(VAGUE_FREQUENCIES))


def _service_line(rng, name, defect=None):
    n_sessions = rng.randint(1, 5)
    freq = "%d session%s per week" % (n_sessions, "" if n_sessions == 1 else "s")
    dur = "%d minutes each" % rng.choice([20, 25, 30, 40, 45])
    where = "in %s" % rng.choice(SERVICE_PLACES)
    if defect == "omit_frequency":
        return "%s -- %s, %s." % (name, dur, where)
    if defect == "omit_duration":
        return "%s -- %s, %s." % (name, freq, where)
    if defect == "vague_location":
        return "%s -- %s, %s, in the appropriate setting." % (name, freq, dur)
    return "%s -- %s, %s, %s." % (name, freq, dur, where)


def _services(rng, state):
    n = rng.choice([2, 3])
    names = rng.sample(SERVICE_NAMES, n)
    if state == "present_complete":
        return "\n".join(_service_line(rng, nm) for nm in names)
    bad = rng.randrange(n)
    defect = rng.choice(["omit_frequency", "omit_duration", "vague_location"])
    return "\n".join(_service_line(rng, nm, defect if i == bad else None)
                     for i, nm in enumerate(names))


def _accommodations(rng, state):
    n = rng.choice([2, 3])
    picks = rng.sample(ACCOMMODATIONS, n)
    if state == "present_complete":
        return "\n".join("%s -- %s." % (a, rng.choice(ACC_SETTINGS)) for a in picks)
    if rng.random() < 0.5:
        return "Accommodations to be provided as needed, at teacher discretion."
    bad = rng.randrange(n)
    return "\n".join(("%s." % a) if i == bad else ("%s -- %s." % (a, rng.choice(ACC_SETTINGS)))
                     for i, a in enumerate(picks))


def _participation(rng, state):
    if state == "present_complete":
        return ("The pupil will be outside the general classroom for %d minutes of the 1,650 "
                "minutes in a school week, for the services set out above, because that "
                "instruction cannot be delivered at the intensity needed in a class of %d."
                % (rng.choice([120, 180, 240, 300, 360]), rng.randint(24, 31)))
    return rng.choice([
        "The pupil will participate with peers wherever it is appropriate to do so.",
        "Inclusion with peers is supported and encouraged as far as possible.",
        "The pupil will be included in general classes to the greatest extent that works for "
        "them.",
    ])


def _transition(rng, state):
    goal = rng.choice(POST_SCHOOL)
    if state == "present_complete":
        picks = rng.sample(STEPS, 2)
        return ("Post-school goal: %s.\nSteps this plan year: %s; and %s."
                % (goal, picks[0], picks[1]))
    return "Post-school goal: %s.\nThe team will look at options nearer the time." % goal


RENDER = {
    "present_levels": _present_levels,
    "progress_measurement": _progress,
    "services": _services,
    "accommodations": _accommodations,
    "participation_rationale": _participation,
    "transition": _transition,
}


def _states_for(rng, bucket, band, absent_pick, secondary, goal_defect):
    """The seven component states this bucket asks for. Pure data -- the text is rendered from it."""
    states = {k: "present_complete" for k in RB.COMPONENTS}

    if band == "under":
        states["transition"] = "not_required"
    elif band == "none":
        # No age stated, so `not_required` can never be correct. undetermined_age plans carry no
        # transition section at all; the others carry complete content.
        states["transition"] = "absent" if bucket == "undetermined_age" else "present_complete"

    if bucket == "missing_one":
        states[absent_pick[0]] = "absent"
    elif bucket == "missing_several":
        for k in absent_pick:
            states[k] = "absent"
    elif bucket == "transition_missing_required":
        states["transition"] = "absent"
    elif bucket == "goal_unmeasurable":
        states["annual_goals"] = "present_not_measurable"
    elif bucket == "services_unspecified":
        states["services"] = "present_not_measurable"
    elif bucket == "progress_no_schedule":
        states["progress_measurement"] = "present_not_measurable"
    elif bucket == "transition_unmeasurable":
        # Only reachable at or above the transition age -- see BANDS. A post-school goal with no
        # steps under it below the threshold would be `not_required` and would decide nothing.
        states["transition"] = "present_not_measurable"

    # ⚠︎ THE SECOND UNMEASURABLE COMPONENT FALLS THROUGH TO THE NEXT CANDIDATE RATHER THAN BEING
    # DROPPED. Written as a single `if state == present_complete` it silently did nothing whenever
    # the drawn component was already absent on that plan -- 12 asked for, 11 delivered, and the
    # shortfall would have landed on whichever component the exact deal happened to collide with.
    # A composition that is exact in the deal and approximate on the page is the defect the exact
    # deal exists to prevent.
    if secondary:
        order = ["present_levels", "accommodations", "participation_rationale"]
        start = order.index(secondary)
        for step in range(len(order)):
            key = order[(start + step) % len(order)]
            if states[key] == "present_complete":
                states[key] = "present_not_measurable"
                break
    return states


def _render_plan(rng, rec_id, plan_id, pupil_ref, age, band, status, states, place,
                 goal_defect, placeholder_keys, checklist, note):
    school, district = place
    lines = [
        _underline("Synthetic Record"),
        "GENERATED SAMPLE -- not a real pupil, school or district. No names, no dates and no "
        "diagnosis appear anywhere in this file.",
        "Written by tools/build_corpus.py from seed %d." % SEED, "",
        _underline("Plan"), plan_id, "",
        _underline("Pupil Reference"), pupil_ref, "",
        _underline("Pupil Age"), ("not stated" if age is None else str(age)), "",
        _underline("Plan Status"), status, "",
    ]

    goal_bad_index = None
    for key in RB.COMPONENTS:
        state = states[key]
        section = RB.SECTION_BY_KEY[key]
        if state == "not_required" or (state == "absent" and key not in placeholder_keys):
            continue                       # the section is simply not in the plan
        if state == "absent":
            body = rng.choice(RB.M["placeholder_bodies"])
        elif key == "annual_goals":
            body, goal_bad_index = _annual_goals(
                rng, state, goal_defect if state == "present_not_measurable" else None)
        else:
            body = RENDER[key](rng, state)
        lines += [_underline(section), body, ""]

    lines += [_underline("Checklist Completed By"), checklist, ""]
    lines += [_underline("Case Manager Note"), note, ""]
    lines += [_underline("School and District"), "%s, %s" % (school, district), ""]
    return "\n".join(lines) + "\n", goal_bad_index


def build_all(rng, n=N_RECORDS):
    spec = list(BUCKETS)
    if n != N_RECORDS:
        spec = [(name, max(1, round(count * n / N_RECORDS))) for name, count in BUCKETS]
    buckets = _deal(rng, n, spec)

    # ---- age bands: the forced ones first, then the flexible slots, all exact ------------------
    bands = [None] * n
    under_left, none_left = N_UNDER, N_NONE
    for i, b in enumerate(buckets):
        if len(BANDS[b]) == 1:
            bands[i] = BANDS[b][0]
            if bands[i] == "under":
                under_left -= 1
            elif bands[i] == "none":
                none_left -= 1
    flexible = [i for i in range(n) if bands[i] is None]
    none_slots = [i for i in flexible if "none" in BANDS[buckets[i]]]
    picked_none = rng.sample(sorted(none_slots), none_left)
    for i in picked_none:
        bands[i] = "none"
    rest = [i for i in flexible if bands[i] is None]
    picked_under = rng.sample(sorted(rest), under_left)
    for i in picked_under:
        bands[i] = "under"
    for i in range(n):
        if bands[i] is None:
            bands[i] = "over"

    # ---- which component is absent -------------------------------------------------------------
    # ⚑ DEALT FROM ONE RING RATHER THAN SAMPLED PER PLAN, so no core component can end up absent on
    # a single plan by chance. The ring holds three copies of each of the six; 7 single-absence
    # plans and 4 multi-absence plans consume 17 of the 18, which puts every component at two
    # absences or more by construction rather than by luck. Sampling per plan gave `annual_goals`
    # exactly one, and a component with one instance is an anecdote in a denominator.
    ring = CORE * 3
    rng.shuffle(ring)
    pos = 0
    absent_by_slot = {}
    for i in range(n):
        if buckets[i] == "missing_one":
            absent_by_slot[i] = [ring[pos]]
            pos += 1
    for i in range(n):
        if buckets[i] == "missing_several":
            want, picked = rng.choice([2, 3]), []
            while len(picked) < want and pos < len(ring):
                if ring[pos] not in picked:
                    picked.append(ring[pos])
                pos += 1
            absent_by_slot[i] = picked

    # ---- a SECOND unmeasurable component, on plans whose outcome it cannot change --------------
    sec_ok = [i for i in range(n) if buckets[i] in
              ("missing_one", "missing_several", "transition_missing_required",
               "goal_unmeasurable", "services_unspecified", "progress_no_schedule",
               "transition_unmeasurable")]
    sec_slots = rng.sample(sorted(sec_ok), N_SECONDARY_UNMEASURABLE)
    sec_choices = ["present_levels", "accommodations", "participation_rationale"] * 4
    rng.shuffle(sec_choices)
    secondary = dict(zip(sorted(sec_slots), sec_choices[:len(sec_slots)]))

    # ---- goal defect flavour, exactly split between the two --------------------------------
    goal_slots = sorted(i for i in range(n) if buckets[i] == "goal_unmeasurable")
    flavours = _deal(rng, len(goal_slots),
                     [("omit", N_GOAL_DEFECT_OMIT), ("vague", len(goal_slots) - N_GOAL_DEFECT_OMIT)])
    goal_defect = {}
    for slot, fl in zip(goal_slots, flavours):
        goal_defect[slot] = (rng.choice(["omit_baseline", "omit_criterion", "omit_method"])
                             if fl == "omit"
                             else rng.choice(["vague_baseline", "vague_criterion"]))

    statuses = _deal(rng, n, [("in_effect", N_IN_EFFECT), ("draft", n - N_IN_EFFECT)])

    # ---- PASS ONE: states and outcomes ---------------------------------------------------------
    rows = []
    for i in range(n):
        bucket = buckets[i]
        band = bands[i]
        age = (None if band == "none"
               else (rng.randint(6, RB.TRANSITION_AGE - 1) if band == "under"
                     else rng.randint(RB.TRANSITION_AGE, 18)))
        states = _states_for(rng, bucket, band, absent_by_slot.get(i, []), secondary.get(i),
                             goal_defect.get(i))
        outcome = RB.decide(states, age)["outcome"]
        assert outcome == EXPECTED_OUTCOME[bucket], \
            "%s produced %r, not %r (states=%r age=%r)" % (bucket, outcome,
                                                           EXPECTED_OUTCOME[bucket], states, age)
        rows.append({"i": i, "bucket": bucket, "band": band, "age": age, "states": states,
                     "outcome": outcome, "status": statuses[i]})

    # ---- PASS TWO: the two decoys, dealt EXACTLY against the outcomes they contradict ----------
    done = [r["i"] for r in rows if r["outcome"] == "complete"]
    defective = [r["i"] for r in rows if r["outcome"] != "complete"]
    ambiguous = set(rng.sample(sorted(done), N_AMBIGUOUS_ON_COMPLETE))
    ambiguous |= set(rng.sample(sorted(defective), N_AMBIGUOUS - N_AMBIGUOUS_ON_COMPLETE))

    claims = {}
    for i in rng.sample(sorted(defective), N_ALL_PRESENT_ON_DEFECTIVE):
        claims[i] = "all_present"
    for i in rng.sample(sorted(done), N_ALL_PRESENT_ON_COMPLETE):
        claims[i] = "all_present"
    for i in rng.sample(sorted(i for i in done if i not in claims), N_OUTSTANDING_ON_COMPLETE):
        claims[i] = "items_outstanding"
    left_def = [i for i in defective if i not in claims]
    rng.shuffle(left_def)
    for j, i in enumerate(left_def):
        claims[i] = "items_outstanding" if j < N_OUTSTANDING_ON_DEFECTIVE else "not_completed"
    for i in done:
        claims.setdefault(i, "not_completed")

    # ---- placeholder absences, dealt across the absent instances that exist --------------------
    absent_pairs = sorted((r["i"], k) for r in rows for k in RB.COMPONENTS
                          if r["states"][k] == "absent")
    placeholders = {}
    for i, k in rng.sample(absent_pairs, min(N_PLACEHOLDER, len(absent_pairs))):
        placeholders.setdefault(i, set()).add(k)

    # ---- PASS THREE: render ---------------------------------------------------------------------
    out = []
    stats = {"outcomes": {}, "buckets": {b: 0 for b, _ in BUCKETS}, "ambiguous": 0,
             "on_worklist": 0, "unmeasurable_cells": 0, "absent_cells": 0, "not_required": 0,
             "checklist_trap": 0, "goal_defect_not_first": 0, "no_age_not_undetermined": 0,
             "placeholders": 0}

    for r in rows:
        i = r["i"]
        rec_id = "IEP-%04d" % (i + 1)
        plan_id = "PLN-%s%s-%05d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"),
                                     rng.choice("ABCDEFGHJKLMNPRSTVW"), rng.randint(10000, 99999))
        pupil_ref = "PUP-%s%02d-%04d" % (rng.choice("ABCDEFGHJKLMNPRSTVW"), rng.randint(10, 99),
                                         rng.randint(1000, 9999))
        claim = claims[i]
        if claim == "all_present":
            checklist = CHECKLIST_LINES[claim] % rng.randint(1000, 9999)
        elif claim == "items_outstanding":
            checklist = CHECKLIST_LINES[claim] % (rng.randint(1000, 9999), rng.randint(1, 4))
        else:
            checklist = CHECKLIST_LINES[claim]

        # Tone matches the outcome normally, and contradicts it when ambiguous.
        calm = (r["outcome"] == "complete") if i not in ambiguous else (r["outcome"] != "complete")
        note = rng.choice(CALM_NOTES if calm else WORRIED_NOTES)

        text, bad_goal = _render_plan(rng, rec_id, plan_id, pupil_ref, r["age"], r["band"],
                                      r["status"], r["states"], rng.choice(PLACES),
                                      goal_defect.get(i), placeholders.get(i, set()),
                                      checklist, note)

        gold = {"plan_id_rec": rec_id, "plan_id": plan_id, "pupil_ref": pupil_ref,
                "pupil_age": r["age"], "plan_status": r["status"]}
        gold.update({k: r["states"][k] for k in RB.COMPONENTS})
        gold["checklist_claim"] = claim
        gold["case_manager_note"] = note
        gold["plan_outcome"] = r["outcome"]
        out.append((rec_id, text, gold, r["bucket"]))

        stats["outcomes"][r["outcome"]] = stats["outcomes"].get(r["outcome"], 0) + 1
        stats["buckets"][r["bucket"]] += 1
        if i in ambiguous:
            stats["ambiguous"] += 1
        if r["outcome"] != "complete" and r["status"] == "in_effect":
            stats["on_worklist"] += 1
        for k in RB.COMPONENTS:
            if r["states"][k] == "present_not_measurable":
                stats["unmeasurable_cells"] += 1
            elif r["states"][k] == "absent":
                stats["absent_cells"] += 1
            elif r["states"][k] == "not_required":
                stats["not_required"] += 1
        if claim == "all_present" and r["outcome"] != "complete":
            stats["checklist_trap"] += 1
        if bad_goal not in (None, 0):
            stats["goal_defect_not_first"] += 1
        if r["age"] is None and r["outcome"] != "undetermined":
            stats["no_age_not_undetermined"] += 1
        stats["placeholders"] += len(placeholders.get(i, set()))
    return out, stats


def _body(text, section):
    """The body of a named section, or None when the plan has no such section."""
    head = "%s\n%s" % (section, "-" * max(len(section), 3))
    at = text.find(head)
    if at < 0:
        return None
    rest = text[at + len(head):].lstrip("\n")
    cut = rest.find("\n\n")
    return (rest if cut < 0 else rest[:cut]).strip()


def _has_digit(s):
    return any(ch.isdigit() for ch in s or "")


def _verify(rows):
    """Every gold state must be READABLE OFF the plan it labels, and every gold outcome must be
    that plan's own rulebook lookup. A corpus whose labels are not derivable from its own text is
    not a corpus, it is a second opinion."""
    for rec_id, text, gold, bucket in rows:
        for field in ("plan_id", "pupil_ref", "plan_status", "case_manager_note"):
            assert gold[field] in text, "%s: %s not stated in the plan" % (rec_id, field)
        if gold["pupil_age"] is None:
            assert "not stated" in text, "%s: null age not explained" % rec_id
        else:
            assert _body(text, "Pupil Age") == str(gold["pupil_age"]), \
                "%s: pupil_age not stated verbatim" % rec_id

        assert _body(text, "School and District"), "%s: no School and District section" % rec_id
        assert _body(text, "Synthetic Record"), "%s: no Synthetic Record banner" % rec_id

        for key in RB.COMPONENTS:
            state = gold[key]
            body = _body(text, RB.SECTION_BY_KEY[key])
            if state in ("absent", "not_required"):
                assert body is None or body in RB.M["placeholder_bodies"], \
                    "%s: %s is %s and its section carries real content" % (rec_id, key, state)
                continue
            assert body, "%s: %s is %r and has no section body" % (rec_id, key, state)
            measurable = state == "present_complete"

            if key == "present_levels":
                assert _has_digit(body) == measurable, \
                    "%s: present_levels %r does not match its text" % (rec_id, state)
            elif key == "annual_goals":
                blocks = [b for b in body.split("Goal ") if b.strip()]
                assert blocks, "%s: annual_goals has no goal blocks" % rec_id
                ok = []
                for b in blocks:
                    has = {e: ("%s:" % e) in b for e in ("Baseline", "Criterion", "Measured by")}
                    quantified = all(_has_digit(line) for line in b.splitlines()
                                     if line.strip().startswith(("Baseline:", "Criterion:")))
                    ok.append(all(has.values()) and quantified)
                assert all(ok) == measurable, \
                    "%s: annual_goals %r but %d of %d goal blocks are complete" \
                    % (rec_id, state, sum(ok), len(ok))
            elif key == "progress_measurement":
                assert _has_digit(body) == measurable, \
                    "%s: progress_measurement %r does not match its text" % (rec_id, state)
            elif key == "services":
                # ⚠︎ THE LOCATION TEST NAMES THE PLACES RATHER THAN LOOKING FOR " in ". The
                # vague-location defect reads "in the appropriate setting", which contains " in "
                # and is not a location -- a substring test passed it and would have shipped a
                # `present_not_measurable` label over a line this check called complete.
                ok = [("per week" in ln and "minutes" in ln
                       and any(("in %s" % p) in ln for p in SERVICE_PLACES))
                      for ln in body.splitlines() if ln.strip()]
                assert all(ok) == measurable, \
                    "%s: services %r but %d of %d lines carry all three" \
                    % (rec_id, state, sum(ok), len(ok))
            elif key == "accommodations":
                ok = [" -- " in ln for ln in body.splitlines() if ln.strip()]
                assert all(ok) == measurable, \
                    "%s: accommodations %r but %d of %d lines name a setting" \
                    % (rec_id, state, sum(ok), len(ok))
            elif key == "participation_rationale":
                assert _has_digit(body) == measurable, \
                    "%s: participation_rationale %r does not match its text" % (rec_id, state)
            elif key == "transition":
                assert "Post-school goal:" in body, "%s: transition has no post-school goal" % rec_id
                assert ("Steps this plan year:" in body) == measurable, \
                    "%s: transition %r does not match its text" % (rec_id, state)

        want = RB.required_outcome({k: gold[k] for k in RB.COMPONENTS}, gold["pupil_age"])
        assert gold["plan_outcome"] == want, \
            "%s: gold outcome %r disagrees with its own rulebook lookup (%r)" \
            % (rec_id, gold["plan_outcome"], want)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_RECORDS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rec_id, text, _gold, _bucket in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rec_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rec_id, _text, gold, _bucket in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    total = sum(len(t.encode("utf-8")) for _i, t, _g, _b in rows)
    print("plans: %d   bytes: %d" % (len(rows), total))
    print("outcomes: %s" % "  ".join("%s=%d" % (k, v) for k, v in sorted(stats["outcomes"].items())))
    print("buckets:  %s" % "  ".join("%s=%d" % (k, v) for k, v in stats["buckets"].items()))
    print("%d component cells are PRESENT AND NOT MEASURABLE -- the state this kit exists for"
          % stats["unmeasurable_cells"])
    print("%d component cells are ABSENT (%d of them written as a placeholder rather than omitted)"
          % (stats["absent_cells"], stats["placeholders"]))
    print("%d component cells are NOT REQUIRED -- the pupil's stated age is below %d"
          % (stats["not_required"], RB.TRANSITION_AGE))
    print("%d plan(s) carry a checklist claiming every component is present while the rulebook "
          "finds a defect" % stats["checklist_trap"])
    print("%d plan(s) (%.0f%%) carry a case manager note whose TONE contradicts the outcome"
          % (stats["ambiguous"], 100.0 * stats["ambiguous"] / len(rows)))
    print("%d unmeasurable-goals plan(s) put the defective goal somewhere other than first"
          % stats["goal_defect_not_first"])
    print("%d plan(s) state no age and are still NOT undetermined -- 'no age' is not a shortcut"
          % stats["no_age_not_undetermined"])
    print("%d plan(s) are not complete AND already in effect -- the pure-code worklist flag"
          % stats["on_worklist"])
    print("internal consistency check: PASSED (every gold state is readable off its own plan, "
          "every outcome is that plan's own rulebook lookup)")


if __name__ == "__main__":
    main()
