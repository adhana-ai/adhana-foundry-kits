#!/usr/bin/env python3
"""Generate synthetic appraisal reports and their gold labels, from a fixed seed.

    python3 tools/build_corpus.py

Writes data/corpus/*.txt (one report per file) and data/gold.jsonl, byte-identical on every run.
Every property, appraiser and dollar figure here is invented -- nothing is fetched and nothing is
licensed from anybody, so the corpus ships under this repo's MIT licence. See data/SOURCES.md.

⚑ GOLD IS DERIVED FROM THE GENERATED REPORT TEXT, NEVER FROM A TARGET THAT SEEDED IT. The
reconciled value and the extraordinary-assumption text are read back off the actual generated
document, not carried over from a random draw.

⚑ THE PLANTED AMBIGUITY: this kit's whole guardrail is that an extraordinary assumption (EA) must
be caught wherever it is stated, not only under a dedicated "Extraordinary Assumptions" heading.
For reports that carry one, `AMBIGUOUS_FRACTION` are written EMBEDDED in a different section's
prose (Scope of Work or Comments) with no EA heading at all; the rest get a clearly labelled
"Extraordinary Assumptions" section. Gold always records the TRUE presence and verbatim text
regardless of where it was placed -- derived from which generator branch produced it, never
re-derived from a scorer's or a model's own reading of the section headings.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(DATA, "corpus")
SEED = 20260821
N_REPORTS = 55

FIRST = ["Jordan", "Morgan", "Casey", "Riley", "Avery", "Priya", "Wei", "Fatima", "Diego",
         "Elena", "Marcus", "Nadia", "Owen", "Sofia", "Liam", "Amara", "Kenji", "Ines",
         "Tobias", "Yara", "Grace", "Malik", "Renata", "Anton"]
LAST = ["Alvarez", "Chen", "Okafor", "Petrov", "Nakamura", "Silva", "Kowalski", "Haddad",
        "Rossi", "Larsen", "Osei", "Fischer", "Reyes", "Novak", "Duarte", "Bergstrom",
        "Abara", "Tanaka", "Whitfield", "Correa"]
STREETS = ["Maple Ridge Ln", "Cedar Hollow Dr", "Birchwood Ave", "Stonegate Ct", "Willow Creek Rd",
           "Harborview Ter", "Foxglove Way", "Pinehurst Cir", "Aspen Grove Blvd", "Meadowlark St"]
CITIES = [("Rosedale", "OH"), ("Brookhaven", "TX"), ("Fairmont", "NC"), ("Lakewood", "MI"),
          ("Clearview", "CO"), ("Millbrook", "PA"), ("Sunset Hills", "AZ"), ("Elmwood", "WI")]
APPROACHES = ["sales_comparison", "cost", "income"]

AMBIGUOUS_FRACTION = 0.40
NO_EA_FRACTION = 0.40


def _underline(label, ch="-"):
    return "%s\n%s" % (label, ch * max(len(label), 3))


def _labelled_ea(rng, text):
    return _underline("Extraordinary Assumptions") + "\n" + text


def _embedded_ea(rng, text, in_scope):
    """Same assumption, buried mid-paragraph in a different section with no EA heading."""
    if in_scope:
        return ("The appraiser was not provided a current survey; the site boundaries and "
                "improvements are as represented by the county assessor's records. %s "
                "This report proceeds on that basis." % text)
    return ("Photographs were taken at the time of inspection and are included in the addenda. "
            "%s No further verification of this point was undertaken." % text)


EA_TEXTS = [
    "It is assumed the subject's septic system is functioning adequately; no inspection was "
    "performed and none was available for review.",
    "It is assumed no adverse environmental conditions exist on or near the subject property; "
    "no environmental assessment was ordered or reviewed.",
    "It is assumed the subject property will be completed in a workmanlike manner per the plans "
    "and specifications provided, as the improvements were under construction at inspection.",
    "It is assumed the subject's foundation is free of material defects; a structural engineer's "
    "report was not obtained.",
]


def build_all(rng, n=N_REPORTS):
    stats = {"ea_present": 0, "ea_labelled": 0, "ea_embedded": 0, "no_ea": 0}
    out = []
    for i in range(1, n + 1):
        appraiser = "%s %s. %s" % (rng.choice(FIRST), rng.choice(LAST)[0], rng.choice(LAST))
        street_num = rng.randint(100, 9899)
        city, state = rng.choice(CITIES)
        address = "%d %s, %s, %s" % (street_num, rng.choice(STREETS), city, state)

        year, month = 2026, rng.randint(1, 7)
        effective_date = "%04d-%02d-%02d" % (year, month, rng.randint(1, 25))
        report_date = "%04d-%02d-%02d" % (year, month, min(28, int(effective_date[-2:]) + rng.randint(1, 5)))

        approach = rng.choice(APPROACHES)
        gla = rng.randint(1050, 4200)
        comp_count = rng.randint(3, 6)
        reconciled_value = round(rng.uniform(185000.0, 940000.0), -2)

        has_ea = rng.random() >= NO_EA_FRACTION
        ea_text = ea_section = None
        if has_ea:
            stats["ea_present"] += 1
            raw = rng.choice(EA_TEXTS)
            ambiguous = rng.random() < AMBIGUOUS_FRACTION
            if ambiguous:
                in_scope = rng.random() < 0.5
                ea_section = "Scope of Work" if in_scope else "Comments"
                ea_text = _embedded_ea(rng, raw, in_scope)
                stats["ea_embedded"] += 1
            else:
                ea_section = "Extraordinary Assumptions"
                ea_text = raw
                stats["ea_labelled"] += 1
        else:
            stats["no_ea"] += 1

        rpt_id = "AR-%04d" % i
        lines = [
            _underline("Subject Property"), address, "",
            _underline("Appraiser"), appraiser, "",
            _underline("Effective Date"), effective_date, "",
            _underline("Report Date"), report_date, "",
            _underline("Valuation Approach"), approach.replace("_", " "), "",
            _underline("Improvements"),
            "Gross living area: %d sq ft" % gla,
            "Comparable sales used: %d" % comp_count, "",
        ]
        if has_ea and ea_section == "Scope of Work":
            lines += [_underline("Scope of Work"), ea_text, ""]
        else:
            lines += [_underline("Scope of Work"),
                      "The appraiser inspected the subject property and researched the local "
                      "market for comparable sales. This report was prepared in conformance "
                      "with USPAP.", ""]
        if has_ea and ea_section == "Comments":
            lines += [_underline("Comments"), ea_text, ""]
        elif not (has_ea and ea_section == "Scope of Work"):
            lines += [_underline("Comments"),
                      "No further comments.", ""]
        if has_ea and ea_section == "Extraordinary Assumptions":
            lines += [_underline("Extraordinary Assumptions"), ea_text, ""]
        lines += [_underline("Reconciliation"),
                  "Reconciled value opinion: $%s" % format(int(reconciled_value), ","), ""]
        text = "\n".join(lines) + "\n"

        gold = {
            "stmt_id": rpt_id,
            "property_address": address, "appraiser_name": appraiser,
            "effective_date": effective_date, "report_date": report_date,
            "approach_used": approach, "reconciled_value": reconciled_value,
            "gross_living_area_sqft": gla, "comparable_count": comp_count,
            "extraordinary_assumption_present": "yes" if has_ea else "no",
            "extraordinary_assumption_text": ea_text,
            "stated": {"extraordinary_assumption_text": has_ea},
        }
        out.append((rpt_id, text, gold))
    return out, stats


def _verify(rows):
    for rpt_id, text, gold in rows:
        assert ("Reconciled value opinion: $%s" % format(int(gold["reconciled_value"]), ",")) in text, rpt_id
        if gold["extraordinary_assumption_text"] is not None:
            assert gold["extraordinary_assumption_text"] in text, rpt_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_REPORTS)
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows, stats = build_all(rng, n=args.n)

    os.makedirs(CORPUS, exist_ok=True)
    for f in os.listdir(CORPUS):
        if f.endswith(".txt"):
            os.remove(os.path.join(CORPUS, f))
    for rpt_id, text, _gold in rows:
        with open(os.path.join(CORPUS, "%s.txt" % rpt_id), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for _rpt_id, _text, gold in rows:
            fh.write(json.dumps(gold) + "\n")

    _verify(rows)

    print("reports: %d   no EA: %d (%.0f%%)"
          % (len(rows), stats["no_ea"], 100.0 * stats["no_ea"] / len(rows)))
    print("EA present: %d -- labelled: %d, embedded (no heading): %d (%.0f%% of EAs)"
          % (stats["ea_present"], stats["ea_labelled"], stats["ea_embedded"],
             100.0 * stats["ea_embedded"] / stats["ea_present"] if stats["ea_present"] else 0))
    print("internal consistency check: PASSED (every report's stated value and EA text "
          "reconcile against its own document text)")


if __name__ == "__main__":
    main()
