#!/usr/bin/env python3
"""Generate synthetic bank/brokerage statements and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one statement per file) and data/gold.jsonl, byte-identical on every
run. Every account holder, institution, deposit and balance here is invented -- nothing is
fetched and nothing is licensed from anybody, so the corpus ships under this repo's MIT licence.
See data/SOURCES.md for why an invented corpus is the only option: a real bank/brokerage
statement cannot be published at all.

⚑ GOLD IS DERIVED FROM THE GENERATED DEPOSIT LINES, NEVER FROM A TARGET THAT SEEDED THEM.
`largest_deposit_amount`/`largest_deposit_description` are read back off the actual generated
deposit list, and `ending_balance` is recomputed from `beginning_balance + deposits - other_debits`
-- the same numbers the document states. `_verify()` below reconciles every statement to the cent.

⚑ THE PLANTED AMBIGUITY: "documented" means the description names a verifiable INSTITUTIONAL
counterparty -- a named employer, "IRS TREAS", a named pension fund, "SSA", or a named bank/
brokerage on a transfer. A P2P transfer from a person (Zelle/Venmo/cash), however specific-looking,
is NOT institutionally verifiable and is undocumented -- this is the real underwriting distinction
this kit exists to test. AMBIGUOUS_FRACTION of large deposits are written in the CONFUSABLE
phrasing: a generic "Payroll Deposit" / "Direct Deposit" line with NO employer named (reads as
payroll, is not verifiable) or a transfer that names an institution without the word "payroll" or
"transfer" anywhere near it. A model that pattern-matches on a keyword rather than checking for a
named, verifiable counterparty will misclassify these. Gold always records the TRUE documented
state regardless of phrasing.
"""
import argparse
import itertools
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260820                              # fixed. change it and every downstream file changes.
N_STATEMENTS = 55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]
INSTITUTIONS = ["Meridian Trust Bank", "Northfield Savings", "Cascade Federal Credit Union",
                "Harborline Bank", "Ridgeway National Bank", "Pinehurst Brokerage",
                "Beacon Point Bank", "Ashcroft Federal Bank", "Copper Valley Bank",
                "Sterling Gate Brokerage"]
EMPLOYERS = ["ACME LOGISTICS INC", "BRIGHTPATH HEALTH SYSTEMS", "NORTHWIND MFG CO",
             "SUMMIT RETAIL GROUP", "CLEARVIEW CONSULTING LLC", "VANTAGE FOOD SERVICES",
             "IRONGATE CONSTRUCTION", "BLUE HARBOR LOGISTICS", "CRESTLINE SCHOOL DISTRICT"]
PENSIONS = ["Statewide Teachers Pension Fund", "Ironworkers Local 47 Pension Trust",
            "Meridian Municipal Retirement System"]

ACCOUNT_TYPES = ["checking", "checking", "checking", "savings", "savings", "money_market",
                  "brokerage"]

# Kit-declared policy, NOT a real agency's published guideline -- see README/SOURCES.md.
LARGE_DEPOSIT_THRESHOLD_USD = 1000.0
AMBIGUOUS_FRACTION = 0.40
NO_DEPOSIT_FRACTION = 0.18                    # statements with zero deposits that period


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _small_deposit(rng):
    """A below-threshold deposit. `documented` is a real classification here too -- it is what
    the eval reads when NO large deposit exists in the period, so it must never be left unset."""
    variant = rng.choice([0, 1, 2, 3])
    if variant == 0:
        return round(rng.uniform(15, 300), 2), "Mobile Check Deposit", False
    if variant == 1:
        return round(rng.uniform(20, 400), 2), "ATM Deposit", False
    if variant == 2:
        payer = rng.choice(FIRST) + " " + rng.choice(LAST)[0] + "."
        return round(rng.uniform(20, 250), 2), "Zelle from %s" % payer, False
    # Interest is paid by the holding institution itself -- self-evidently verifiable off the
    # same statement, so it is the one small-deposit kind that counts as documented.
    return round(rng.uniform(10, 500), 2), "Interest Payment", True


def _large_documented_desc(rng, ambiguous):
    kind = rng.choice(["payroll", "tax", "pension", "ssa", "xfer"])
    if kind == "payroll":
        employer = rng.choice(EMPLOYERS)
        if ambiguous:
            # names the employer, but never says the word "payroll" or "direct deposit" --
            # tests whether a model requires the keyword rather than the named counterparty.
            return "ACH CREDIT %s" % employer
        return "Direct Deposit - Payroll %s" % employer
    if kind == "tax":
        return "IRS TREAS 310 TAX REF"
    if kind == "pension":
        return "Pension Payment - %s" % rng.choice(PENSIONS)
    if kind == "ssa":
        return "SOCIAL SECURITY ADMINISTRATION SSA BENEFIT"
    inst = rng.choice(INSTITUTIONS)
    return "Wire Transfer from %s" % inst


def _large_undocumented_desc(rng, ambiguous):
    if ambiguous:
        # says "Payroll" / "Direct Deposit" with NO employer named -- reads as documented on
        # a keyword scan, is not actually verifiable against any named counterparty.
        return rng.choice(["Payroll Deposit", "Direct Deposit", "ACH Credit - Payroll"])
    kind = rng.choice(["cash", "p2p", "check", "generic"])
    if kind == "cash":
        return "Deposit - Cash"
    if kind == "p2p":
        payer = rng.choice(FIRST) + " " + rng.choice(LAST)[0] + "."
        return rng.choice(["Zelle from %s" % payer, "Venmo Transfer from %s" % payer])
    if kind == "check":
        return "Mobile Check Deposit"
    return "Deposit"


def build_all(rng, n=N_STATEMENTS):
    stats = {"large_total": 0, "large_ambiguous": 0, "documented": 0, "undocumented": 0,
             "no_deposits": 0}
    out = []
    for i in range(1, n + 1):
        holder = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        institution = rng.choice(INSTITUTIONS)
        account_type = rng.choice(ACCOUNT_TYPES)
        year, month = 2026, rng.randint(1, 6)
        start = "%04d-%02d-01" % (year, month)
        end_day = 28 if month == 2 else 30
        end = "%04d-%02d-%02d" % (year, month, end_day)
        beginning_balance = round(rng.uniform(1500.0, 42000.0), 2)

        has_deposits = rng.random() >= NO_DEPOSIT_FRACTION
        deposits = []                         # [amount, description, documented_bool]
        if has_deposits:
            n_small = rng.randint(1, 4)
            for _ in range(n_small):
                amt, desc, doc = _small_deposit(rng)
                deposits.append([round(amt, 2), desc, doc])
            if rng.random() < 0.55:
                amt = round(rng.uniform(LARGE_DEPOSIT_THRESHOLD_USD, 42000.0), 2)
                documented = rng.random() < 0.5
                ambiguous = rng.random() < AMBIGUOUS_FRACTION
                stats["large_total"] += 1
                stats["large_ambiguous"] += int(ambiguous)
                desc = (_large_documented_desc(rng, ambiguous) if documented
                        else _large_undocumented_desc(rng, ambiguous))
                deposits.append([amt, desc, documented])
                stats["documented" if documented else "undocumented"] += 1
            rng.shuffle(deposits)
        else:
            stats["no_deposits"] += 1

        other_debits = round(rng.uniform(200.0, 3500.0), 2)
        total_deposits = round(sum(d[0] for d in deposits), 2)
        ending_balance = round(beginning_balance + total_deposits - other_debits, 2)
        largest = max(deposits, key=lambda d: d[0]) if deposits else None

        stmt_id = "AV-%04d" % i
        lines = [
            _underline("Statement Holder"), holder, "",
            _underline("Institution"), institution, "",
            _underline("Account Type"), account_type, "",
            _underline("Statement Period"), "%s to %s" % (start, end), "",
            _underline("Account Summary"),
            "Beginning Balance: $%.2f" % beginning_balance,
            "Ending Balance: $%.2f" % ending_balance, "",
            _underline("Deposits This Period"),
        ]
        if deposits:
            for j, (amt, desc, _doc) in enumerate(deposits, 1):
                day = min(28, j * 4 + rng.randint(1, 3))
                lines.append("%04d-%02d-%02d   $%.2f   %s" % (year, month, day, amt, desc))
        else:
            lines.append("No deposits posted this period.")
        lines += ["", _underline("Other Activity"),
                  "Debits and fees this period: $%.2f" % other_debits, ""]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": stmt_id,
            "account_holder": holder, "institution": institution, "account_type": account_type,
            "period_start": start, "period_end": end,
            "beginning_balance": beginning_balance, "ending_balance": ending_balance,
            "largest_deposit_amount": largest[0] if largest else None,
            "largest_deposit_description": largest[1] if largest else None,
            # Every deposit (small or large) carries a real documented/undocumented
            # classification now, so this is never null on a statement that has a largest
            # deposit at all -- "not applicable" only happens when there is no deposit.
            "deposit_documented": ("yes" if largest and largest[2] else
                                    ("no" if largest else None)),
            "large_deposit_flag": bool(largest and largest[0] >= LARGE_DEPOSIT_THRESHOLD_USD
                                        and not largest[2]),
            "stated": {
                "largest_deposit_amount": largest is not None,
                "largest_deposit_description": largest is not None,
                "deposit_documented": largest is not None,
            },
        }
        out.append((stmt_id, text, gold))
    return out, stats


def _verify(rows):
    """Every dollar figure gold states must reconcile against the document text it labels."""
    for stmt_id, text, gold in rows:
        assert ("Beginning Balance: $%.2f" % gold["beginning_balance"]) in text, stmt_id
        assert ("Ending Balance: $%.2f" % gold["ending_balance"]) in text, stmt_id
        if gold["largest_deposit_amount"] is not None:
            needle = "$%.2f   %s" % (gold["largest_deposit_amount"],
                                     gold["largest_deposit_description"])
            assert needle in text, (stmt_id, needle)
        else:
            assert "No deposits posted this period." in text, stmt_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_STATEMENTS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for stmt_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % stmt_id), "w", encoding="utf-8") as fh:
            fh.write(text)

    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _stmt_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    n_large = stats["large_total"]
    print("statements: %d   no-deposit statements: %d (%.0f%%)"
          % (len(rows), stats["no_deposits"], 100.0 * stats["no_deposits"] / len(rows)))
    print("large deposits (>= $%.0f): %d total, %d documented, %d undocumented"
          % (LARGE_DEPOSIT_THRESHOLD_USD, n_large, stats["documented"], stats["undocumented"]))
    if n_large:
        print("  %d (%.0f%%) written in the confusable ambiguous phrasing"
              % (stats["large_ambiguous"], 100.0 * stats["large_ambiguous"] / n_large))
    print("internal consistency check: PASSED (every statement's stated balances and largest "
          "deposit line reconcile against its own document text)")


if __name__ == "__main__":
    main()
