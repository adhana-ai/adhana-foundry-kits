#!/usr/bin/env python3
"""Generate the recurring-JE basis documents and the close-cycle records that check against them,
from a fixed seed.

    python3 tools/build_corpus.py

Writes data/basis/<rje_id>.txt, data/templates.json, data/close_cycles.jsonl and data/gold.jsonl,
byte-identical on every run. Nothing is fetched and nothing is licensed from anybody: every account,
amount and basis narrative here is invented, so the corpus ships under this repo's MIT licence and
there is no third-party grant to verify.

⚑ WHY THE BASIS DOCUMENTS ARE INVENTED, AND WHY THAT IS THE HONEST CHOICE HERE RATHER THAN THE
CONVENIENT ONE. A real recurring-JE workpaper names a real account structure, real contracted
amounts (a real lease, a real depreciation schedule) and sits inside a real close package nobody
will let leave the building. A synthetic set is the only kind of close corpus that can be re-run by
a stranger with a clone and no NDA to sign. See data/SOURCES.md.

⚑ THE BASIS IS PROSE ON PURPOSE. The four checks below are simple comparisons once the facts are in
hand -- the actual job is getting them out of a paragraph that phrases the same fact a different way
every time ("Approved amount last period: $4,120.00" vs "The prior period's approved posting totaled
$4,120.00"). A structured lookup table would make this kit a diff, not a reconciliation. See
src/close.py for what the model is actually asked to do with it.

⚑ FOUR CHECKS, EACH PLANTED ON PURPOSE. A corpus that cannot express a check's failure cannot show
the eval earning its keep -- same discipline as data-reconcile's five planted checks. Every close
cycle below is generated with a KNOWN verdict per check, counted and asserted:

    account     the drafted JE's posting account against the account the basis document states
                for this recurring entry.
    amount      the drafted JE's amount against the prior-period APPROVED amount the basis
                document states, allowing a small normal fluctuation and nothing more.
    basis       the drafted JE's stated calculation method against the method the basis document
                describes -- catches a recurring entry whose basis silently changed.
    residual    the account-reconciliation residual (GL balance less supporting schedule) against
                the materiality threshold the basis document states for that account.

Each check on each close cycle is exactly one of three things: CLEAN (the value satisfies what the
basis document states), DEFECT (the value violates what the basis document states), or UNVERIFIABLE
(the basis document never states the fact this check needs -- a recurring entry whose calculation
method lives only in a preparer's memory or a prior-year workpaper, never a machine-readable record;
an account whose reconciliation materiality band was never documented). A checker that guesses here
is worse than one that says so -- unverifiable is not a coin flip, it is forced by a real omission
the corpus plants on purpose (see build_templates()).
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
SEED = 20260819                              # fixed. change it and every downstream file changes.

# 12 recurring-JE templates, each posting to a different GL account every close. Deliberately a mix
# of the account families a month-end close actually carries: accruals, amortization, deferred
# revenue, and standing allowances.
TEMPLATE_ACCOUNTS = [
    ("6410", "Facilities Rent Expense", "straight-line lease accrual over the remaining term"),
    ("6120", "Software Subscription Expense", "monthly amortization of the annual licence prepay"),
    ("6510", "Depreciation Expense - Equipment", "straight-line depreciation per the fixed-asset schedule"),
    ("2210", "Deferred Revenue - Support Contracts", "ratable recognition over the contract's service period"),
    ("6330", "Insurance Expense", "monthly amortization of the annual premium prepay"),
    ("2140", "Accrued Payroll - Bonus", "pro-rata accrual against the annual bonus pool"),
    ("6605", "Bad Debt Expense", "the rolling allowance percentage applied to period-end receivables"),
    ("1420", "Prepaid Maintenance", "straight-line amortization of the service contract prepay"),
    ("6710", "Property Tax Expense", "pro-rata accrual of the annual assessed tax bill"),
    ("2310", "Warranty Reserve", "the standing warranty rate applied to period shipments"),
    ("6205", "Utilities Accrual", "the trailing three-month average consumption estimate"),
    ("1450", "Prepaid Freight", "straight-line amortization of the annual freight-contract prepay"),
]
DECOY_ACCOUNTS = [
    ("6420", "Facilities Repairs Expense"), ("6130", "IT Hardware Expense"),
    ("6520", "Depreciation Expense - Leasehold"), ("2220", "Deferred Revenue - Licences"),
    ("6340", "Insurance Expense - D&O"), ("2150", "Accrued Payroll - Commissions"),
    ("6615", "Bad Debt Recovery"), ("1430", "Prepaid Rent"), ("6720", "Franchise Tax Expense"),
    ("2320", "Litigation Reserve"), ("6215", "Telecom Accrual"), ("1460", "Prepaid Insurance"),
]
CHECKS = ("account", "amount", "basis", "residual")
VERDICTS = ("clean", "defect", "unverifiable")

PREPARERS = ["R. Okafor", "M. Sundaram", "L. Bergstrom", "T. Ferreira", "A. Kowalski", "J. Meyer"]
REVIEWERS = ["D. Whitfield", "S. Nakamura", "C. Alvarado", "P. Delgado"]


def _template_id(i):
    return "RJE-%04d" % (100 + i)


NO_BASIS_N = 2                                 # 2 of 12 templates -- one in six, exactly
NO_THRESHOLD_N = 3                             # 3 of 12 templates -- one in four, exactly


def build_templates(rng):
    """Each template gets a fixed account, a prior-period approved amount, and a documented
    calculation basis -- usually. Exactly 2 of the 12 templates (one in six) have NO documented
    basis at all (the calculation method lives only in a preparer's prior-year workpaper), and
    exactly 3 of the 12 (one in four) have NO documented reconciliation materiality band. Those two
    omissions are what makes `unverifiable` a real, not a hypothetical, verdict -- same discipline
    as data-reconcile's supplier agreements that omit a ship-to list or a value band.

    ⚠︎ CHOSEN BY SAMPLE, NOT BY INDEPENDENT COIN FLIP PER TEMPLATE. An independent
    `rng.random() > threshold` draw per template can legitimately land on zero omissions across 12
    templates (roughly an 11% chance at 1-in-6) -- which would silently ship a kit whose flagship
    unverifiable case never appears anywhere in the corpus. Sampling a fixed count guarantees the
    proportion this docstring claims is the proportion that ships."""
    no_basis = set(rng.sample(range(len(TEMPLATE_ACCOUNTS)), NO_BASIS_N))
    remaining = [i for i in range(len(TEMPLATE_ACCOUNTS)) if i not in no_basis]
    no_threshold = set(rng.sample(remaining, NO_THRESHOLD_N))

    templates = []
    for i, (acct_id, acct_name, basis_method) in enumerate(TEMPLATE_ACCOUNTS):
        prior_amount = round(rng.uniform(850.0, 42000.0), 2)
        has_basis = i not in no_basis
        has_threshold = i not in no_threshold
        threshold = round(rng.choice([500, 750, 1000, 1500, 2500, 4000]) * 1.0) if has_threshold else None
        templates.append({
            "id": _template_id(i), "account_id": acct_id, "account_name": acct_name,
            "basis_method": basis_method, "prior_amount": prior_amount,
            "has_basis": has_basis, "has_threshold": has_threshold, "threshold": threshold,
            "preparer": rng.choice(PREPARERS), "reviewer": rng.choice(REVIEWERS),
        })
    return templates


def _amount_para(t, rng):
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return ("The prior-period approved amount for this recurring entry was $%.2f, posted to "
                "account %s (%s)." % (t["prior_amount"], t["account_id"], t["account_name"]))
    if variant == 1:
        return ("Approved amount last period: $%.2f. This recurring entry posts to account %s -- "
                "%s." % (t["prior_amount"], t["account_id"], t["account_name"]))
    return ("Last period's approved posting under this recurring template totaled $%.2f against "
            "account %s (%s)." % (t["prior_amount"], t["account_id"], t["account_name"]))


def _basis_para(t, rng):
    if not t["has_basis"]:
        variant = rng.choice([0, 1])
        if variant == 0:
            return ("Basis note: the calculation method for this recurring entry is not recorded "
                    "in this workpaper. Refer to the preparer's prior-year working file.")
        return ("This template does not document a calculation method here -- the basis is "
                "maintained in the preparer's own file from the prior close, not attached.")
    variant = rng.choice([0, 1, 2])
    if variant == 0:
        return "Basis: %s." % t["basis_method"][0].upper() + t["basis_method"][1:]
    if variant == 1:
        return ("The amount is calculated using %s. This method has not changed since the "
                "template was established." % t["basis_method"])
    return ("Calculation method for this recurring entry: %s. Any change to this method requires "
            "a documented basis-change memo before the next close." % t["basis_method"])


def _threshold_para(t, rng):
    if not t["has_threshold"]:
        return ("No reconciliation materiality band is documented for account %s -- treat any "
                "residual on this account as needing reviewer judgment." % t["account_id"])
    variant = rng.choice([0, 1])
    if variant == 0:
        return ("A reconciliation residual on account %s of $%d or less is treated as immaterial "
                "and may be carried without a write-off memo. A residual above that requires a "
                "write-off memo or escalation to the reviewer."
                % (t["account_id"], t["threshold"]))
    return ("Residuals up to $%d on this account do not require explanation. Anything above $%d "
            "must be documented with a write-off memo or flagged to the reviewer before the close "
            "can be signed off." % (t["threshold"], t["threshold"]))


def _duties_para(t):
    return ("Preparer of record: %s. Reviewer of record: %s. Segregation of duties: the preparer "
            "and reviewer must be different named individuals, and neither may post or clear this "
            "entry without the other's sign-off." % (t["preparer"], t["reviewer"]))


def basis_text(t, rng):
    """Render the template's facts as a prose basis workpaper. Both the PHRASING of each paragraph
    (picked from several hand-written variants) and the ORDER the paragraphs appear in are
    randomised per template, so a checker cannot key off a fixed sentence template or a fixed
    position. This is the whole reason evals/baseline.py, which is regex against one fixed
    template, is the honest free floor and not a competitor."""
    header = ["RECURRING JOURNAL ENTRY BASIS", "%s (%s)" % (t["account_name"], t["id"]), "",
              _amount_para(t, rng)]
    body = [_basis_para(t, rng), _threshold_para(t, rng), _duties_para(t)]
    rng.shuffle(body)
    return "\n\n".join(header + body) + "\n"


def _draft_account(t, defect, rng):
    if defect:
        pool = [a for a in DECOY_ACCOUNTS if a[0] != t["account_id"]]
        return rng.choice(pool)
    return (t["account_id"], t["account_name"])


def _draft_amount(t, defect, rng):
    if defect:
        pct = rng.uniform(0.18, 0.55) * rng.choice([-1, 1])
        return round(max(t["prior_amount"] * (1 + pct), 25.0), 2)
    pct = rng.uniform(-0.03, 0.03)
    return round(max(t["prior_amount"] * (1 + pct), 25.0), 2)


def _draft_basis_note(t, defect, rng):
    if defect:
        others = [m for (_, _, m) in TEMPLATE_ACCOUNTS if m != t["basis_method"]]
        return "Calculated using %s this period." % rng.choice(others)
    if not t["has_basis"]:
        return "Calculated the same way as last period, per the preparer's working file."
    return "Calculated using %s, consistent with the template." % t["basis_method"]


def _residual(t, defect, rng):
    if not t["has_threshold"]:
        return round(rng.uniform(-3000, 3000), 2)
    if defect:
        band = t["threshold"] * rng.uniform(1.4, 4.0)
        return round(band * rng.choice([-1, 1]), 2)
    return round(rng.uniform(-0.8, 0.8) * t["threshold"], 2)


def build_cycles(templates, rng, n_per_template=5):
    """Each template gets N close cycles. One cycle per template is fully clean; the rest each
    carry exactly one planted defect (round-robined across the four checks) so per-check accuracy
    is measurable and not dominated by cycles that are wrong everywhere at once. A template whose
    basis is undocumented yields `unverifiable` on the basis check for every one of its cycles,
    whatever the draft says -- the omission, not a coin flip, decides it. Same for the residual
    check on a template whose account has no documented materiality band."""
    cycles, gold = [], []
    periods = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
    cyc_i = 0
    for t in templates:
        plan = ["clean"] + [CHECKS[k % len(CHECKS)] for k in range(n_per_template - 1)]
        for pi, defect_check in enumerate(plan):
            cyc_i += 1
            close_id = "CLS-%05d" % cyc_i
            acct_id, acct_name = _draft_account(t, defect_check == "account", rng)
            amount = _draft_amount(t, defect_check == "amount", rng)
            basis_note = _draft_basis_note(t, defect_check == "basis", rng)
            gl_balance = round(rng.uniform(1500.0, 90000.0), 2)
            residual = _residual(t, defect_check == "residual", rng)
            supporting_balance = round(gl_balance - residual, 2)

            cycle = {
                "close_id": close_id, "rje_id": t["id"], "period": periods[pi % len(periods)],
                "je_account_id": acct_id, "je_account_name": acct_name, "je_amount": amount,
                "je_basis_note": basis_note,
                "recon_gl_balance": gl_balance, "recon_supporting_balance": supporting_balance,
                "recon_residual": round(gl_balance - supporting_balance, 2),
            }

            account_v = "defect" if acct_id != t["account_id"] else "clean"
            amount_v = "defect" if abs(amount - t["prior_amount"]) > 0.05 * t["prior_amount"] else "clean"
            basis_v = ("unverifiable" if not t["has_basis"]
                       else ("defect" if defect_check == "basis" else "clean"))
            residual_v = ("unverifiable" if not t["has_threshold"]
                          else ("defect" if abs(residual) > t["threshold"] else "clean"))

            checks = {"account": account_v, "amount": amount_v, "basis": basis_v,
                      "residual": residual_v}
            overall = ("defects_flagged" if "defect" in checks.values() else
                       "unverifiable" if "unverifiable" in checks.values() else "clean")
            cycles.append(cycle)
            gold.append({"close_id": close_id, "rje_id": t["id"], "checks": checks,
                        "overall": overall})
    return cycles, gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=5)
    args = ap.parse_args()

    rng = random.Random(SEED)
    templates = build_templates(rng)

    basis_dir = os.path.join(DATA, "basis")
    os.makedirs(basis_dir, exist_ok=True)
    tpl_index = []
    for t in templates:
        text = basis_text(t, rng)
        with open(os.path.join(basis_dir, t["id"] + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)
        tpl_index.append({"id": t["id"], "account_id": t["account_id"],
                          "account_name": t["account_name"], "has_basis": t["has_basis"],
                          "has_threshold": t["has_threshold"]})
    with open(os.path.join(DATA, "templates.json"), "w", encoding="utf-8") as fh:
        json.dump(tpl_index, fh, indent=2)

    cycles, gold = build_cycles(templates, rng, n_per_template=args.per_template)
    with open(os.path.join(DATA, "close_cycles.jsonl"), "w", encoding="utf-8") as fh:
        for c in cycles:
            fh.write(json.dumps(c) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")

    tally = {}
    for g in gold:
        tally[g["overall"]] = tally.get(g["overall"], 0) + 1
    print("templates: %d   close cycles: %d   basis docs: %s" % (
        len(templates), len(cycles), os.path.join("data", "basis")))
    print("overall verdict tally:", tally)
    per_check = {c: {} for c in CHECKS}
    for g in gold:
        for c in CHECKS:
            v = g["checks"][c]
            per_check[c][v] = per_check[c].get(v, 0) + 1
    for c in CHECKS:
        print("  %-10s %s" % (c, per_check[c]))


if __name__ == "__main__":
    main()
