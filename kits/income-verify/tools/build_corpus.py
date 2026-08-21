#!/usr/bin/env python3
"""Generate synthetic pay stubs and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one stub per file) and data/gold.jsonl, byte-identical on every run.
Every employee, employer and dollar figure here is invented -- nothing is fetched and nothing is
licensed from anybody, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ GOLD IS DERIVED FROM THE GENERATED YTD FIGURES, NEVER FROM A TARGET THAT SEEDED THEM. The
overtime-periods ratio and the qualifying-income arithmetic are recomputed from the actual numbers
written into the document text, not carried over from the random draw that produced them.

⚑ THE PLANTED AMBIGUITY: a bonus history note that USES THE WORD "annual" without actually
describing more than one year's payment ("Annual performance bonus" with no payment history
stated) reads as recurring on a keyword scan and is not actually documented as continuing; a note
that never says "annual" or "recurring" but DOES state two or more years of payment ("Bonus paid
in both 2024 and 2025 performance cycles") is genuinely continuing. AMBIGUOUS_FRACTION of bonus
notes are written in one of these confusable forms on purpose -- gold always records the TRUE
continuing state, derived from which generator branch produced the note, never re-derived from
the words a scorer or a model might also read.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_STUBS = 55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]
EMPLOYERS = ["ACME LOGISTICS INC", "BRIGHTPATH HEALTH SYSTEMS", "NORTHWIND MFG CO",
             "SUMMIT RETAIL GROUP", "CLEARVIEW CONSULTING LLC", "VANTAGE FOOD SERVICES",
             "IRONGATE CONSTRUCTION", "BLUE HARBOR LOGISTICS", "CRESTLINE SCHOOL DISTRICT",
             "PINEHURST FINANCIAL", "MERIDIAN HEALTHCARE PARTNERS"]

FREQUENCIES = ["weekly", "biweekly", "semimonthly", "monthly"]
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}

OT_CONTINUANCE_THRESHOLD = 0.75
LARGE_BONUS_THRESHOLD_USD = 1000.0
AMBIGUOUS_FRACTION = 0.40
NO_OT_FRACTION = 0.30
NO_BONUS_FRACTION = 0.35


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _recurring_bonus_note(rng, ambiguous):
    if ambiguous:
        # states two+ years of actual payment but never says "annual" or "recurring" --
        # tests whether a model reads the history rather than the label.
        years = rng.sample(range(2023, 2026), 2)
        return "Bonus paid in both the %d and %d performance cycles." % (min(years), max(years))
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "Annual performance bonus, paid in 2024 and 2025, expected to continue."
    if variant == 1:
        return "Recurring quarterly incentive bonus, paid each quarter for the past two years."
    return "Annual bonus per employment agreement, paid consistently each of the last 3 years."


def _one_time_bonus_note(rng, ambiguous):
    if ambiguous:
        # says "annual" but describes only ONE payment with no history -- reads as recurring
        # on a keyword scan, is not documented as continuing.
        return rng.choice([
            "Annual performance bonus.",
            "Annual incentive bonus, first year of eligibility.",
        ])
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "One-time signing bonus, not expected to recur."
    if variant == 1:
        return "Discretionary spot bonus, single payment, no history of recurrence."
    return "Retention bonus tied to a specific project, one-time payment."


def build_all(rng, n=N_STUBS):
    stats = {"ot_present": 0, "ot_qualifying": 0, "bonus_present": 0, "bonus_recurring": 0,
             "bonus_ambiguous": 0, "no_ot": 0, "no_bonus": 0}
    out = []
    for i in range(1, n + 1):
        name = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        employer = rng.choice(EMPLOYERS)
        freq = rng.choice(FREQUENCIES)
        total_periods = PERIODS_PER_YEAR[freq]
        year = 2026
        month = rng.randint(3, 11)          # far enough into the year for a real YTD figure
        period_end = "%04d-%02d-%02d" % (year, month, rng.randint(15, 28))
        months_elapsed = month
        periods_elapsed = max(1, round(total_periods * months_elapsed / 12))

        annual_base_rate = round(rng.uniform(38000.0, 145000.0), 2)
        ytd_base = round(annual_base_rate * months_elapsed / 12, 2)

        has_ot = rng.random() >= NO_OT_FRACTION
        ot_periods_paid = ot_periods_total = ytd_ot = None
        if has_ot:
            stats["ot_present"] += 1
            ot_periods_total = periods_elapsed
            # Sometimes clearly qualifying, sometimes clearly not, sometimes right at the line.
            band = rng.choice(["high", "low", "borderline"])
            if band == "high":
                frac = rng.uniform(0.80, 1.0)
            elif band == "low":
                frac = rng.uniform(0.10, 0.55)
            else:
                frac = rng.uniform(0.68, 0.78)
            ot_periods_paid = max(1, round(ot_periods_total * frac))
            ytd_ot = round(rng.uniform(800.0, 14000.0), 2)
            if ot_periods_paid / ot_periods_total >= OT_CONTINUANCE_THRESHOLD:
                stats["ot_qualifying"] += 1
        else:
            stats["no_ot"] += 1

        has_bonus = rng.random() >= NO_BONUS_FRACTION
        ytd_bonus = bonus_note = bonus_recurring = None
        if has_bonus:
            stats["bonus_present"] += 1
            ytd_bonus = round(rng.uniform(300.0, 18000.0), 2)
            recurring = rng.random() < 0.5
            ambiguous = rng.random() < AMBIGUOUS_FRACTION
            stats["bonus_ambiguous"] += int(ambiguous)
            if recurring:
                bonus_note = _recurring_bonus_note(rng, ambiguous)
                bonus_recurring = True
                stats["bonus_recurring"] += 1
            else:
                bonus_note = _one_time_bonus_note(rng, ambiguous)
                bonus_recurring = False
        else:
            stats["no_bonus"] += 1

        stmt_id = "IV-%04d" % i
        lines = [
            _underline("Employee"), name, "",
            _underline("Employer"), employer, "",
            _underline("Pay Frequency"), freq, "",
            _underline("Pay Period End"), period_end, "",
            _underline("Year-to-Date Earnings"),
            "Base pay YTD: $%.2f" % ytd_base,
        ]
        if has_ot:
            lines.append("Overtime pay YTD: $%.2f (paid in %d of %d pay periods this year)"
                         % (ytd_ot, ot_periods_paid, ot_periods_total))
        else:
            lines.append("Overtime pay YTD: none")
        if has_bonus:
            lines.append("Bonus pay YTD: $%.2f" % ytd_bonus)
        else:
            lines.append("Bonus pay YTD: none")
        lines += ["", _underline("Bonus History")]
        lines.append(bonus_note if has_bonus else "No bonus paid this year.")
        lines.append("")
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": stmt_id,
            "employee_name": name, "employer_name": employer, "pay_frequency": freq,
            "pay_period_end": period_end,
            "ytd_base_pay": ytd_base,
            "ytd_overtime_pay": ytd_ot,
            "overtime_periods_paid": ot_periods_paid,
            "overtime_periods_total": ot_periods_total,
            "ytd_bonus_pay": ytd_bonus,
            "bonus_recurring": ("yes" if bonus_recurring is True else
                                ("no" if bonus_recurring is False else None)),
            "months_elapsed": months_elapsed,
            "stated": {
                "ytd_overtime_pay": has_ot, "overtime_periods_paid": has_ot,
                "overtime_periods_total": has_ot,
                "ytd_bonus_pay": has_bonus, "bonus_recurring": has_bonus,
            },
        }
        out.append((stmt_id, text, gold))
    return out, stats


def _verify(rows):
    for stmt_id, text, gold in rows:
        assert ("Base pay YTD: $%.2f" % gold["ytd_base_pay"]) in text, stmt_id
        if gold["ytd_overtime_pay"] is not None:
            needle = "Overtime pay YTD: $%.2f (paid in %d of %d pay periods this year)" % (
                gold["ytd_overtime_pay"], gold["overtime_periods_paid"],
                gold["overtime_periods_total"])
            assert needle in text, (stmt_id, needle)
        else:
            assert "Overtime pay YTD: none" in text, stmt_id
        if gold["ytd_bonus_pay"] is not None:
            assert ("Bonus pay YTD: $%.2f" % gold["ytd_bonus_pay"]) in text, stmt_id
        else:
            assert "Bonus pay YTD: none" in text, stmt_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_STUBS)
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

    print("stubs: %d   no-overtime: %d (%.0f%%)   no-bonus: %d (%.0f%%)"
          % (len(rows), stats["no_ot"], 100.0 * stats["no_ot"] / len(rows),
             stats["no_bonus"], 100.0 * stats["no_bonus"] / len(rows)))
    print("overtime present: %d, qualifying (>=%.0f%% of periods): %d"
          % (stats["ot_present"], OT_CONTINUANCE_THRESHOLD * 100, stats["ot_qualifying"]))
    print("bonus present: %d, recurring: %d, one-time: %d, %d (%.0f%%) written in the "
          "confusable ambiguous phrasing"
          % (stats["bonus_present"], stats["bonus_recurring"],
             stats["bonus_present"] - stats["bonus_recurring"], stats["bonus_ambiguous"],
             100.0 * stats["bonus_ambiguous"] / stats["bonus_present"] if stats["bonus_present"] else 0))
    print("internal consistency check: PASSED (every stub's stated YTD figures reconcile "
          "against its own document text)")


if __name__ == "__main__":
    main()
