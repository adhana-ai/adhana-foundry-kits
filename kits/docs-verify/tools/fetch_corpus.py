"""Pull raw study records from ClinicalTrials.gov into data/_fetched/.

WHAT THIS IS AND IS NOT. This writes the RAW API responses and nothing else, exactly as UC002's
fetcher does — fetching touches the network and is not reproducible byte-for-byte (the registry is
edited daily), while building the shippable corpus from a fetch IS reproducible. A forker can
rebuild the exact corpus this kit ships without a network, and can also pull a fresh one.

⚠︎ data/_fetched/ IS NEVER SHIPPED. `.gitignore` holds it. data/ ships the CORPUS, licensed for a
public repo — never the raw pulls.

WHY THIS SOURCE, FOR THIS KIT. Records are U.S. Government works and therefore public domain
(17 U.S.C. §105) — the one legal landmine a public kit clears first. For a claim-checking kit they
have a second property that matters more: a study record is DENSE WITH SPECIFIC, CHECKABLE
ASSERTIONS. Phase, enrolment, allocation, masking, eligibility bounds, the primary outcome and its
time frame are each a short factual statement a claim can agree with, contradict, or fail to
mention. That is what makes a three-way verdict gradable without a human in the loop.

WHY DIFFERENT CONDITIONS FROM UC002. docs-extract already ships a CTG corpus. Pulling the same
conditions would make this kit's corpus a near-duplicate of its sibling's, and two kits measuring
different things over the same 57 documents is a weaker demonstration than two corpora. These ten
conditions do not overlap that kit's.
"""
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "_fetched")
API = "https://clinicaltrials.gov/api/v2/studies"

CONDITIONS = ["osteoarthritis", "anemia", "copd", "hepatitis", "lymphoma",
              "endometriosis", "tuberculosis", "cataract", "obesity", "insomnia"]
PER_CONDITION = 3


def fetch(condition, n):
    q = urllib.parse.urlencode({
        "query.cond": condition,
        "filter.overallStatus": "COMPLETED",
        "pageSize": str(n),
        "countTotal": "false",
    })
    req = urllib.request.Request(
        "%s?%s" % (API, q),
        headers={"User-Agent": "adhana-foundry-kits/docs-verify (public-domain corpus build)"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    os.makedirs(RAW, exist_ok=True)
    kept, seen = 0, set()
    for cond in CONDITIONS:
        try:
            page = fetch(cond, PER_CONDITION)
        except Exception as exc:
            print("  %-16s FAILED (%s) — skipped, not retried" % (cond, exc))
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
        print("  %-16s ok" % cond)
        time.sleep(1.0)
    print("fetched %d unique record(s) -> data/_fetched/" % kept)


if __name__ == "__main__":
    main()
