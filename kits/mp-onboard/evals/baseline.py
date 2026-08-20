"""What a simple, dumb rule catches, over the same corpus. Free. No key, no dependency, no model
call.

    python -m evals.baseline

Every sibling kit publishes this floor -- fin-payrun's rule-order baseline, fin-invval's own floor
-- and this kit's version of the same idea is a classifier someone free-texting a quick script
would actually write: if a note is attached at all, treat it as covering whatever field
disagreed.

⚠︎ THE BUG THIS BASELINE HAS, ON PURPOSE, AND WHY IT IS HONEST RATHER THAN A STRAWMAN. A person
asked to write "does the note explain the mismatch" in five minutes reaches for the field that's
cheapest to check -- is submission_note non-empty -- and stops there, rather than checking whether
the note actually names the field that disagreed. That is the WRONG rule: the mechanic this kit
measures requires the note to specifically and genuinely account for THAT field's discrepancy, not
merely exist. Treating any non-empty note as covering every mismatch in the application is not a
bug someone would need to be clever to introduce; it is the natural shortcut to write, and it is
exactly why the over-explaining metric exists.

**This baseline is correct on every application with no note at all, and on every application
with no mismatch at all.** It goes wrong exactly where a note is attached but does not actually
address the field that disagrees -- most visibly on the corpus's planted banking trap, where a
majority of trap applications carry a generic, unrelated note (see data/SOURCES.md) that this
baseline reads as an explanation it isn't. See the printed miss list below for exactly which
applications this baseline gets wrong, and why.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import onboard as C                                    # noqa: E402
from evals import scoring as S                                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(HERE, "results")


def classify(app):
    """has_note, not "does the note name this field" -- see the module docstring. Returns the
    seven-field flag dict, the same shape src/onboard.py's check() returns."""
    d = app["declared"]
    doc = {
        "business_name": app["business_registration"]["legal_name"],
        "business_address": app["business_registration"]["registered_address"],
        "tax_id": app["business_registration"]["tax_id"],
        "bank_account_name": app["bank_letter"]["account_holder_name"],
        "bank_routing_number": app["bank_letter"]["routing_number"],
        "owner_name": app["id_document"]["full_name"],
        "owner_address": app["id_document"]["address"],
    }
    has_note = bool((app.get("submission_note") or "").strip())
    flags = {}
    for f in S.FIELDS:
        if d[f] == doc[f]:
            flags[f] = "match"
        elif has_note:
            flags[f] = "mismatch_explained"
        else:
            flags[f] = "mismatch"
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="b000-notepresence")
    a = ap.parse_args()

    gold = C.load_gold()
    records = []
    misses = []
    for app in C.applications():
        flags = classify(app)
        rec = {"application_id": app["application_id"]}
        rec.update(flags)
        records.append(rec)
        g = gold[app["application_id"]]
        wrong = [f for f in S.FIELDS if flags[f] != g[f]]
        if wrong:
            misses.append((app["application_id"], g.get("pattern"), wrong,
                          bool((app.get("submission_note") or "").strip())))

    scored = S.score(records, gold)
    out = {"run_id": a.run_id, "baseline": True, "applications": len(records),
          "scores": scored["overall"], "per_field": scored["per_field"],
          "misses": [{"application_id": i, "pattern": p, "wrong_fields": w, "had_note": n}
                    for i, p, w, n in misses]}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "eval-%s.json" % a.run_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("note-presence baseline (any note = explained) over %d applications" % len(records))
    print("field accuracy: %s%%" % scored["overall"]["field_accuracy_pct"])
    print("missed_banking_mismatch: %s of %s (%s%%)"
          % (scored["overall"]["missed_banking_mismatch"],
             scored["overall"]["missed_banking_mismatch_denominator"],
             scored["overall"]["missed_banking_mismatch_rate_pct"]))
    print("over_explained: %s of %s (%s%%)"
          % (scored["overall"]["over_explained"], scored["overall"]["over_explained_denominator"],
             scored["overall"]["over_explained_rate_pct"]))
    for f, pf in scored["per_field"].items():
        print("  %-24s accuracy %s%%  (gold %s)" % (f, pf["accuracy_pct"], pf["gold_total"]))
    print("\nmisses (%d):" % len(misses))
    for i, p, w, n in misses:
        print("  %-16s pattern=%-22s had_note=%-5s wrong_fields=%s" % (i, p, n, ", ".join(w)))
    print("-> %s" % os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
