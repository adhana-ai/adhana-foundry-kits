"""SEAM 3 — the read-only guard. Pure code, and the reason this kit is safe to point at your data.

WHAT IT IS FOR. The model is asked for a question's answer and returns a STATEMENT, which is a
very different thing from an answer: a statement can delete the table it was asked about. Every
other failure in this kit produces a wrong number you can throw away. This one produces a database
you cannot get back, so it is the only failure the pipeline refuses rather than records.

⚑ IT RUNS BEFORE EXECUTION, NOT AFTER. Scoring a destructive statement after running it is not a
guard, it is a post-mortem. The ordering is the whole design: `model -> guard -> exec`.

⚑ TWO INDEPENDENT LAYERS, BECAUSE ONE IS A SINGLE POINT OF FAILURE.
  1. This module rejects anything that is not a single read-only SELECT.
  2. execute.py opens the database with SQLite's own `mode=ro` URI, so even a statement that got
     past this file cannot write. A parser can be fooled; a read-only file descriptor cannot.
Neither layer is decoration. If you delete one, say which one you deleted and why.

⚠︎ WHY A KEYWORD BLOCKLIST IS NOT ENOUGH ON ITS OWN, AND WHAT IS DONE INSTEAD. "Reject anything
containing DELETE" fails in both directions: it rejects `SELECT name FROM customers WHERE notes
LIKE '%delete%'`, which is harmless, and it can be walked around by a statement whose first
keyword is something the list never imagined. So the rule here is an ALLOWLIST on the leading
keyword — SELECT, or WITH followed by a SELECT — plus a hard cap of one statement. Everything not
positively recognised is refused. A blocklist has to imagine every attack; an allowlist only has
to recognise the one shape that is permitted.

⚠︎ COMMENTS AND STRINGS ARE STRIPPED BEFORE ANY OF THIS IS DECIDED. `SELECT 1; -- ` followed by a
newline and a DROP is two statements wearing one coat, and `';DROP TABLE x;--` inside a literal is
not a statement at all. Deciding statement count on raw text gets both wrong.
"""
import re

# The one shape that is allowed through. Anything else is refused, including statements that are
# perfectly harmless — a guard that tries to be clever about harmlessness is a guard with a bug.
ALLOWED_LEAD = ("select", "with")

# Recorded for the reason string only. The DECISION is the allowlist above; this list exists so a
# refusal can say "this looks like a DELETE" rather than "refused", which is the difference
# between a reader learning something and a reader filing a bug.
NAMED = ("insert", "update", "delete", "drop", "alter", "create", "replace", "truncate",
         "attach", "detach", "pragma", "vacuum", "reindex", "begin", "commit", "rollback")


class Refused(Exception):
    """Raised only by `enforce`. Carries `reason`, which is written for a person to read."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def strip_noise(sql):
    """Remove string literals and comments, so statement-counting sees structure and not content.

    Literals become empty quotes rather than disappearing: the goal is to preserve the SHAPE of the
    statement while removing anything an author could hide a semicolon inside.
    """
    out = re.sub(r"'(?:[^']|'')*'", "''", sql)          # single-quoted literals, '' escape included
    out = re.sub(r'"(?:[^"]|"")*"', '""', out)          # quoted identifiers
    out = re.sub(r"--[^\n]*", " ", out)                 # line comments
    out = re.sub(r"/\*.*?\*/", " ", out, flags=re.S)    # block comments
    return out


def statements(sql):
    """Split on semicolons AFTER noise removal. A trailing semicolon is not a second statement."""
    return [s for s in strip_noise(sql).split(";") if s.strip()]


def enforce(sql):
    """Return the SQL unchanged, or raise Refused with a reason a person can act on.

    Returning the ORIGINAL text rather than the stripped one is deliberate: the stripped form exists
    to make a decision, never to be executed. Executing a rewritten statement would mean the thing
    that ran is not the thing that was checked, which is its own class of bug.
    """
    if not sql or not sql.strip():
        raise Refused("empty statement — the model returned nothing to run")

    parts = statements(sql)
    if len(parts) == 0:
        raise Refused("no statement found once comments and string literals were removed")
    if len(parts) > 1:
        raise Refused("%d statements in one response; exactly one is allowed. A second statement "
                      "is how a read turns into a write." % len(parts))

    lead = (parts[0].strip().split() or [""])[0].lower().strip("(")
    if lead in ALLOWED_LEAD:
        # WITH must still resolve to a SELECT: `WITH x AS (...) DELETE FROM ...` is legal SQL in
        # some engines and is exactly the shape an allowlist on the first word alone would miss.
        if lead == "with" and not re.search(r"\)\s*select\b", parts[0], re.I):
            raise Refused("WITH clause does not lead to a SELECT — a CTE followed by anything "
                          "else is not a read")
        return sql

    if lead in NAMED:
        # "a UPDATE" and "a INSERT" both shipped onto the published threat page before anybody
        # read the table out loud. The reason string is written for a PERSON — it is the whole
        # justification for keeping NAMED separate from the allowlist that makes the decision —
        # and a reason a person stumbles over is doing its one job badly.
        article = "an" if lead[0] in "aeiou" else "a"
        raise Refused("refused: this is %s %s, not a query. The kit answers questions; it never "
                      "changes your data." % (article, lead.upper()))
    raise Refused("refused: statement starts with %r, which is not SELECT or WITH. Anything not "
                  "positively recognised as a read is refused." % lead)


def check(sql):
    """Boolean form for callers that want to branch rather than catch. Returns (ok, reason)."""
    try:
        enforce(sql)
        return True, None
    except Refused as exc:
        return False, exc.reason
