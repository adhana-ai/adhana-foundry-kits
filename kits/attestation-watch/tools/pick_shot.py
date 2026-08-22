#!/usr/bin/env python3
"""Which register should the screenshot and the worked example use? Pure code, free, no model.

    python3 tools/pick_shot.py

⚑ CHOSEN BY A RULE, NOT BY EYE. A worked example picked by scrolling until something looks
interesting is a worked example picked to flatter the kit. The rule here, in order: the most
DISTINCT statuses on one register; then the most rows that need an owner rather than a reminder
(`contradicted` and `not_determinable`); then the largest roster. Ties break on register id, so
the answer is stable across runs and across machines.

It prints the register it picked and what is on it, so the caption on the kit page can be written
from the register rather than from memory.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rulebook as RB                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def rank(reg):
    st = [p["status"] for p in reg["attesters"]]
    return (len(set(st)),
            sum(1 for s in st if s in ("contradicted", "not_determinable")),
            len(st),
            reg["register_id"])


def main():
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    best = max(rows, key=rank)
    st = [p["status"] for p in best["attesters"]]
    print("SHOT_DOC=%s" % best["register_id"])
    print("  %d people, %d distinct statuses, %d needing an owner rather than a reminder"
          % (len(st), len(set(st)),
             sum(1 for s in st if s in ("contradicted", "not_determinable"))))
    for p in best["attesters"]:
        print("  %-8s %-24s %-18s due %s   filed %s"
              % (p["person_ref"], p["role"], p["status"], p["due_on"] or "none derivable",
                 p["return_filed_on"] or "nothing on file"))
    print("  worklist: %s"
          % ", ".join(p["person_ref"] for p in best["attesters"]
                      if p["status"] in RB.WORKLIST))
    print("  administrator's note: %s" % best["register_note"])
    print("  the note's register %s this register's own facts"
          % ("CONTRADICTS" if best["contradicting_note"] else "agrees with"))
    print("  needs_owner_review: %r" % best["needs_owner_review"])


if __name__ == "__main__":
    main()
