"""Build the sample database. Two tables, one fixed seed, no network.

WHY THE CORPUS IS GENERATED RATHER THAN FETCHED. Every other kit in this repo ships documents it
pulled from somewhere public and had to argue a licence for. This kit's corpus is a SCHEMA more
than a body of text — what the model is shown is `customers(...)` and `orders(...)`, not the rows —
so a fabricated database costs nothing in realism and removes the licence question entirely. MIT,
same as the repo, nothing scraped, nothing redistributed.

The two tables are the worked example on AI Foundry's own Query Construction page: `customers` and
`orders`, joined on `customer_id`, with `order_amount` and `order_date`. A reader who arrives from
the teaching page meets the tables they were just taught, which is worth more than novelty.

⚑ FIXED SEED, AND THE SEED IS THE POINT. `random.Random(SEED)` means every fork rebuilds the
BYTE-IDENTICAL database, so the labelled set's gold answers stay true for everyone. A corpus that
differs per clone would make every published number unreproducible, which is the one thing a kit
exists to avoid. Do not "improve" the data without regenerating the gold answers — check_labels.py
recomputes them and will tell you.

⚠︎ THE AWKWARD ROWS ARE DELIBERATE, NOT NOISE. Three properties are built in on purpose because
they are what separates a query that runs from a query that is right:

  · 112 customers have NO orders in 2024. An inner JOIN silently drops them, which is the classic
    wrong-but-plausible answer to "average revenue per customer".
  · Some orders carry a NULL order_amount (cancelled before pricing). AVG skips NULLs silently.
  · Two customers share a display name. GROUP BY name rather than customer_id merges them.

Each one is a real mistake a competent person makes, and each is invisible in the result. The kit
cannot demonstrate that the eval layer earns its keep unless the data can express the failure.
"""
import os
import random
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "data", "shop.db")

SEED = 20260811
N_CUSTOMERS = 400
N_ORDERS = 5000
NO_ORDER_CUSTOMERS = 112          # never ordered in 2024 — the inner-JOIN trap
NULL_AMOUNT_SHARE = 0.03          # cancelled before pricing — the AVG-skips-NULL trap

FIRST = ["Brightwell", "Kesler", "Ardan", "Nornis", "Vantage", "Halloway", "Pemberton",
         "Castell", "Rowan", "Merrick", "Danforth", "Ellery", "Skarn", "Thackeray",
         "Vestral", "Orwin", "Lambeth", "Quillon", "Redmayne", "Fairholt"]
LAST = ["Foods", "& Vance", "Logistics", "Supply", "Partners", "Holdings", "Metals",
        "Textiles", "Freight", "Provisions", "Instruments", "Dairy", "Timber", "Optics"]
# ⚠︎ THE SUFFIX EXISTS TO MAKE NAMES UNIQUE, AND IT WAS ADDED AFTER MEASURING. Without it the
# pool is 20 x 14 = 280 combinations for 400 customers, so the generator produced 117 accidentally
# shared names — and the comment below claiming ONE planted duplicate was simply false. A corpus
# where a third of the names collide does not teach "GROUP BY the key, not the label"; it just
# makes every name-grouped query wrong for a reason nobody chose. 20 x 14 x 5 = 1,400 is enough to
# draw 400 distinct names, so the one collision that remains is the one put there on purpose.
SUFFIX = ["Ltd", "Group", "Co", "PLC", "Holdings"]
REGIONS = ["North", "South", "East", "West"]
STATUS = ["shipped", "shipped", "shipped", "shipped", "pending", "cancelled"]

SCHEMA = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  region      TEXT    NOT NULL,
  signup_date TEXT    NOT NULL
);
CREATE TABLE orders (
  order_id     INTEGER PRIMARY KEY,
  customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
  order_date   TEXT    NOT NULL,
  order_amount REAL,
  status       TEXT    NOT NULL
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date     ON orders(order_date);
"""


def _date(rng, year):
    return "%04d-%02d-%02d" % (year, rng.randint(1, 12), rng.randint(1, 28))


def build(path=DB):
    rng = random.Random(SEED)
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)

    pool = ["%s %s %s" % (f, l, s) for f in FIRST for l in LAST for s in SUFFIX]
    rng.shuffle(pool)
    if len(pool) < N_CUSTOMERS:
        raise SystemExit("name pool %d < %d customers — widen FIRST/LAST/SUFFIX"
                         % (len(pool), N_CUSTOMERS))
    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        customers.append((cid, pool[cid - 1], rng.choice(REGIONS),
                          _date(rng, rng.choice([2022, 2023]))))
    # THE DUPLICATE NAME, planted rather than hoped for: two different customer_ids, one display
    # name. GROUP BY c.name silently merges them and GROUP BY c.customer_id does not.
    customers[7] = (customers[7][0], customers[3][1], customers[7][2], customers[7][3])
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)

    # The first NO_ORDER_CUSTOMERS ids get no 2024 orders at all. They are real customers with
    # real signup dates — an inner JOIN drops them and an average over customers must not.
    ordering = list(range(NO_ORDER_CUSTOMERS + 1, N_CUSTOMERS + 1))
    orders = []
    for oid in range(1, N_ORDERS + 1):
        cid = rng.choice(ordering)
        year = 2024 if rng.random() < 0.72 else 2023
        amount = round(rng.lognormvariate(4.6, 0.85), 2)
        if rng.random() < NULL_AMOUNT_SHARE:
            amount = None
        orders.append((oid, cid, _date(rng, year), amount, rng.choice(STATUS)))
    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    con.commit()

    stats = {
        "customers": con.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "orders": con.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "orders_2024": con.execute(
            "SELECT COUNT(*) FROM orders WHERE order_date >= '2024-01-01' "
            "AND order_date < '2025-01-01'").fetchone()[0],
        "null_amounts": con.execute(
            "SELECT COUNT(*) FROM orders WHERE order_amount IS NULL").fetchone()[0],
        "customers_without_2024_orders": con.execute(
            "SELECT COUNT(*) FROM customers c WHERE NOT EXISTS ("
            "  SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id"
            "   AND o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01')").fetchone()[0],
        "duplicate_display_names": con.execute(
            "SELECT COUNT(*) FROM (SELECT name FROM customers GROUP BY name HAVING COUNT(*) > 1)"
        ).fetchone()[0],
        "bytes": 0,
    }
    con.close()
    stats["bytes"] = os.path.getsize(path)
    return stats


def main():
    s = build()
    print("built %s" % os.path.relpath(DB, HERE))
    for k, v in s.items():
        print("  %-30s %s" % (k, "{:,}".format(v) if isinstance(v, int) else v))
    print("\nthe three planted traps, all of them invisible in a result set:")
    print("  %-30s %s" % ("customers with no 2024 order", s["customers_without_2024_orders"]))
    print("  %-30s %s" % ("orders with NULL amount", s["null_amounts"]))
    print("  %-30s %s" % ("shared display names", s["duplicate_display_names"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
