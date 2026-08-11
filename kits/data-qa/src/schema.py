"""SEAM 2 — the schema card. The only thing about your database the model ever sees.

⚑ THE MODEL NEVER SEES A ROW. This is the property that makes the kit safe to point at a real
database and it is easy to lose by accident: adding "here are three example rows to help" to the
prompt sends customer data to a third party. If you decide you want sample values, that is a real
decision with a privacy consequence — make it deliberately, and say so on the report.

⚑ IT IS READ OUT OF THE DATABASE, NOT WRITTEN DOWN. `PRAGMA table_info` and `foreign_key_list` are
the source. A schema card typed into a file drifts from the database the moment either changes, and
the failure is silent — the model writes a perfectly good query against a table that no longer has
that column. Reading it means the card cannot be stale.

⚠︎ WHY THE WHOLE SCHEMA GOES IN, AND WHERE THAT STOPS WORKING. There is no retrieval step and no
schema-linking. For two tables that is honest and simple. It stops working when the schema no
longer fits the context window — a few hundred tables, or a few dozen very wide ones — and at that
point this kit's answer is "you now need schema linking", not a bigger prompt. That limit belongs
in the published `breaks_at_scale` in those words rather than hidden behind a technique.
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "data", "shop.db")


def read(path=DB):
    """Return [{name, columns:[{name,type,pk,notnull}], foreign_keys:[...]}] straight from SQLite."""
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        tables = []
        for t in names:
            cols = [{"name": r[1], "type": r[2] or "", "notnull": bool(r[3]), "pk": bool(r[5])}
                    for r in con.execute("PRAGMA table_info(%s)" % t)]
            fks = [{"column": r[3], "references": r[2], "to": r[4]}
                   for r in con.execute("PRAGMA foreign_key_list(%s)" % t)]
            tables.append({"name": t, "columns": cols, "foreign_keys": fks})
        return tables
    finally:
        con.close()


def card(tables=None, path=DB):
    """Render the schema as the text the prompt carries. Terse on purpose: every token here is
    paid for on every question, and lens 07 prices exactly this."""
    tables = tables if tables is not None else read(path)
    lines = []
    for t in tables:
        cols = []
        for c in t["columns"]:
            bits = c["type"]
            if c["pk"]:
                bits += " PRIMARY KEY"
            elif c["notnull"]:
                bits += " NOT NULL"
            cols.append("  %s %s" % (c["name"], bits.strip()))
        lines.append("TABLE %s (\n%s\n)" % (t["name"], ",\n".join(cols)))
        for fk in t["foreign_keys"]:
            lines.append("  FOREIGN KEY %s.%s -> %s.%s"
                         % (t["name"], fk["column"], fk["references"], fk["to"]))
    return "\n".join(lines)


def stats(path=DB):
    """Row counts, for the UI and the report. Not sent to the model — it is context for a person."""
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        return {t["name"]: con.execute("SELECT COUNT(*) FROM %s" % t["name"]).fetchone()[0]
                for t in read(path)}
    finally:
        con.close()


if __name__ == "__main__":
    print(card())
    print()
    for name, n in stats().items():
        print("%-12s %s rows" % (name, "{:,}".format(n)))
