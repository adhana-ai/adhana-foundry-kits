"""The four tools the model may call, and nothing else.

⚑ THE CATALOGUE IS A CLOSED LIST AND THE LOOP ENFORCES IT. A model that names a tool not in here
gets a refusal back, not an exception and not a guess at what it meant. That refusal is a recorded
outcome — "asked for something that does not exist" is a distinct failure from "picked the wrong
one of the four", and collapsing them would hide which it does.

⚑ ALL FOUR ARE READ-ONLY, LOCAL AND PURE. No network, no writes, no auth, no service. That is the
line between a kit and a product, and an agentic kit is the one most likely to be asked to cross
it: the moment a tool can act on the world, the eval stops being about tool CHOICE and starts being
about blast radius, which is a different kit and a much larger one.

⚠︎ `today()` RETURNS A FIXED DATE. It does not read the clock. A corpus whose answers change at
midnight cannot be diffed, and the labelled answers here were computed against this instant.
"""
from __future__ import annotations

import os
import re
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
DB = os.path.join(DATA, "shop.db")
NOTES = os.path.join(DATA, "notes")

# The one fixed instant. Kept in step with tools/build_corpus.py::TODAY by the check in
# evals/check_labels.py, because two copies of a constant is two copies of a constant.
TODAY = "2026-03-31"

# Anything that is not a plain read is refused before sqlite sees it. A kit that let a model write
# to the sample database would be teaching the wrong thing regardless of how the eval scored.
_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma|vacuum)\b",
                    re.I)

CATALOGUE = [
    {"name": "shop_sql",
     "arg": "a single read-only SELECT over tables customers(id,name,joined) and "
            "orders(id,customer_id,placed,amount,shipped)",
     "does": "runs it and returns up to 20 rows"},
    {"name": "doc_search",
     "arg": "a few keywords",
     "does": "returns the matching policy notes, in full — there are six and they are short"},
    {"name": "calc",
     "arg": "an arithmetic expression using digits and + - * / ( ) . %",
     "does": "evaluates it and returns the number"},
    {"name": "today",
     "arg": "nothing",
     "does": "returns the current date as YYYY-MM-DD"},
]
NAMES = [t["name"] for t in CATALOGUE]


class ToolError(RuntimeError):
    """A tool was called and could not do the thing. Recorded, never raised out of the loop."""


def shop_sql(arg):
    q = (arg or "").strip().rstrip(";")
    if not q.lower().startswith("select"):
        raise ToolError("only a single SELECT is allowed")
    if _WRITE.search(q) or ";" in q:
        raise ToolError("only a single read-only SELECT is allowed")
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    try:
        cur = con.execute(q)
        rows = cur.fetchmany(20)
        cols = [d[0] for d in cur.description or []]
    except sqlite3.Error as exc:
        raise ToolError("sqlite: %s" % exc)
    finally:
        con.close()
    if not rows:
        return "0 rows"
    return "\n".join([" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in r)
                                           for r in rows])


def doc_search(arg):
    terms = [t for t in re.split(r"\W+", (arg or "").lower()) if len(t) > 2]
    if not terms:
        raise ToolError("no searchable terms")
    hits = []
    for name in sorted(os.listdir(NOTES)):
        text = open(os.path.join(NOTES, name), encoding="utf-8").read()
        if any(t in text.lower() or t in name.lower() for t in terms):
            hits.append("--- %s ---\n%s" % (name, text.strip()))
    return "\n".join(hits) if hits else "no note matched"


def calc(arg):
    expr = (arg or "").strip()
    # A calculator that can evaluate arbitrary Python is not a calculator. The whitelist is the
    # guard, checked before eval sees the string rather than after.
    if not expr or not re.fullmatch(r"[0-9+\-*/().%\s]+", expr):
        raise ToolError("only digits and + - * / ( ) . % are allowed")
    try:
        val = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 — whitelisted above
    except Exception as exc:
        raise ToolError("could not evaluate: %s" % exc)
    return ("%g" % val) if isinstance(val, float) else str(val)


def today(arg=None):
    return TODAY


DISPATCH = {"shop_sql": shop_sql, "doc_search": doc_search, "calc": calc, "today": today}


def resolve(name):
    """Normalise a name the model wrote to a catalogue name, or None.

    ⚑ CASE AND SURROUNDING PUNCTUATION ARE NOT A TOOL CHOICE. `CALL TODAY` and `call today()` are
    a model picking `today` in a slightly different hand, and scoring them as "asked for a tool
    that does not exist" would file a formatting slip under the one measurement this kit exists to
    make. Anything beyond that — a name that is not one of the four — is a real refusal.
    """
    key = (name or "").strip().strip("()").strip().lower()
    return key if key in DISPATCH else None


def call(name, arg):
    """Run one tool. Returns (ok, text). An unknown name is a refusal, not a crash."""
    key = resolve(name)
    if key is None:
        return False, ("no tool called %r — the catalogue is: %s" % (name, ", ".join(NAMES)))
    try:
        return True, DISPATCH[key](arg)
    except ToolError as exc:
        return False, str(exc)


def catalogue_text():
    """The catalogue as the model sees it, verbatim — one place, so the prompt and the guard can
    never describe different tools."""
    return "\n".join("- %s(%s) — %s" % (t["name"], t["arg"], t["does"]) for t in CATALOGUE)
