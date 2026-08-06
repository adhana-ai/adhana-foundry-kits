"""Score a set of routing decisions against the gold labels. Pure arithmetic — no model, no judge.

⚑ THIS IS THE ONLY FILE IN THE KIT THAT OPENS data/gold.jsonl, and that is enforced by convention
rather than by code: everything else reads data/corpus/, which contains no labels. The separation
was made at the corpus boundary in tools/build_corpus.py for exactly this reason.

⚑ ACCURACY IS REPORTED LAST, NOT FIRST. A single accuracy number over a router hides the two facts
that decide whether it can be deployed: WHICH class it confuses with which, and how much traffic
it hands to a person. A 90% router that escalates 40% of its input is not a 90% router; it is a
60% router with a queue of homework. So the confusion matrix and the escalation rate come first
and the headline number comes after them.

⚠︎ AND THE TWO ERRORS ARE NOT WORTH THE SAME — see taxonomy.py. Filing a proposed rule as a notice
forfeits a comment window and nobody finds out; filing a notice as a rule wastes an hour and
somebody complains immediately. This scorer does NOT weight them, because a weight is a business
input and inventing one here would publish my guess as the kit's finding. What it does instead is
print the off-diagonal cells separately so the expensive direction is visible and the reader can
apply their own weight.
"""
import json
import os

from src import taxonomy as TX

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def load_gold():
    with open(GOLD, encoding="utf-8") as f:
        return {json.loads(line)["doc_id"]: json.loads(line)["queue"]
                for line in f if line.strip()}


def confusion(pairs):
    """pairs: [(gold_queue, routed_queue_or_None)]. Returns the matrix plus the escalation column.

    `None` is a real column, not a missing value. A router that declines is doing something, and
    a matrix that dropped those rows would report accuracy over a subset the router chose for
    itself — which is the single easiest way to publish a flattering number by accident.
    """
    labels = TX.labels()
    m = {g: {p: 0 for p in labels + [None]} for g in labels}
    for gold, pred in pairs:
        if gold in m:
            m[gold][pred if pred in labels else None] += 1
    return m


def per_class(m):
    """Precision, recall and F1 per queue, computed over ROUTED decisions only, with the count of
    what was withheld printed beside them so the two are never read apart."""
    labels = TX.labels()
    out = {}
    for q in labels:
        tp = m[q][q]
        fn = sum(m[q][p] for p in labels if p != q)
        withheld = m[q][None]
        fp = sum(m[g][q] for g in labels if g != q)
        prec = tp / (tp + fp) if (tp + fp) else None
        # ⚠︎ RECALL COUNTS WITHHELD DOCUMENTS AS MISSES, because for the queue they belonged to
        # they ARE misses: nobody actioned them. Excluding them would let a router raise its recall
        # by refusing to answer, which is the opposite of what recall is for.
        rec = tp / (tp + fn + withheld) if (tp + fn + withheld) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None
        out[q] = {"tp": tp, "fp": fp, "fn": fn, "withheld": withheld,
                  "precision": round(prec, 4) if prec is not None else None,
                  "recall": round(rec, 4) if rec is not None else None,
                  "f1": round(f1, 4) if f1 is not None else None}
    return out


def score(records, gold=None):
    """records: {doc_id: {"routed_to":…, "state":…, "escalated":…}}. The whole verdict."""
    gold = gold or load_gold()
    pairs, states = [], {}
    for doc_id, rec in records.items():
        if doc_id not in gold:
            continue
        pairs.append((gold[doc_id], rec.get("routed_to")))
        key = rec.get("state") if not rec.get("escalated") else "escalated"
        states[key] = states.get(key, 0) + 1

    m = confusion(pairs)
    n = len(pairs)
    correct = sum(m[q][q] for q in TX.labels())
    withheld = sum(m[q][None] for q in TX.labels())
    answered = n - withheld
    counts = {q: sum(m[q].values()) for q in TX.labels()}
    return {
        "documents": n,
        "gold_per_class": counts,
        "confusion": m,
        "per_class": per_class(m),
        "outcomes": states,
        "withheld": withheld,
        "withheld_rate": round(withheld / n, 4) if n else None,
        # Two accuracies, and the kit prints BOTH every time. `accuracy` is over everything the
        # router was given; `accuracy_when_answered` is over what it chose to answer. Reporting
        # only the second is how a router that escalates half its traffic advertises 96%.
        "accuracy": round(correct / n, 4) if n else None,
        "accuracy_when_answered": round(correct / answered, 4) if answered else None,
        "correct": correct,
        "answered": answered,
    }


def floor_sweep(records, gold=None, floors=(0.6, 0.9, 0.95, 0.99, 1.0)):
    """What each confidence floor would have bought, on the answers this run actually produced.

    ⚑ THE CURVE IS THE PUBLISHED THING, NEVER A CHOSEN NUMBER. Picking the floor that scores best
    on these 120 documents and printing that would be fitting a threshold to the set it is
    measured on. So the whole trade is printed and the choice stays the reader's.

    ⚠︎ AND ON THE FIRST REAL RUN IT SHOWED THE FLOOR DOES NOTHING. Every parseable answer came
    back at 0.95 or above, wrong ones included, so 0.6 and 0.95 escalate zero documents and the
    first floor that catches anything escalates 43% of the traffic. That finding only exists
    because this function reports the sweep instead of the kit reporting the default's result.
    A guardrail that is never exercised looks identical to a guardrail that works.
    """
    gold = gold or load_gold()
    pairs = [(rec.get("confidence"), rec.get("model_queue"), gold.get(doc_id))
             for doc_id, rec in records.items()
             if doc_id in gold and rec.get("state") == "ok"]
    out = []
    for f in floors:
        escalated = sum(1 for c, _, _ in pairs if c is None or c < f)
        routed_wrong = sum(1 for c, p, g in pairs if c is not None and c >= f and p != g)
        routed_right = sum(1 for c, p, g in pairs if c is not None and c >= f and p == g)
        out.append({"floor": f, "answers": len(pairs), "escalated": escalated,
                    "routed_correct": routed_right, "routed_wrong": routed_wrong,
                    "escalated_pct": round(100.0 * escalated / len(pairs), 1) if pairs else None})
    return out


def sweep_text(sweep):
    lines = ["%-7s %10s %10s %12s" % ("floor", "escalates", "still wrong", "still right"),
             "-" * 42]
    for r in sweep:
        lines.append("%-7.2f %6d %3.0f%% %10d %12d"
                     % (r["floor"], r["escalated"], r["escalated_pct"] or 0,
                        r["routed_wrong"], r["routed_correct"]))
    return "\n".join(lines)


def board(rows):
    """rows: [(name, note, scored)] -> the printable board, null baseline first."""
    out = ["", "%-22s %9s %9s %9s %9s" % ("", "docs", "accuracy", "answered", "withheld"),
           "-" * 64]
    for name, note, s in rows:
        out.append("%-22s %9d %8.1f%% %8.1f%% %8.1f%%" % (
            name, s["documents"], 100 * (s["accuracy"] or 0),
            100 * (s["accuracy_when_answered"] or 0), 100 * (s["withheld_rate"] or 0)))
        out.append("%-22s %s" % ("", note))
    return "\n".join(out)


def matrix_text(s):
    labels = TX.labels()
    head = "%-14s %s %8s" % ("gold \\ routed", "".join("%12s" % TX.label_of(p) for p in labels),
                             "withheld")
    lines = [head, "-" * len(head)]
    for g in labels:
        lines.append("%-14s %s %8d" % (TX.label_of(g),
                                       "".join("%12d" % s["confusion"][g][p] for p in labels),
                                       s["confusion"][g][None]))
    return "\n".join(lines)
