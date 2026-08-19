"""What regex alone catches, over the same corpus. Free. No key, no dependency, no model call.

    python -m evals.baseline

Every sibling kit publishes this floor — data-reconcile's regex-against-agreements score, ops-triage's
rule-and-threshold floor — and this kit's is the same idea applied to a close cycle: pull each
check's fact out of the basis document's prose with a handful of regexes tuned against the phrasing
this kit's own corpus happens to use most, then run the same deterministic comparison
`src/close.py` would run on facts a model extracted.

⚠︎ THIS IS NOT A COMPETITOR TO THE MODEL, IT IS THE FLOOR THE MODEL HAS TO CLEAR. The corpus's basis
documents are deliberately written in two or three phrasing variants per fact (see
tools/build_corpus.py::basis_text) precisely so a fixed set of patterns cannot cover all of them.
Where a pattern only matches the phrasing it was written against, the check comes back
`unverifiable` here even though the basis document does state the fact — that gap, measured per
check below, is what a model reading the sentence is actually for.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import close as C                                     # noqa: E402
from evals import scoring as S                                  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")

# ⚠︎ ONE PATTERN PER FIELD, DELIBERATELY, NOT ONE PER PHRASING VARIANT. tools/build_corpus.py
# writes each fact in one of two or three hand-written phrasings (see basis_text). A regex author
# who has not read every basis document in the corpus writes the pattern that matches the phrasing
# they saw first and moves on -- which is exactly this list. Widening it to cover every variant
# that ships would make this file the thing it exists to be the honest floor under. The account
# pattern below is the one exception: the account code appears beside the word "account" in every
# phrasing this corpus writes, so it happens to transfer without anyone writing it to.
_ACCOUNT_RE = re.compile(r"account (\d{4})")
_AMOUNT_RE = [re.compile(r"was \$([\d,]+\.\d{2}),")]
_BASIS_RE = [re.compile(r"Basis: (.+?)\.")]
_DRAFT_BASIS_RE = [re.compile(r"Calculated using (.+?),? consistent with the template"),
                   re.compile(r"Calculated using (.+?) this period")]
_THRESHOLD_RE = [re.compile(r"Residuals up to \$(\d+) on this account do not require explanation")]


def _first(patterns, text):
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def extract(basis_text):
    """Best-effort structured facts out of one basis document's prose. Any field this cannot find
    stays None -- callers treat None as 'no fact found', which is exactly what makes it an honest
    floor rather than a guesser."""
    m = _ACCOUNT_RE.search(basis_text)
    account = m.group(1) if m else None
    amount = _first(_AMOUNT_RE, basis_text)
    method = _first(_BASIS_RE, basis_text)
    threshold = _first(_THRESHOLD_RE, basis_text)
    return {
        "account": account,
        "prior_amount": float(amount.replace(",", "")) if amount else None,
        "basis_method": method.strip() if method else None,
        "threshold": float(threshold) if threshold else None,
    }


def judge(cycle, facts):
    """The same deterministic comparison a perfect extractor would run -- this is not where the
    baseline is weak. It is weak in `extract()`, which is the point."""
    out = {}

    if facts["account"] is None:
        out["account"] = "unverifiable"
    else:
        out["account"] = "defect" if cycle["je_account_id"] != facts["account"] else "clean"

    if facts["prior_amount"] is None:
        out["amount"] = "unverifiable"
    else:
        dev = abs(cycle["je_amount"] - facts["prior_amount"])
        out["amount"] = "defect" if dev > 0.05 * facts["prior_amount"] else "clean"

    if facts["basis_method"] is None:
        out["basis"] = "unverifiable"
    else:
        draft_method = _first(_DRAFT_BASIS_RE, cycle["je_basis_note"])
        matches = bool(draft_method) and draft_method.strip().lower() == facts["basis_method"].lower()
        out["basis"] = "clean" if matches else "defect"

    if facts["threshold"] is None:
        out["residual"] = "unverifiable"
    else:
        out["residual"] = "defect" if abs(cycle["recon_residual"]) > facts["threshold"] else "clean"

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-regex")
    a = ap.parse_args()

    gold = C.load_gold()
    records = []
    for cycle in C.cycles():
        text = C.load_basis(cycle["rje_id"])
        facts = extract(text)
        verdicts = judge(cycle, facts)
        records.append({"close_id": cycle["close_id"],
                        "checks": [{"check": c, "verdict": v} for c, v in verdicts.items()]})

    scored = S.score(records, gold)
    out = {"run_id": a.run_id, "baseline": True, "cycles": len(records),
          "scores": scored["overall"], "per_check": scored["per_check"]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("regex baseline over %d close cycles, %d checks" % (len(records), scored["overall"]["checks_scored"]))
    print("overall accuracy: %s%%" % scored["overall"]["accuracy_pct"])
    for c, pc in scored["per_check"].items():
        print("  %-10s accuracy %s%%  (unverifiable-by-baseline: %s of %s)"
              % (c, pc["accuracy_pct"], pc["predicted_unverifiable"], pc["gold_total"]))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
