"""One scorer, used by the free floor and the model alike.

⚑ THREE POPULATIONS, AND THEY ARE NEVER AVERAGED INTO ONE NUMBER.

  applied cells   the request should have been carried out. Is the file now exactly right?
  collateral      of the writes that happened, did anything change that should NOT have?
  refusal cells   the request should have produced NO write. Was it correctly declined?

A single blended "accuracy" would let a system that edits everything look good: it would score full
marks on the applied population and its failures would be diluted by them. The expensive real
failure here is a confident write that should never have happened, and it lives in its own column.

⚑ COLLATERAL IS THE METRIC THIS KIT EXISTS FOR, AND IT IS NOT THE SAME AS "WRONG".
A document can have the requested change applied perfectly AND have three other lines rewritten —
tidied punctuation, a reflowed clause, a "helpful" correction nobody asked for. Every other kit
here returns a judgement and cannot express that failure at all. So it is counted separately, in
LINES, and the exact lines are kept on the record.
"""
import difflib
import json
import os
import re


def load_requests(root):
    rows = []
    with open(os.path.join(root, "data", "requests.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_doc(root, kind, doc_id):
    with open(os.path.join(root, "data", kind, doc_id + ".txt"), encoding="utf-8") as f:
        return f.read()


def norm(text):
    """Normalise for comparison. Applied to gold and output identically.

    Only trailing whitespace per line and at the end of the file. NOT case, NOT internal spacing,
    NOT punctuation — this kit's whole claim is that the bytes are right, and a scorer that forgave
    internal differences would forgive exactly the collateral damage it exists to measure.
    """
    if text is None:
        return None
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).rstrip("\n")


def line_diff(before, after):
    """The lines that differ, as (kind, text). Used both to score collateral and to show it."""
    a, b = norm(before).split("\n"), norm(after).split("\n")
    out = []
    for d in difflib.unified_diff(a, b, lineterm="", n=0):
        if d.startswith(("---", "+++", "@@")):
            continue
        if d.startswith("-"):
            out.append(("removed", d[1:]))
        elif d.startswith("+"):
            out.append(("added", d[1:]))
    return out


def score_one(before, gold, produced, should_write):
    """One request. `produced` is None when the system declined to write."""
    r = {"should_write": should_write, "wrote": produced is not None}

    if not should_write:
        # A refusal is correct when NOTHING was written. Writing the document back unchanged is
        # still a write in the sense that matters — but it does no damage, so it is recorded
        # separately rather than counted as an unsafe write.
        if produced is None:
            r.update(declined=True, unsafe_write=False, harmless_rewrite=False, correct=True)
        elif norm(produced) == norm(before):
            r.update(declined=False, unsafe_write=False, harmless_rewrite=True, correct=False)
        else:
            r.update(declined=False, unsafe_write=True, harmless_rewrite=False, correct=False,
                     damage=line_diff(before, produced))
        return r

    # An edit was required.
    if produced is None:
        r.update(applied=False, collateral_lines=0, correct=False, refused_a_valid_edit=True)
        return r
    ok = norm(produced) == norm(gold)
    # Collateral is measured against GOLD, not against BEFORE: the requested change is expected to
    # differ from before, so diffing there would count the intended edit as damage.
    damage = line_diff(gold, produced)
    r.update(applied=ok, collateral_lines=len(damage), correct=ok,
             refused_a_valid_edit=False)
    if damage:
        r["damage"] = damage[:8]
    return r


def score_all(rows, produced_by_id, root):
    """rows: the request records. produced_by_id: {doc_id: text or None}."""
    per, fam = [], {}
    for row in rows:
        did = row["doc_id"]
        before = load_doc(root, "corpus", did)
        gold = load_doc(root, "gold", did)
        s = score_one(before, gold, produced_by_id.get(did), row["should_write"])
        s.update(doc_id=did, family=row["family"])
        per.append(s)
        f = fam.setdefault(row["family"], {"n": 0, "correct": 0})
        f["n"] += 1
        f["correct"] += 1 if s["correct"] else 0

    edits = [s for s in per if s["should_write"]]
    refus = [s for s in per if not s["should_write"]]
    applied_ok = sum(1 for s in edits if s["applied"])
    clean = sum(1 for s in edits if s["applied"] and s["collateral_lines"] == 0)
    collateral_total = sum(s["collateral_lines"] for s in edits)
    declined = sum(1 for s in refus if s["declined"])
    unsafe = sum(1 for s in refus if s["unsafe_write"])

    return {
        "scores": {
            # ⚑ EVERY RATE SHIPS WITH ITS DENOMINATOR, HEALTHY RUNS INCLUDED. A guard that only
            # appears when something is wrong is a guard nobody learns to read — and a refusal rate
            # over 8 rows is a different claim from the same rate over 36.
            "edit_cells": len(edits),
            "edit_applied": round(applied_ok / len(edits), 4) if edits else None,
            "edit_clean": round(clean / len(edits), 4) if edits else None,
            "collateral_lines": collateral_total,
            "refusal_cells": len(refus),
            "refusal_accuracy": round(declined / len(refus), 4) if refus else None,
            "unsafe_writes": unsafe,
        },
        "by_family": {k: dict(v, pct=round(100 * v["correct"] / v["n"], 1))
                      for k, v in sorted(fam.items())},
        "rows": per,
    }
