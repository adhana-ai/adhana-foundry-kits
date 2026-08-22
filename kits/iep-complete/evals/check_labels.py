"""Check the gold set before anything is scored against it. Run this before spending money.

Usage:  python -m evals.check_labels
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extract as EX                          # noqa: E402
from src import rulebook as RB                         # noqa: E402
from src import select as SEL                          # noqa: E402
from src.extract import compute as _compute            # noqa: E402
from src.extract import correct_outcome as _outcome_of  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")

# ⚠︎ ONE NULLABLE FIELD, AND ITS NULL IS A STATED FACT RATHER THAN A CONVENIENCE.
#   pupil_age is null exactly where the plan says the age is NOT STATED. It is deliberately NOT
#   two-way with the `undetermined` outcome: three plans in this corpus state no age and are still
#   answerable, because a component they DO carry is already defective. A corpus where "no age"
#   always meant "undetermined" would teach a one-line shortcut and grade it as reading.
NULLABLE = {"pupil_age"}

FLOORS = {
    "unmeasurable_cells": 25,
    "not_measurable_plans": 15,
    "checklist_trap": 12,
    "transition_not_required": 4,
    "components_missing_plans": 10,
    "goal_defect_not_first": 3,
    "no_age_still_answerable": 3,
    "per_component_state": 2,
}

problems = []


def bad(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def _section_body(text, name):
    head = "%s\n%s" % (name, "-" * max(len(name), 3))
    at = text.find(head)
    if at < 0:
        return None
    rest = text[at + len(head):].lstrip("\n")
    cut = rest.find("\n\n")
    return (rest if cut < 0 else rest[:cut]).strip()


def _goal_blocks(body):
    """The goal blocks in an Annual Goals body, in order, as raw text."""
    out, cur = [], None
    for line in (body or "").splitlines():
        if line.startswith("Goal "):
            if cur is not None:
                out.append("\n".join(cur))
            cur = [line]
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        out.append("\n".join(cur))
    return out


def _goal_is_measurable(block):
    has = all(("%s:" % e) in block for e in ("Baseline", "Criterion", "Measured by"))
    quantified = all(any(ch.isdigit() for ch in line) for line in block.splitlines()
                     if line.strip().startswith(("Baseline:", "Criterion:")))
    return has and quantified


def main():
    fields = EX.load_fields()
    docs = set(EX.documents())
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    by_id = {r["plan_id_rec"]: r for r in rows}
    text_of = {d: EX.load_doc(d) for d in docs}

    if len(by_id) != len(rows):
        bad("duplicate plan_id_rec in gold.jsonl (%d rows, %d ids)" % (len(rows), len(by_id)))

    missing = docs - set(by_id)
    if missing:
        bad("%d plan(s) have no gold row: %s" % (len(missing), sorted(missing)[:5]))
    orphan = set(by_id) - docs
    if orphan:
        bad("%d gold row(s) have no plan: %s" % (len(orphan), sorted(orphan)[:5]))

    for f in fields:
        if f.get("values"):
            for plan_id, r in by_id.items():
                v = r.get(f["name"])
                if v not in (None, "") and v not in f["values"]:
                    bad("%s: %s=%r is not one of %s" % (plan_id, f["name"], v, f["values"]))

    for f in fields:
        if f["name"] in NULLABLE:
            continue
        n_null = sum(1 for r in by_id.values() if r.get(f["name"]) is None)
        if n_null:
            bad("%s is null in %d gold row(s) -- only %s is nullable in this corpus"
                % (f["name"], n_null, " and ".join(sorted(NULLABLE))))

    # ⚑ GOLD MUST AGREE WITH ITS OWN RULEBOOK LOOKUP. This is the check that makes the whole kit
    # honest: `plan_outcome` is not a second opinion about the checklist, it is the lookup.
    disagree = [p for p, r in sorted(by_id.items()) if _outcome_of(r) != r.get("plan_outcome")]
    if disagree:
        bad("%d gold row(s) label an outcome their own states do not produce: %s"
            % (len(disagree), disagree[:5]))

    # ⚑ THE CONDITIONAL COMPONENT, BOTH WAYS. `not_required` is awarded if and only if the plan
    # states an age below the threshold -- never on a plan with no age, which is the distinction
    # between "the rulebook does not ask for this" and "nobody can tell whether it does".
    wrong_nr = [p for p, r in by_id.items()
                if (r.get("transition") == "not_required")
                != (r.get("pupil_age") is not None and r["pupil_age"] < RB.TRANSITION_AGE)]
    if wrong_nr:
        bad("%d row(s) where transition=='not_required' and the stated age disagree: %s"
            % (len(wrong_nr), sorted(wrong_nr)[:5]))

    # ⚑ AN UNDETERMINED OUTCOME ALWAYS MEANS THE AGE IS MISSING -- AND THE CONVERSE MUST BE FALSE.
    undet_with_age = [p for p, r in by_id.items()
                      if r["plan_outcome"] == "undetermined" and r["pupil_age"] is not None]
    if undet_with_age:
        bad("%d row(s) are undetermined while stating an age: %s"
            % (len(undet_with_age), sorted(undet_with_age)[:5]))
    answerable = [p for p, r in by_id.items()
                  if r["pupil_age"] is None and r["plan_outcome"] != "undetermined"]
    if len(answerable) < FLOORS["no_age_still_answerable"]:
        bad("only %d row(s) state no age and are still answerable -- fewer than %d and 'no age "
            "means undetermined' is a one-line shortcut this corpus would reward"
            % (len(answerable), FLOORS["no_age_still_answerable"]))
    else:
        print("  info  %d row(s) state no age and are still ANSWERABLE -- 'no age' is not a "
              "shortcut" % len(answerable))

    # ⚑ THE FOUR HARD CASES, ASSERTED RATHER THAN TRUSTED. Each is a reading a checkbox review gets
    # wrong, and each has to be MEASURED rather than anecdotal, so each has a floor.

    # (1) present, and not measurable -- the state this kit exists for.
    unmeasurable = [(p, k) for p, r in by_id.items() for k in RB.COMPONENTS
                    if r[k] == "present_not_measurable"]
    if len(unmeasurable) < FLOORS["unmeasurable_cells"]:
        bad("only %d component cell(s) are present-and-not-measurable -- the state this kit exists "
            "for needs at least %d to be measured rather than anecdotal"
            % (len(unmeasurable), FLOORS["unmeasurable_cells"]))
    else:
        print("  info  %d component cell(s) are PRESENT AND NOT MEASURABLE across %d plan(s)"
              % (len(unmeasurable), len({p for p, _k in unmeasurable})))
    n_nm = sum(1 for r in by_id.values() if r["plan_outcome"] == "not_measurable")
    if n_nm < FLOORS["not_measurable_plans"]:
        bad("only %d plan(s) have EVERY required component present and at least one of them "
            "unmeasurable -- the case a checkbox review cannot see needs at least %d"
            % (n_nm, FLOORS["not_measurable_plans"]))

    # Every unmeasurable component must actually be readable as unmeasurable off its own text.
    for p, k in unmeasurable:
        body = _section_body(text_of[p], RB.SECTION_BY_KEY[k])
        if not body:
            bad("%s: %s is present_not_measurable and its section has no body" % (p, k))
        elif body.strip().lower().rstrip(".") in {q.lower() for q in RB.M["placeholder_bodies"]}:
            bad("%s: %s is present_not_measurable and its body is a placeholder" % (p, k))

    # (2) the checklist claims everything is present, and the rulebook finds a defect.
    trap = [p for p, r in by_id.items()
            if r["checklist_claim"] == "all_present" and r["plan_outcome"] != "complete"]
    if len(trap) < FLOORS["checklist_trap"]:
        bad("only %d plan(s) carry a checklist claiming every component is present while the "
            "rulebook finds a defect -- the checkbox-is-not-evidence trap needs at least %d"
            % (len(trap), FLOORS["checklist_trap"]))
    else:
        print("  info  %d plan(s) carry a checklist claiming everything is present while the "
              "rulebook finds a defect" % len(trap))

    # ⚠︎ AND THE CLAIM MUST NOT CORRELATE WITH THE ANSWER IN EITHER DIRECTION. If every sound plan
    # carried the same claim, "copy the checklist" would be a perfect one-line shortcut and a run
    # that took it would score as a run that read the plan. Each of the three values has to appear
    # on a sound plan AND on a defective one.
    for value in ("all_present", "items_outstanding", "not_completed"):
        on_sound = sum(1 for r in by_id.values()
                       if r["checklist_claim"] == value and r["plan_outcome"] == "complete")
        on_def = sum(1 for r in by_id.values()
                     if r["checklist_claim"] == value and r["plan_outcome"] != "complete")
        if not on_sound or not on_def:
            bad("checklist_claim=%r appears on %d sound and %d defective plan(s) -- a claim that "
                "occurs on only one kind of plan makes 'copy the checklist' a correct shortcut"
                % (value, on_sound, on_def))

    # (3) transition is age-conditional -- and the SAME plan must read as incomplete for an older
    #     pupil. Asserted by substituting the state the same DOCUMENT would earn above the
    #     threshold (`absent`, since these plans carry no transition section) rather than by
    #     re-labelling the age alone, which would only prove the contradiction branch fires.
    nr = [p for p, r in by_id.items()
          if r["transition"] == "not_required" and r["plan_outcome"] == "complete"]
    for p in nr:
        r = by_id[p]
        states = {k: r[k] for k in RB.COMPONENTS}
        states["transition"] = "absent"
        older = RB.required_outcome(states, RB.TRANSITION_AGE + 2)
        if older != "components_missing":
            bad("%s: has no transition section and is complete below the threshold, but for an "
                "older pupil the same document reads %r rather than components_missing" % (p, older))
    if len(nr) < FLOORS["transition_not_required"]:
        bad("only %d plan(s) are COMPLETE with no transition section because the pupil is below "
            "the threshold -- the false-defect case needs at least %d"
            % (len(nr), FLOORS["transition_not_required"]))
    else:
        print("  info  %d plan(s) are complete WITHOUT a transition section, because the stated "
              "age is below %d -- a checkbox review raises a false defect on every one"
              % (len(nr), RB.TRANSITION_AGE))

    # (4) the easy half: a component that is simply not there.
    n_cm = sum(1 for r in by_id.values() if r["plan_outcome"] == "components_missing")
    if n_cm < FLOORS["components_missing_plans"]:
        bad("only %d plan(s) are missing a required component outright -- the easy half of this "
            "kit's job needs at least %d, or the separability claim is untested in one direction"
            % (n_cm, FLOORS["components_missing_plans"]))
    else:
        print("  info  %d plan(s) are missing a required component outright -- the half a checkbox "
              "review does catch" % n_cm)

    # ⚑ THE DEFECTIVE GOAL IS NOT ALWAYS THE FIRST ONE, READ OFF THE SHIPPED TEXT. A corpus that
    # always broke goal 1 would reward a reader that checks one block and stops.
    not_first = []
    for p, r in sorted(by_id.items()):
        if r["annual_goals"] != "present_not_measurable":
            continue
        blocks = _goal_blocks(_section_body(text_of[p], RB.SECTION_BY_KEY["annual_goals"]))
        okay = [_goal_is_measurable(b) for b in blocks]
        if all(okay):
            bad("%s: annual_goals is present_not_measurable and every goal block parses as "
                "measurable" % p)
        elif okay and okay[0]:
            not_first.append(p)
    if len(not_first) < FLOORS["goal_defect_not_first"]:
        bad("only %d unmeasurable-goals plan(s) put the defective goal somewhere other than first "
            "-- fewer than %d and a reader that checks goal 1 and stops scores as one that read "
            "the section" % (len(not_first), FLOORS["goal_defect_not_first"]))
    else:
        print("  info  %d unmeasurable-goals plan(s) open with a SOUND goal and break a later one"
              % len(not_first))

    # ⚑ NO GRADER MAY BE DEGENERATE. An outcome class with no members, a component state that never
    # occurs, or a worklist flag that is constant would all score perfectly and mean nothing.
    counts = {}
    for r in by_id.values():
        counts[r["plan_outcome"]] = counts.get(r["plan_outcome"], 0) + 1
    for v in RB.OUTCOMES:
        if not counts.get(v):
            bad("gold has no %r rows -- the four-way outcome grader would be degenerate" % v)
    print("  info  outcomes: %s" % "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in RB.OUTCOMES))

    for k in RB.COMPONENTS:
        seen = {}
        for r in by_id.values():
            seen[r[k]] = seen.get(r[k], 0) + 1
        for state in ("absent", "present_not_measurable"):
            if seen.get(state, 0) < FLOORS["per_component_state"]:
                bad("component %s is %r on only %d plan(s) -- a state with fewer than %d instances "
                    "is an anecdote in a denominator" % (k, state, seen.get(state, 0),
                                                         FLOORS["per_component_state"]))

    n_needs = sum(1 for r in by_id.values() if r["plan_outcome"] != "complete")
    if n_needs in (0, len(by_id)):
        bad("every plan has the same needs-work answer (%d of %d) -- the worklist matrix this kit "
            "exists to publish would be degenerate" % (n_needs, len(by_id)))
    else:
        print("  info  %d of %d plans need somebody to open them" % (n_needs, len(by_id)))

    n_flag = sum(1 for r in by_id.values()
                 if _compute({"plan_outcome": r.get("plan_outcome"),
                              "plan_status": r.get("plan_status")}))
    if n_flag == 0 or n_flag == len(by_id):
        bad("the pure-code worklist flag is constant across gold (%d of %d) -- it would score "
            "perfectly and mean nothing" % (n_flag, len(by_id)))
    else:
        print("  info  %d of %d plans are not complete AND already in effect -- the worklist flag"
              % (n_flag, len(by_id)))

    # ⚑ THE TWO SECTIONS SELECTION DROPS MUST EXIST ON EVERY PLAN AND BE MAPPED BY NOTHING. The
    # saving is a claim on the kit's own pages; this is the check that makes it a fact. It is also
    # the check that would catch somebody mapping a field to one of them later.
    mapped = {s for names in SEL.SECTION_HINTS.values() for s in names}
    for name in SEL.NEVER_SENT:
        if name in mapped:
            bad("%r is listed as never sent and is mapped by a field in SECTION_HINTS" % name)
        absent_on = [p for p in sorted(docs) if _section_body(text_of[p], name) is None]
        if absent_on:
            bad("%r is missing from %d plan(s): %s" % (name, len(absent_on), absent_on[:5]))
    print("  info  %s are mapped by no field and never leave the machine"
          % " and ".join(repr(n) for n in SEL.NEVER_SENT))

    # ⚑ THE FREE FLOOR'S OWN PROPERTY, ASSERTED BEFORE ANYTHING MAY SPEND. It is published as a
    # checkbox review that structurally CANNOT reach two of the four states; a floor that quietly
    # learned to reach one of them would make every separability figure on this kit's pages a
    # different claim. Written in from the start, on the lesson a sibling kit paid for live when its
    # own floor's keyword list turned out to fire on the register it was written to ignore.
    try:
        from evals import baseline as B
    except ImportError as exc:
        print("  info  floor check skipped: %s" % exc)
    else:
        reached = set()
        for p in sorted(docs):
            r = B.extract(text_of[p], fields)
            for k in RB.COMPONENTS:
                reached.add(r["fields"][k]["value"])
        forbidden = reached & {"present_not_measurable", "not_required"}
        if forbidden:
            bad("the free floor returned %s -- it is published as a checkbox review that cannot "
                "reach those states, and every separability figure on this kit's pages assumes it"
                % sorted(forbidden))
        else:
            print("  info  the free floor reaches only %s, as published" % sorted(reached))

    # ⚑ THE TWO NOTE REGISTERS MUST BE DISTINGUISHABLE TO A READER. The case manager's note is a
    # decoy for the MODEL rather than an input to the floor, so nothing scores it -- which is
    # exactly why an unchecked overlap between the two lists would go unnoticed and quietly weaken
    # the planted ambiguity to nothing.
    try:
        from tools.build_corpus import CALM_NOTES, WORRIED_NOTES
    except ImportError as exc:
        print("  info  register check skipped: %s" % exc)
    else:
        used = {r["case_manager_note"] for r in by_id.values()}
        unknown = used - set(CALM_NOTES) - set(WORRIED_NOTES)
        if unknown:
            bad("gold carries %d note(s) from neither register: %s" % (len(unknown),
                                                                       sorted(unknown)[:2]))
        overlap = set(CALM_NOTES) & set(WORRIED_NOTES)
        if overlap:
            bad("%d note template(s) appear in both registers: %s" % (len(overlap),
                                                                      sorted(overlap)))
        worried_on_sound = sum(1 for r in by_id.values()
                               if r["plan_outcome"] == "complete"
                               and r["case_manager_note"] in WORRIED_NOTES)
        calm_on_defective = sum(1 for r in by_id.values()
                                if r["plan_outcome"] != "complete"
                                and r["case_manager_note"] in CALM_NOTES)
        if worried_on_sound < 3 or calm_on_defective < 3:
            bad("the planted note ambiguity runs in one direction only (%d worried notes on sound "
                "plans, %d calm notes on defective ones) -- both need at least 3, or the decoy "
                "only ever tests one kind of misreading"
                % (worried_on_sound, calm_on_defective))
        else:
            print("  info  %d worried note(s) sit on a SOUND plan and %d calm note(s) on a "
                  "DEFECTIVE one -- the decoy runs both ways"
                  % (worried_on_sound, calm_on_defective))

    if problems:
        print("\nCHECK LABELS: %d PROBLEM(S)" % len(problems))
        raise SystemExit(1)
    print("check_labels: %d plan(s), %d field(s), gold consistent with the corpus and with its own "
          "rulebook lookup" % (len(docs), len(fields)))


if __name__ == "__main__":
    main()
