"""Score one answer against the dataset's own dialogue state. Pure code, no model, no cost.

⚑ THERE IS NO JUDGE IN THIS FILE AND THAT IS THE POINT OF THE KIT. Every other kit here that grades
open text needs a model to grade it, which costs money and needs its own validation before its
verdicts mean anything. Here the gold is published: SGD records, for every turn, exactly which
slots have been established and with what values. So the verdict is `==` against ground truth
somebody else committed to in advance, and running the eval is free.

⚠︎ THE COMPARISON IS DELIBERATELY LENIENT ON SURFACE FORM AND STRICT ON EVERYTHING ELSE. Gold
carries a LIST of accepted strings per slot ("checking" may appear as "checking account"), so a
match is membership in that list after casefolding and whitespace collapse — not string equality
against the first entry, which would mark correct answers wrong for punctuation. It does NOT
normalise numbers, expand abbreviations or accept substrings: "Peter" is not "Peter Kim", and
treating it as one would hide the exact failure this kit exists to measure.

The four outcomes per required fact, and why none of them may be folded into another:

    correct    stated, and the value is one gold accepts
    wrong      stated, and it is not — the expensive one, because the checklist reads as full
    missed     gold has it, the answer does not — costs one more question
    open       gold does not have it either, and the answer agrees. NOT a win to brag about and
               not a failure: at this point in the conversation nobody has said it yet.

`correct + wrong + missed + open == len(required)` on every case, always. The identity is asserted,
not assumed — see `score()`.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from src import slots                                                        # noqa: E402


def _norm(v):
    return " ".join(str(v).split()).casefold()


def _accepts(gold_values, answer_value):
    """Gold is a list of surface strings the dataset accepts for that slot."""
    return _norm(answer_value) in {_norm(g) for g in gold_values}


def score(case, answer):
    """One case -> a dict of per-fact outcomes plus the turn decision.

    `answer` is prompt.parse() output, or None when the model did not return the shape. A None
    answer is UNPARSED and is counted apart from every other outcome: it is not "collected
    nothing", because collecting nothing is sometimes exactly right.
    """
    need = slots.required(case["intent"])
    gold = case["gold_slots"]

    if answer is None:
        return {"case_id": case["case_id"], "unparsed": True,
                "correct": 0, "wrong": 0, "missed": 0, "open": 0,
                "decision": None, "decision_ok": False, "gold_complete": case["gold_complete"]}

    got = answer["collected"]
    out = {"correct": 0, "wrong": 0, "missed": 0, "open": 0}
    facts = []
    for s in need:
        if s in got and s in gold:
            k = "correct" if _accepts(gold[s], got[s]) else "wrong"
        elif s in got:
            # The model reported a fact the conversation had not established yet. This is the
            # invented value, and it is `wrong` rather than a fifth category: downstream cannot
            # tell the difference and neither can the person whose money moves.
            k = "wrong"
        elif s in gold:
            k = "missed"
        else:
            k = "open"
        out[k] += 1
        facts.append({"slot": s, "outcome": k,
                      "answer": got.get(s), "gold": gold.get(s)})

    assert sum(out.values()) == len(need), "outcomes must account for every required fact"

    # ⚑ THE DECISION IS DERIVED, NOT ASKED FOR. `missing()` is a set difference over what the model
    # said it collected. A model cannot claim completeness its own extraction does not support.
    decision = "stop" if not slots.missing(case["intent"], got) else "ask"
    truth = "stop" if case["gold_complete"] else "ask"

    return {"case_id": case["case_id"], "unparsed": False, "facts": facts,
            "decision": decision, "truth": truth, "decision_ok": decision == truth,
            "stopped_early": decision == "stop" and truth == "ask",
            "kept_asking": decision == "ask" and truth == "stop",
            "gold_complete": case["gold_complete"], **out}


def totals(rows):
    """Roll per-case scores up to the numbers a report may publish.

    ⚠︎ `stopped_early` IS REPORTED ON ITS OWN AND NEVER INSIDE A DECISION ACCURACY. It is the
    failure this use case exists to measure and it is not symmetric with its opposite: asking one
    question too many annoys somebody, stopping one too soon hands a downstream process a record it
    believes is complete. An accuracy figure averages the two into a number that hides the one that
    matters.
    """
    n = len(rows)
    graded = [r for r in rows if not r["unparsed"]]
    facts = sum(r["correct"] + r["wrong"] + r["missed"] + r["open"] for r in graded)
    return {
        "cases": n,
        "unparsed": n - len(graded),
        "facts_judged": facts,
        "correct": sum(r["correct"] for r in graded),
        "wrong": sum(r["wrong"] for r in graded),
        "missed": sum(r["missed"] for r in graded),
        "open": sum(r["open"] for r in graded),
        "decision_ok": sum(1 for r in graded if r["decision_ok"]),
        "stopped_early": sum(1 for r in graded if r.get("stopped_early")),
        "kept_asking": sum(1 for r in graded if r.get("kept_asking")),
        # An unparsed reply is not a correct decision and is not folded into the denominator's
        # favour: the rate is over EVERY case, so a model that fails to answer is not rewarded.
        "decision_rate": (sum(1 for r in graded if r["decision_ok"]) / n) if n else 0.0,
    }
