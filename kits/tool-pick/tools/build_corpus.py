#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the corpus: a seeded shop database, six policy notes, and 120 labelled requests.

⚑ SELF-AUTHORED, AND FOR THIS USE CASE THAT IS THE HONEST CHOICE RATHER THAN THE CONVENIENT ONE.
A tool-choice corpus has to declare, for every request, the tool sequence that answers it — and
that label only exists relative to THIS set of tools. There is no public benchmark of "requests
labelled against your four local tools", because the tools are the variable. Generating both
together is the only way the labels can be true.

⚑ NO CLOCK IS READ. `today()` returns a fixed date and every generated row is arithmetic from a
fixed seed, so the corpus is byte-identical on every rebuild. A corpus that reads the clock cannot
be diffed, and a kit whose evidence changes when nobody edited it is not evidence.

THE TRAPS ARE PLANTED DELIBERATELY, and each one is a way a tool-choosing model actually fails:

  needs-none      the request needs no tool at all, and its words point straight at one
  two-step        two tools, IN ORDER — the second needs what the first returned
  wrong-surface   the obvious keyword names the wrong tool
  ambiguous       two rules match; only one is right
  unanswerable    nothing here can answer it, and the honest output is to decline

⚠︎ AND THE PLANTED TRAP MUST BE THE ONLY ONE. A generator that draws from too small a pool plants
collisions it did not mean to — UC010's produced 117 accidental duplicate names under a comment
claiming one. So `main()` audits its own output: every request is checked for accidental keyword
collisions and the counts per trap are printed and asserted.

    python3 tools/build_corpus.py
"""
from __future__ import annotations

import json
import os
import random
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
NOTES = os.path.join(DATA, "notes")
DB = os.path.join(DATA, "shop.db")
REQUESTS = os.path.join(DATA, "requests.jsonl")

SEED = 20260813
# The one fixed instant this corpus knows about. `today()` returns it, and every date below is
# arithmetic from it — nothing here calls datetime.now().
TODAY = "2026-03-31"

# ── the six policy notes ───────────────────────────────────────────────────────────────────────
# Short, plain, and each carrying exactly one fact a request will need. Written out rather than
# generated, because a "policy note" assembled from random words cannot be searched meaningfully
# and would make doc_search look worse than it is.
NOTE_TEXT = {
    "returns": "RETURNS POLICY\n\nA customer may return any item within 30 days of the order "
               "date for a full refund. Items returned after 30 days are refused. There is no "
               "limit on the number of separate returns a customer may make.\n",
    "refunds": "REFUND WINDOW\n\nRefunds are issued to the original payment method within 5 "
               "working days of the returned item arriving. The refund window is 30 days and is "
               "counted from the order date, not the delivery date.\n",
    "shipping": "SHIPPING\n\nStandard shipping is free on orders over 50. Orders under 50 are "
                "charged a flat 4.99. Express shipping is 12.99 and is not free at any order "
                "value.\n",
    "loyalty": "LOYALTY\n\nCustomers who have placed more than 3 orders are loyalty members. "
               "Loyalty members receive free express shipping and a 10 percent discount on every "
               "order.\n",
    "cancellations": "CANCELLATIONS\n\nAn order may be cancelled at no cost before it ships. "
                     "Once shipped, a cancellation is handled as a return and the returns policy "
                     "applies.\n",
    "warranty": "WARRANTY\n\nElectrical items carry a 12 month warranty from the order date. "
                "Warranty claims are separate from returns and are not subject to the 30 day "
                "window.\n",
}

# ── the four tools' names, as the corpus labels them ───────────────────────────────────────────
SQL, DOC, CALC, TODAY_T = "shop_sql", "doc_search", "calc", "today"

# ── the request templates, by trap ─────────────────────────────────────────────────────────────
# Each entry: (trap, text, truth, decline). `truth` is the tool sequence, in order. An empty list
# with decline=False means "answerable with no tool at all"; decline=True means "no tool here can
# answer it and saying so is the right output".
TEMPLATES = [
    # ── plain: one tool, unambiguous. The set has to contain the easy cases or the score is not
    # a score of anything a real request set looks like.
    ("plain", "How many orders were placed in {month}?", [SQL], False),
    ("plain", "How many customers are on file?", [SQL], False),
    ("plain", "Which customer has spent the most overall?", [SQL], False),
    ("plain", "What does the returns policy say about the deadline?", [DOC], False),
    ("plain", "How long is the warranty on electrical items?", [DOC], False),
    ("plain", "When is shipping free?", [DOC], False),
    ("plain", "What is {a} percent of {b}?", [CALC], False),
    ("plain", "What is {a} multiplied by {b}?", [CALC], False),
    ("plain", "What is today's date?", [TODAY_T], False),
    ("plain", "What is the date today?", [TODAY_T], False),

    # ── two-step: the second tool needs what the first returned. A one-shot router cannot get
    # these at any setting, which is the floor's structural ceiling rather than a tuning problem.
    ("two-step", "How many orders fall outside the deadline in the returns policy?",
     [DOC, SQL], False),
    ("two-step", "What percentage of customers have placed more than one order?", [SQL, CALC],
     False),
    ("two-step", "How much did customer {cid} spend, as a percentage of the {month} total?",
     [SQL, CALC], False),
    ("two-step", "How many customers qualify as loyalty members under the loyalty policy?",
     [DOC, SQL], False),
    ("two-step", "What is the average order value, and what is 10 percent of it?", [SQL, CALC],
     False),
    ("two-step", "How many days are left in the refund window for an order placed on {date}?",
     [DOC, CALC], False),

    # ── needs-none: answerable with no tool, and the wording drags a keyword router into one.
    ("needs-none", "How many plays did Shakespeare write?", [], False),
    ("needs-none", "How many days are in a leap year?", [], False),
    ("needs-none", "What does the acronym SQL stand for?", [], False),
    ("needs-none", "Who is the current customer of record for a returns policy — explain the "
                   "term in general.", [], False),

    # ── wrong-surface: the loudest keyword names the wrong tool.
    ("wrong-surface", "How many orders does the returns policy allow a customer to make?",
     [DOC], False),
    ("wrong-surface", "What is the total discount a loyalty customer receives, per the policy?",
     [DOC], False),
    ("wrong-surface", "What is the percentage discount in the loyalty policy?", [DOC], False),

    # ── ambiguous: two rules match and only one is right.
    ("ambiguous", "What is the current refund window in our policy?", [DOC], False),
    ("ambiguous", "What is the current number of customers?", [SQL], False),
    ("ambiguous", "What is today's total order count?", [SQL], False),

    # ── unanswerable: nothing here can answer it, and its words match a rule anyway.
    ("unanswerable", "What are our competitors' total sales?", [], True),
    ("unanswerable", "How many orders will we take next month?", [], True),
    ("unanswerable", "What is the customer satisfaction score for {month}?", [], True),
    ("unanswerable", "What does our supplier's returns policy allow?", [], True),
]

MONTHS = ["January", "February", "March"]
DATES = ["2026-03-02", "2026-03-11", "2026-03-19", "2026-02-24"]


def build_db(rng):
    """The two-table shop database — the same shape UC010 ships, generated here from this seed.

    Small on purpose: 120 customers and 400 orders is enough for every question in the set to have
    a real answer, and small enough that a forker can open the file and check one by hand.
    """
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, joined TEXT NOT NULL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
                             placed TEXT NOT NULL, amount REAL, shipped INTEGER NOT NULL);
    """)
    first = ["Ada", "Bram", "Cleo", "Dara", "Emil", "Fern", "Gus", "Hana", "Ivo", "Juno",
             "Kit", "Lena", "Mo", "Nils", "Ola", "Pia", "Quin", "Rex", "Sena", "Tam"]
    last = ["Ashby", "Berg", "Cole", "Dunn", "Ecker", "Frost", "Gill", "Hale", "Iyer", "Jost",
            "Kern", "Lowe", "Marsh", "Nagy", "Ohm", "Pike", "Quill", "Roth", "Sole", "Tan"]
    # 400 combinations for 120 customers — UC010's generator drew 400 names from 280 combinations
    # and produced 117 accidental collisions under a comment claiming one. Checked below, not hoped.
    names = ["%s %s" % (f, l) for f in first for l in last]
    rng.shuffle(names)
    customers = [(i + 1, names[i], "2025-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28)))
                 for i in range(120)]
    con.executemany("INSERT INTO customers VALUES (?,?,?)", customers)
    orders = []
    for oid in range(1, 401):
        cid = rng.randint(1, 120)
        month = rng.choice([1, 2, 3])
        placed = "2026-%02d-%02d" % (month, rng.randint(1, 28))
        amount = round(rng.uniform(8.0, 240.0), 2)
        orders.append((oid, cid, placed, amount, 1 if rng.random() < 0.82 else 0))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    con.commit()
    con.close()
    return len(customers), len(orders), len(set(c[1] for c in customers))


def build_notes():
    os.makedirs(NOTES, exist_ok=True)
    for name, text in NOTE_TEXT.items():
        with open(os.path.join(NOTES, "%s.txt" % name), "w", encoding="utf-8") as f:
            f.write(text)
    return len(NOTE_TEXT)


def build_requests(rng):
    """120 requests, cycling the templates so every trap is represented in a stated proportion."""
    rows = []
    i = 0
    while len(rows) < 120:
        trap, tpl, truth, decline = TEMPLATES[i % len(TEMPLATES)]
        i += 1
        text = tpl.format(month=rng.choice(MONTHS), a=rng.randint(5, 40) * 5,
                          b=rng.randint(20, 90) * 50, cid=rng.randint(1, 120),
                          date=rng.choice(DATES))
        rows.append({"id": "q%03d" % (len(rows) + 1), "trap": trap, "text": text,
                     "truth": list(truth), "decline": decline})
    return rows


def audit(rows):
    """Check that the planted traps are the only ones, and that the set is what it claims.

    ⚑ A CENSUS NO CODE CHECKS IS A CENSUS THAT GOES WRONG. Two things are asserted rather than
    assumed: every trap kind is present, and no two requests with DIFFERENT truths share identical
    text — a duplicate with a different label is an unwinnable row that would silently cap the
    score of anything, model or floor.
    """
    counts = {}
    for r in rows:
        counts[r["trap"]] = counts.get(r["trap"], 0) + 1
    by_text = {}
    for r in rows:
        by_text.setdefault(r["text"], set()).add(tuple(r["truth"]) + (r["decline"],))
    contradictions = [t for t, v in by_text.items() if len(v) > 1]
    return counts, contradictions


def main():
    rng = random.Random(SEED)
    os.makedirs(DATA, exist_ok=True)
    n_cust, n_ord, n_names = build_db(rng)
    n_notes = build_notes()
    rows = build_requests(rng)
    with open(REQUESTS, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    counts, contradictions = audit(rows)
    print("shop.db          %d customers (%d distinct names), %d orders"
          % (n_cust, n_names, n_ord))
    print("notes/           %d policy notes" % n_notes)
    print("requests.jsonl   %d requests" % len(rows))
    for trap in sorted(counts):
        print("   %-14s %3d" % (trap, counts[trap]))
    print("fixed date       %s (today() returns this; no clock is read)" % TODAY)

    if n_names != n_cust:
        print("!! %d accidental duplicate customer name(s) — widen the name pool"
              % (n_cust - n_names))
        return 1
    if contradictions:
        print("!! %d request text(s) carry more than one truth: %s"
              % (len(contradictions), contradictions[:2]))
        return 1
    missing = {t for t, _, _, _ in TEMPLATES} - set(counts)
    if missing:
        print("!! trap kind(s) absent from the built set: %s" % ", ".join(sorted(missing)))
        return 1
    print("\naudit: every trap kind present, no contradictory labels, no accidental name "
          "collisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
