"""SEAM 4 — running the statement. Pure code, read-only, bounded in time and in rows.

⚑ THE CONNECTION IS OPENED READ-ONLY AT THE FILE LEVEL. `file:...?mode=ro` is SQLite's own flag,
not a convention this kit invented: the database is opened without write permission, so a
statement that somehow got past guard.py still cannot change anything. That is the second of the
two independent layers described in guard.py, and it is the one that does not depend on anybody's
parser being right.

⚑ BOTH BOUNDS EXIST BECAUSE BOTH FAILURES ARE REAL, AND THEY ARE DIFFERENT FAILURES.
  · TIME  — a generated query can cross-join two tables and never come back. `set_progress_handler`
            interrupts it from inside SQLite rather than leaving the process wedged.
  · ROWS  — a query can return the whole table, which is not a wrong answer so much as an
            unusable one, and on a bigger database is how a kit eats its own memory.
A run that hits either bound is RECORDED as having hit it, never silently truncated: a result cut
off at the cap and a result that genuinely had that many rows must not look the same.
"""
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "data", "shop.db")

TIMEOUT_S = 5.0
MAX_ROWS = 500


class ExecError(Exception):
    """A statement that ran and failed. Distinct from guard.Refused, which never ran at all —
    the eval taxonomy needs to tell 'the model wrote invalid SQL' from 'the model wrote a write'."""


def connect(path=DB):
    if not os.path.exists(path):
        raise ExecError("no database at %s — run `python3 tools/build_db.py` first" % path)
    # uri=True is what makes mode=ro mean anything; without it the whole string is read as a
    # filename and the database opens writable with a very odd name.
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def run(sql, path=DB, timeout_s=TIMEOUT_S, max_rows=MAX_ROWS):
    """Execute a read-only statement. Returns a dict; raises ExecError only when SQLite refused it.

    `truncated` is a first-class field rather than an inference from len(rows) == max_rows, because
    a query that legitimately returns exactly max_rows is not truncated and must not be reported as
    though it were.
    """
    con = connect(path)
    deadline = time.time() + timeout_s
    # Fires every N VM instructions; returning non-zero aborts the statement from inside SQLite.
    con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
    t0 = time.time()
    try:
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
    except sqlite3.OperationalError as exc:
        # "interrupted" is what the progress handler produces, and it is a timeout rather than a
        # syntax problem. Reporting them as the same thing would send a reader to fix the wrong file.
        msg = str(exc)
        if "interrupted" in msg.lower():
            raise ExecError("timed out after %.1fs — the query did not finish" % timeout_s)
        raise ExecError("SQLite refused the statement: %s" % msg)
    except sqlite3.Error as exc:
        raise ExecError("SQLite error: %s" % exc)
    finally:
        con.close()
    return {"columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "ms": round((time.time() - t0) * 1000, 2)}


def signature(result):
    """A comparable form of a result set, for execution match.

    Floats are rounded to 4 decimals: two arithmetically identical aggregates can differ in the
    last bit depending on summation order, and a kit that fails a correct answer over 1e-15 is
    measuring float representation rather than SQL.
    """
    def norm(v):
        if isinstance(v, float):
            return round(v, 4)
        return v
    return [[norm(v) for v in row] for row in result["rows"]]


def same(a, b, ordered=False):
    """Execution match between two result sets.

    Column NAMES are deliberately not compared — `AS revenue` versus `AS total_revenue` is a
    labelling choice, not a different answer.

    ⚑ `ordered` IS DECLARED BY THE LABEL, NOT SNIFFED FROM THE SQL — corrected after the first run.
    This used to read `"order by" in (sql_a + sql_b)`, i.e. compare row order whenever EITHER query
    happened to sort. That is wrong in a way that quietly costs the model marks: a gold query may
    carry `ORDER BY` as a presentation nicety for a question that never demanded one, and a model
    answering "how many orders does each status have" without a gratuitous sort was then scored
    wrong for returning the identical rows. It cost q-13 and q-17 on the first run.

    Whether order is part of the answer is a property of the QUESTION — "top 10" needs it, "how
    many per status" does not — so it belongs in the labelled set where the gold author can state
    it, not in a string test over SQL somebody else wrote.

    ⚠︎ COLUMN SETS ARE STILL COMPARED EXACTLY, AND THAT IS A REAL LIMITATION RATHER THAN A BUG.
    "Which region has the most customers?" answered as `North` and as `North, 106` are both
    defensible, and this returns False for that pair. It is left strict on purpose: loosening it
    would mean guessing which columns a question implies, which is a judgement the harness has no
    basis to make. It goes in `could_not_verify` on every published report instead.
    """
    ra, rb = signature(a), signature(b)
    if not ordered:
        ra = sorted(ra, key=lambda r: [(v is None, str(v)) for v in r])
        rb = sorted(rb, key=lambda r: [(v is None, str(v)) for v in r])
    return ra == rb
