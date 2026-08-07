"""Score materiality verdicts by AGREEMENT, not by a gold match. Pure arithmetic — no judge.

⚑ WHY AGREEMENT, AND NOT `==` AGAINST A LABEL — read this before the confusion matrix below.
docs-route can score `==` because the Office of the Federal Register assigns every document a
type before the kit exists; that is a gold answer nobody here wrote. No publisher assigns a
"material / editorial" grade to its own corrections — see materiality.py — so there is nothing
this kit's model output can be `==` against. Building a gold set by writing our own verdicts and
grading the model against them would be publishing our guess as the kit's finding.

⚑ WHAT IS MEASURABLE INSTEAD: DO TWO INDEPENDENT READERS OF THE SAME CHANGE AGREE. Run the same
prompt through two different models — the kit standard already requires it — and where they land
on the same verdict is real signal even with no ground truth behind it: two independent judges
agreeing is evidence, the same logic inter-rater reliability runs on outside AI. Where they
DISAGREE is the actionable output of this kit: not "the model was wrong", but "this is exactly
the kind of change that needs a person," which is the same third-outcome discipline docs-route
built around its confidence floor, arrived at from the opposite direction — there, the model
itself signals uncertainty; here, disagreement between two models is what signals it.

⚠︎ AND THAT IS THE HONEST LIMIT, STATED RATHER THAN HIDDEN: two models agreeing does not mean they
are both right, only that they are not obviously confused by this change. `Eval.could_not_verify`
on the published kit says so.
"""
import json
import os

from src import materiality as MT

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pair_ids():
    path = os.path.join(HERE, "data", "pairs.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line)["pair_id"] for line in f if line.strip()]


def outcomes(records):
    """Count of each outcome across one run — flagged / abstained / escalated / offmenu /
    unparsed / no_change. Pure code, needs no comparison run to compute."""
    from src import redline as RL
    counts = {}
    for rec in records.values():
        o = RL.outcome(rec)
        counts[o] = counts.get(o, 0) + 1
    return counts


def agree(records_a, records_b, name_a, name_b):
    """records_a/b: {pair_id: record} from two separate runs (two models, or a model and the
    regex baseline). Only pairs BOTH runs reached a verdict on ("ok" or "abstained", never
    "unparsed"/"offmenu"/"no_change" — a format failure agreeing with anything is not agreement)
    count toward the rate.
    """
    ids = sorted(set(records_a) & set(records_b))
    comparable, agreed, disagreements = [], 0, []
    for pid in ids:
        ra, rb = records_a[pid], records_b[pid]
        va = ra.get("materiality") if ra.get("state") == "ok" else (
            MT.ABSTAIN if ra.get("state") == "abstained" else None)
        vb = rb.get("materiality") if rb.get("state") == "ok" else (
            MT.ABSTAIN if rb.get("state") == "abstained" else None)
        if va is None or vb is None:
            continue
        comparable.append(pid)
        if va == vb:
            agreed += 1
        else:
            disagreements.append({"pair_id": pid, name_a: va, name_b: vb,
                                  "span_v2": ((ra.get("span") or {}).get("v2") or "")[:160]})
    return {
        "a": name_a, "b": name_b,
        "pairs_total": len(ids),
        "pairs_comparable": len(comparable),
        "agreed": agreed,
        "agreement_rate": round(agreed / len(comparable), 4) if comparable else None,
        "disagreements": disagreements,
    }


def agreement_text(a):
    lines = ["%s vs %s" % (a["a"], a["b"]),
            "  comparable pairs   %d of %d" % (a["pairs_comparable"], a["pairs_total"]),
            "  agreed             %d" % a["agreed"],
            "  agreement rate     %s"
            % ("%.1f%%" % (100 * a["agreement_rate"]) if a["agreement_rate"] is not None else "n/d")]
    if a["disagreements"]:
        lines.append("  disagreements (need a person):")
        for d in a["disagreements"][:5]:
            lines.append("    %-24s %-10s %-10s %s" % (d["pair_id"], d[a["a"]], d[a["b"]],
                                                       d["span_v2"]))
    return "\n".join(lines)
