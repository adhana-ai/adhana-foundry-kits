"""Pull raw study records from ClinicalTrials.gov into data/_fetched/.

WHAT THIS IS AND IS NOT. This writes the RAW API responses and nothing else, exactly as UC002's
and UC007's fetchers do — fetching touches the network and is not reproducible byte-for-byte (the
registry is edited daily), while building the shippable corpus from a fetch IS reproducible. A
forker can rebuild the exact corpus this kit ships without a network, and can also pull a fresh one.

⚠︎ data/_fetched/ IS NEVER SHIPPED. `.gitignore` holds it. data/ ships the CORPUS, licensed for a
public repo — never the raw pulls.

WHY THIS SOURCE, FOR THIS KIT. Records are U.S. Government works and therefore public domain
(17 U.S.C. §105). But this kit picks the source for a second reason the sibling kits do not have:
**a real federal rulebook governs these exact documents.** 42 CFR §11.28(a)(2) enumerates, by name,
the data elements a responsible party must submit for an applicable clinical trial. That is a
rulebook nobody had to invent — it is transcribed, and the documents it governs are public domain.
A compliance kit whose rules are made up is a demo; this one checks a real document against the
real rule that binds it.

── WHY THIS FETCHER SELECTS ON STATUS AND UC007'S DOES NOT ────────────────────────────────────
UC007's fetcher hard-filters `overallStatus=COMPLETED`, which is right for claim-checking and
WRONG here, and the difference was measured rather than argued. Reusing that corpus was proposed,
approved, and then found not to work: over its 20 documents, **6 of the candidate rules are
satisfied by all 20** (primary outcome, brief summary, interventions, time frame …) and **7 by
none** (official title, responsible party, facility, why stopped …). Only 2 discriminated at all.
Every rule that is trivially met on every document, or trivially never-addressed on every
document, teaches a grader nothing and measures a checker not at all.

The cause is the status filter. `Why Study Stopped` — §11.28(a)(2)(ii)(F) — is *by definition*
absent from a completed trial and present on a terminated, withdrawn or suspended one. Filtering
to COMPLETED flattens the single most discriminating rule in the whole part to a constant.

So this fetcher spreads deliberately across `overallStatus`, and the spread is the point:

    TERMINATED / WITHDRAWN / SUSPENDED   populate `whyStopped`   (absent from every COMPLETED record)
    RECRUITING / ACTIVE_NOT_RECRUITING   have no completion date yet, and often no results
    COMPLETED                            the dense case, kept so the corpus is not all edge

Measured live 2026-08-08 over 30 records across these five statuses: **17/30 carry a `whyStopped`
and 22/30 carry `secondaryOutcomes` — both 0/20 in UC007's corpus.**

── WHY DIFFERENT CONDITIONS AGAIN ─────────────────────────────────────────────────────────────
UC002 pulled ten conditions and UC007 pulled ten others, on the reasoning — written in UC007's own
fetcher docstring — that "two kits measuring different things over the same documents is a weaker
demonstration than two corpora". That argument applies a third time, so these ten overlap neither
set. Condition is not this kit's variance axis, but a corpus that is visibly its own is worth the
zero extra effort of choosing different search terms.
"""
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
API = "https://clinicaltrials.gov/api/v2/studies"

# Neither UC002's ten (diabetes, asthma, melanoma, stroke, epilepsy, hypertension, psoriasis,
# migraine, sepsis, glaucoma) nor UC007's ten (osteoarthritis, anemia, copd, hepatitis, lymphoma,
# endometriosis, tuberculosis, cataract, obesity, insomnia).
CONDITIONS = ["schizophrenia", "osteoporosis", "sickle cell", "crohn", "psoriatic arthritis",
              "atrial fibrillation", "macular degeneration", "cystic fibrosis", "gout", "eczema"]

# THE VARIANCE AXIS. Order matters only for readability; every status is pulled for every
# condition slice below, so no single condition can dominate a status bucket.
STATUSES = ["TERMINATED", "WITHDRAWN", "SUSPENDED", "RECRUITING",
            "ACTIVE_NOT_RECRUITING", "COMPLETED"]
PER_QUERY = 2


def fetch(condition, status, n):
    q = urllib.parse.urlencode({
        "query.cond": condition,
        "filter.overallStatus": status,
        "pageSize": str(n),
        "countTotal": "false",
    })
    req = urllib.request.Request(
        "%s?%s" % (API, q),
        headers={"User-Agent": "adhana-foundry-kits/docs-comply (public-domain corpus build)"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    os.makedirs(RAW, exist_ok=True)
    kept, seen = 0, set()
    by_status = {}
    for status in STATUSES:
        for cond in CONDITIONS:
            try:
                page = fetch(cond, status, PER_QUERY)
            except Exception as exc:
                print("  %-22s %-16s FAILED (%s) — skipped, not retried" % (status, cond, exc))
                continue
            for st in page.get("studies", []):
                nct = (st.get("protocolSection", {}).get("identificationModule", {})
                         .get("nctId"))
                if not nct or nct in seen:
                    continue
                seen.add(nct)
                with open(os.path.join(RAW, nct + ".json"), "w", encoding="utf-8") as fh:
                    json.dump(st, fh, indent=1)
                kept += 1
                by_status[status] = by_status.get(status, 0) + 1
            time.sleep(0.6)
        print("  %-22s %d record(s)" % (status, by_status.get(status, 0)))
    print("fetched %d unique record(s) -> data/_fetched/" % kept)


if __name__ == "__main__":
    main()
