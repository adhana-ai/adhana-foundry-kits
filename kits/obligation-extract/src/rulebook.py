"""THE WORKSHEET RULEBOOK, loaded from data/rulebook.json. Pure code, no model, no network.

⚑ THE RULEBOOK IS DATA, NOT CODE, AND THAT IS THE POINT OF THIS KIT. What the kit does is turn
three STATED FACTS about a contract line into two worksheet calls, so the rule that turns them has
to be a thing a reader can open, read, disagree with and replace -- not a dict buried in a Python
module. `data/rulebook.json` is that file. Everything below is the arithmetic that reads it.

⚠︎ THE SHIPPED RULEBOOK IS ILLUSTRATIVE AND IS NOT AN AUTHORITY. It was written for this kit. It
reproduces no accounting standard, no standard-setter's guidance, no audit firm's manual and no
company's own revenue policy, and it names none of them. See data/SOURCES.md, and the same sentence
is printed on the kit's own UI where a reader actually reads the answer.

⚠︎ AND WHAT COMES OUT IS A REVIEWER'S WORKSHEET. Not an accounting conclusion, not an allocation,
not a schedule and not a journal entry. Nothing in this kit determines anything: it reads what the
paperwork says, applies the shipped rulebook, and NAMES THE LINES THE PAPERWORK DOES NOT SETTLE.
The controller determines the obligations, the allocation and the timing.

⚑ TWO CALLS PER LINE, AND THEY ARE INDEPENDENT:

  SEPARATION -- distinct / bundled / not_determined. Four steps, in order, stopping at the first
  that fires. The one that gets skipped is step 4: a line with a fee of its own and NOTHING said
  about whether the customer could take it alone is `not_determined`, because a price is what the
  customer is charged and not a statement about separability.

  PATTERN -- over_time / point_in_time / not_determined. Asked of every line independently of its
  separation call: a bundled line still either has a stated window, a stated event, or neither.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULEBOOK_PATH = os.path.join(HERE, "data", "rulebook.json")

CHARGES = ("separate_fee", "no_separate_charge", "not_stated")
DEPENDENCIES = ("required_first", "separately_available", "silent")
TIMINGS = ("period", "event", "silent")

SEPARATIONS = ("distinct", "bundled", "not_determined")
PATTERNS = ("over_time", "point_in_time", "not_determined")


def load(path=RULEBOOK_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


R = load()

ITEM_TYPES = tuple(sorted(R["item_types"]))


def separation(charge, dependency):
    """THE SEPARATION RULE, in one place, returning one of SEPARATIONS or None.

    ⚑ ONE DEFINITION, THREE READERS -- tools/build_corpus.py writes gold with it, src/prompt.py
    states it to the model in words, and evals/judge.py re-runs it over the model's OWN extracted
    facts for the no-gold consistency diagnostic. They cannot drift about what a call means.

    None is returned when a fact is missing or outside the rulebook's vocabulary. That is a real
    answer and it is deliberately NOT folded into `not_determined`: `not_determined` is a finding
    ABOUT THE CONTRACT, and None is a finding about the reply.
    """
    if charge not in CHARGES or dependency not in DEPENDENCIES:
        return None
    if dependency == "required_first":
        return "bundled"
    if dependency == "separately_available":
        return "distinct"
    if charge == "no_separate_charge":
        return "bundled"
    return "not_determined"


def pattern(timing):
    """THE PATTERN RULE. One fact in, one of PATTERNS out, or None for a fact outside the
    vocabulary. Independent of the separation call, by design."""
    if timing not in TIMINGS:
        return None
    if timing == "period":
        return "over_time"
    if timing == "event":
        return "point_in_time"
    return "not_determined"


def decide(charge, dependency, timing):
    """Both calls plus their reasoning. {separation, pattern, separation_reason, pattern_reason}.

    The reason strings are what make a worksheet row auditable by the person who has to take it to
    the deal desk, and they are derived here rather than taken from the model -- a model-authored
    justification for a code-computed call is a caption, not evidence.
    """
    sep = separation(charge, dependency)
    pat = pattern(timing)
    out = {"separation": sep, "pattern": pat,
           "separation_reason": None, "pattern_reason": None}

    if sep is None:
        out["separation_reason"] = ("The reply did not carry a charge and dependency this rulebook "
                                    "recognises, so no separation call can be made from it.")
    elif dependency == "required_first":
        out["separation_reason"] = ("The contract states this line must be completed, accepted or "
                                    "supplied before another ordered item can be used, so the "
                                    "worksheet records it alongside that item.")
    elif dependency == "separately_available":
        out["separation_reason"] = ("The contract states the customer may take, cancel, defer or "
                                    "obtain this line on its own, which settles it whatever the "
                                    "fee column says.")
    elif charge == "no_separate_charge":
        out["separation_reason"] = ("The order form gives this line no price of its own and the "
                                    "contract says nothing about taking it separately, so this "
                                    "rulebook records it with the line it rides on.")
    else:
        out["separation_reason"] = ("The contract says nothing about whether this line can be "
                                    "taken on its own. A fee of its own is a price, not a "
                                    "statement about separability, so the paperwork does not "
                                    "settle this and the worksheet says so.")

    if pat is None:
        out["pattern_reason"] = ("The reply did not carry a timing statement this rulebook "
                                 "recognises, so no pattern call can be made from it.")
    elif timing == "period":
        out["pattern_reason"] = "The contract states a period over which this line is supplied."
    elif timing == "event":
        out["pattern_reason"] = ("The contract states a single completion, delivery, issue or "
                                 "acceptance event for this line.")
    else:
        out["pattern_reason"] = ("The contract states neither a period nor a single event for "
                                 "this line, so the paperwork does not settle the pattern.")
    return out


def rulebook_block(r=None):
    """The rulebook, rendered for the prompt out of data/rulebook.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of these steps inside src/prompt.py is a copy
    that drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold labels disagree about the same rule, silently, and the
    disagreement would score as a model failure.
    """
    r = r or R
    lines = ["WORKSHEET RULEBOOK (the authority for `separation` and `pattern`; this is an "
             "ILLUSTRATIVE rulebook written for this kit, and it reproduces no accounting "
             "standard)", "",
             "WHAT COUNTS AS A LINE ON THE WORKSHEET"]
    for s in r["what_is_an_obligation_here"]:
        lines.append("  - %s" % s)
    lines += ["", "THE THREE STATED FACTS, read off the contract"]
    for key in ("charge", "dependency", "timing"):
        lines.append("  %s:" % key)
        for value, meaning in r["stated_facts"][key].items():
            lines.append("    %-22s %s" % (value, meaning))
    lines += ["", "SEPARATION -- work through IN ORDER, stop at the first that fires"]
    for s in r["separation_rule"]:
        lines.append("  %s" % s)
    lines += ["", "DELIVERY PATTERN"]
    for s in r["pattern_rule"]:
        lines.append("  %s" % s)
    lines += ["", "WHY `not_determined` IS A REAL ANSWER", "  " + r["why_not_determined_is_first_class"]]
    return "\n".join(lines)
