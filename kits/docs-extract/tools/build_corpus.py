"""Turn the raw pulls in data/_fetched/ into the shippable corpus and its gold set.

THE ONE DESIGN DECISION IN THIS FILE, AND WHY IT IS THE WHOLE INSTRUMENT.

A document here is built from the record's OWN PROSE — brief summary, detailed description,
eligibility criteria, arm and outcome descriptions — plus the short identity header a reader sees
at the top of a registry page. The gold values come from a DIFFERENT PLACE: the record's
structured modules.

The alternative was to render the structured values into the document as labelled lines and then
ask a model to read them back. That produces a beautiful accuracy figure and measures nothing: we
would have written the answer into the question. Keeping the two apart means every correct
extraction is the model genuinely finding a value stated in prose, and every "not found" is a
value the sponsor happened never to write down. Both are real facts about the document.

⚠︎ IT FOLLOWS THAT SOME FIELDS ARE NOT EXTRACTABLE AT ALL, and that is measured here rather than
discovered later. `--ceiling` reports, per field, how many documents state the gold value in their
prose at all. A field whose ceiling is near zero cannot be scored against a model and must not be
in the field set: it would publish a low accuracy that says nothing about the model.
"""
import argparse
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
CORPUS = os.path.join(HERE, "data", "corpus")
GOLD = os.path.join(HERE, "data", "gold.jsonl")


def _p(st):
    return st.get("protocolSection", {})


def _drop_na(v):
    """The registry's placeholders for "this does not apply", normalised to absence."""
    return None if v in (None, "", "NA", "N/A") else v


def document(st):
    """The shippable document: what a person reads, in the order they read it."""
    p = _p(st)
    ident = p.get("identificationModule", {})
    desc = p.get("descriptionModule", {})
    elig = p.get("eligibilityModule", {})
    out = p.get("outcomesModule", {})
    arms = p.get("armsInterventionsModule", {})
    conds = p.get("conditionsModule", {})

    L = ["ClinicalTrials.gov Study Record",
         "=" * 34,
         "",
         "NCT Number: %s" % ident.get("nctId", ""),
         "Brief Title: %s" % ident.get("briefTitle", ""),
         "Official Title: %s" % ident.get("officialTitle", ""),
         "Conditions: %s" % ", ".join(conds.get("conditions", [])),
         ""]
    if desc.get("briefSummary"):
        L += ["Brief Summary", "-" * 13, desc["briefSummary"].strip(), ""]
    if desc.get("detailedDescription"):
        L += ["Detailed Description", "-" * 20, desc["detailedDescription"].strip(), ""]
    if arms.get("interventions"):
        L += ["Interventions", "-" * 13]
        for iv in arms["interventions"]:
            L.append("* %s: %s — %s" % (iv.get("type", ""), iv.get("name", ""),
                                        (iv.get("description") or "").strip()))
        L.append("")
    if out.get("primaryOutcomes"):
        L += ["Primary Outcome Measures", "-" * 24]
        for o in out["primaryOutcomes"]:
            L.append("* %s" % o.get("measure", ""))
            if o.get("description"):
                L.append("  %s" % o["description"].strip())
            if o.get("timeFrame"):
                L.append("  Time frame: %s" % o["timeFrame"].strip())
        L.append("")
    if elig.get("eligibilityCriteria"):
        L += ["Eligibility Criteria", "-" * 20, elig["eligibilityCriteria"].strip(), ""]
    return "\n".join(L).rstrip() + "\n"


def gold(st):
    """The ground truth, read ONLY from structured modules — never from the text above."""
    p = _p(st)
    ident = p.get("identificationModule", {})
    dsg = p.get("designModule", {})
    sts = p.get("statusModule", {})
    spn = p.get("sponsorCollaboratorsModule", {})
    elig = p.get("eligibilityModule", {})
    out = p.get("outcomesModule", {})
    phases = [x for x in dsg.get("phases", []) if x and x != "NA"]
    prim = (out.get("primaryOutcomes") or [{}])[0]
    return {
        "nct_id": ident.get("nctId"),
        "brief_title": ident.get("briefTitle"),
        "condition": ", ".join(p.get("conditionsModule", {}).get("conditions", [])) or None,
        "phase": (phases[0].replace("PHASE", "Phase ").strip() if phases else None),
        "enrollment": (dsg.get("enrollmentInfo") or {}).get("count"),
        "lead_sponsor": (spn.get("leadSponsor") or {}).get("name"),
        "start_date": (sts.get("startDateStruct") or {}).get("date"),
        "completion_date": (sts.get("completionDateStruct") or {}).get("date"),
        "minimum_age": elig.get("minimumAge"),
        "sex": elig.get("sex"),
        "primary_outcome": prim.get("measure"),
        # ⚠︎ "NA" IS NOT A VALUE, IT IS THE ABSENCE OF ONE — caught by evals/check_labels.py on its
        # first run, in 14 of 57 records. The registry writes NA for a single-arm study, where
        # there is nothing to allocate anyone to. Carried through as the literal string it would
        # have become an enum value no field schema declares, and the model would have been marked
        # wrong for correctly not finding a concept the study does not have. None puts it in the
        # refusal half, which is where it belongs.
        "allocation": _drop_na((dsg.get("designInfo") or {}).get("allocation")),
        "masking": ((dsg.get("designInfo") or {}).get("maskingInfo") or {}).get("masking"),
    }


def _stated(value, text):
    """Is this gold value actually stated in the document's prose?

    Deliberately GENEROUS — it is measuring a ceiling, not scoring a model. Case-insensitive, and
    a number counts however it is written. If this says a field is unstated, no extractor of any
    kind could have found it, which is exactly the claim a ceiling needs to support.
    """
    if value in (None, ""):
        return False
    t = text.lower()
    v = str(value).lower().strip()
    if v in t:
        return True
    if re.fullmatch(r"\d+", v):                       # 120 / "120 patients" / "120 subjects"
        return re.search(r"\b%s\b" % re.escape(v), t) is not None
    # "18 Years" is stated by "18 years of age", "aged 18", "at least 18"
    m = re.fullmatch(r"(\d+)\s+years?", v)
    if m:
        return re.search(r"\b%s\b\s*(years?|yrs?|y\.?o\.?)?" % m.group(1), t) is not None
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ceiling", action="store_true",
                    help="report how many documents state each gold value at all, and write nothing")
    a = ap.parse_args()

    raws = sorted(glob.glob(os.path.join(RAW, "*.json")))
    if not raws:
        raise SystemExit("no raw records — run tools/fetch_corpus.py first")

    docs, golds = [], []
    for fn in raws:
        st = json.load(open(fn, encoding="utf-8"))
        g = gold(st)
        if not g["nct_id"]:
            continue
        docs.append((g["nct_id"], document(st)))
        golds.append(g)

    if a.ceiling:
        keys = [k for k in golds[0] if k != "nct_id"]
        print("%-18s %8s  %s" % ("field", "stated", "of %d documents" % len(docs)))
        for k in keys:
            n = sum(1 for (_, txt), g in zip(docs, golds) if _stated(g.get(k), txt))
            have = sum(1 for g in golds if g.get(k) not in (None, ""))
            print("%-18s %5d/%-3d  gold present in %d" % (k, n, len(docs), have))
        return

    os.makedirs(CORPUS, exist_ok=True)
    for nct, txt in docs:
        with open(os.path.join(CORPUS, "%s.txt" % nct), "w", encoding="utf-8") as f:
            f.write(txt)

    # ⚑ EVERY GOLD RECORD CARRIES A `stated` MAP, AND IT IS THE POINT OF THIS KIT.
    #
    # A registry value can be true and absent: the sponsor knows the start date, the document does
    # not say it. Scoring a model WRONG for not finding a value that is not there would measure
    # nothing but the corpus, and it would train the reader to distrust the one behaviour worth
    # having. So `stated` splits each field into the two questions that can actually be asked:
    #
    #   stated  -> did the model find the value that IS there?          (extraction accuracy)
    #   !stated -> did the model correctly return nothing?              (refusal / hallucination)
    #
    # The second is the guardrail for this use case, and it is why "not found" is a first-class
    # display state in the app rather than an empty cell. A model that invents a plausible date
    # for the 57 documents that never state one fails here loudly, which no single accuracy
    # percentage would have shown.
    with open(GOLD, "w", encoding="utf-8") as f:
        for (_, txt), g in zip(docs, golds):
            g = dict(g)
            g["stated"] = {k: _stated(v, txt) for k, v in g.items() if k != "nct_id"}
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    total = sum(len(t) for _, t in docs)
    print("build_corpus: %d document(s), %d bytes, gold -> %s"
          % (len(docs), total, os.path.relpath(GOLD, HERE)))


if __name__ == "__main__":
    main()
